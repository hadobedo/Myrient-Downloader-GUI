import os
import subprocess
import zipfile
import platform
import threading
import time
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
from PyQt5.QtWidgets import QApplication

from core.utils import generate_unique_filename


class SplitPkgThread(QThread):
    progress = pyqtSignal(str)
    status = pyqtSignal(bool)

    def __init__(self, file_path, overwrite_manager=None):
        super().__init__()
        self.file_path = file_path
        self.overwrite_manager = overwrite_manager
    def run(self):
        file_size = os.path.getsize(self.file_path)
        if file_size < 4294967295:
            self.status.emit(False)
            return
        else:
            chunk_size = 4294967295
            num_parts = -(-file_size // chunk_size)
            
            # Check for existing split files if overwrite manager is available
            if self.overwrite_manager:
                existing_parts = []
                for i in range(num_parts):
                    split_file_path = os.path.join(os.path.dirname(self.file_path), f"{Path(self.file_path).stem}.pkg.666{str(i).zfill(2)}")
                    if os.path.exists(split_file_path):
                        existing_parts.append({
                            'path': split_file_path,
                            'existing_size': os.path.getsize(split_file_path),
                            'new_size': min(chunk_size, file_size - (i * chunk_size))
                        })
                
                if existing_parts:
                    from gui.overwrite_dialog import OverwriteDialog
                    choice, _ = self.overwrite_manager.handle_conflict(
                        existing_parts, "processing", None
                    )
                    
                    if choice == OverwriteDialog.CANCEL:
                        self.status.emit(False)
                        return
                    elif choice == OverwriteDialog.SKIP:
                        self.status.emit(True)  # Consider existing files as successful
                        return
                    # If OVERWRITE or RENAME, continue with splitting
            
            BUFFER_SIZE = 8 * 1024 * 1024  # 8MB read buffer
            with open(self.file_path, 'rb') as f:
                for i in range(num_parts):
                    part_size = min(chunk_size, file_size - (i * chunk_size))
                    split_file_path = os.path.join(os.path.dirname(self.file_path), f"{Path(self.file_path).stem}.pkg.666{str(i).zfill(2)}")
                    bytes_written = 0
                    with open(split_file_path, 'wb') as chunk_file:
                        while bytes_written < part_size:
                            read_size = min(BUFFER_SIZE, part_size - bytes_written)
                            data = f.read(read_size)
                            if not data:
                                break
                            chunk_file.write(data)
                            bytes_written += len(data)
                    progress_text = f"Splitting {self.file_path}: part {i+1}/{num_parts} complete"
                    self.progress.emit(progress_text)
            os.remove(self.file_path)
            self.status.emit(True)


class SplitIsoThread(QThread):
    progress = pyqtSignal(str)
    status = pyqtSignal(bool)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        file_size = os.path.getsize(self.file_path)
        if file_size < 4294967295:
            self.status.emit(False)
            return
        else:
            chunk_size = 4294967295
            num_parts = -(-file_size // chunk_size)
            BUFFER_SIZE = 8 * 1024 * 1024  # 8MB read buffer
            with open(self.file_path, 'rb') as f:
                for i in range(num_parts):
                    part_size = min(chunk_size, file_size - (i * chunk_size))
                    split_path = f"{os.path.splitext(self.file_path)[0]}.iso.{str(i)}"
                    bytes_written = 0
                    with open(split_path, 'wb') as chunk_file:
                        while bytes_written < part_size:
                            read_size = min(BUFFER_SIZE, part_size - bytes_written)
                            data = f.read(read_size)
                            if not data:
                                break
                            chunk_file.write(data)
                            bytes_written += len(data)
                    progress_text = f"Splitting {self.file_path}: part {i+1}/{num_parts} complete"
                    self.progress.emit(progress_text)
            self.status.emit(True)


class CommandRunner(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    
    def __init__(self, command):
        super().__init__()
        self.command = command
        self.process = None
        self.is_complete = False
        self.mutex = QMutex()
        self.wait_condition = QWaitCondition()

    def run(self):
        self.is_complete = False
        try:
            self.process = subprocess.Popen(
                self.command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                stdin=subprocess.PIPE, 
                bufsize=1, 
                universal_newlines=True
            )
            
            # If on Windows, send a newline character to ps3dec's standard input
            if platform.system() == 'Windows':
                self.process.stdin.write('\n')
                self.process.stdin.flush()
            
            # Start thread to read output
            read_thread = threading.Thread(target=self._reader_thread)
            read_thread.daemon = True
            read_thread.start()
            
            # Wait for process to complete
            self.process.wait()
            
            # Wait a bit for the read thread to complete
            read_thread.join(timeout=2.0)
            
            if self.process.returncode != 0:
                error_msg = f"Error: Command failed with return code {self.process.returncode}"
                # Error message will be emitted via signal
                self.output_signal.emit(error_msg)
                self.error_signal.emit(error_msg)
        except Exception as e:
            error_msg = f"Exception in command execution: {str(e)}"
            # Error message will be emitted via signal
            self.error_signal.emit(error_msg)
        finally:
            # Notify that we're done
            self.mutex.lock()
            self.is_complete = True
            self.wait_condition.wakeAll()
            self.mutex.unlock()
            
            # Always emit finished signal, even in case of error
            self.finished_signal.emit()

    def _reader_thread(self):
        """Thread function to read process output"""
        for line in iter(self.process.stdout.readline, ''):
            line_text = line.rstrip('\n')
            # Only use one output path - send through signal
            # The signal will be connected to a method that handles the output
            self.output_signal.emit(line_text)
            QApplication.processEvents()

    def wait_for_completion(self, timeout=None):
        """Wait for the command to complete with optional timeout in seconds"""
        self.mutex.lock()
        success = True
        if not self.is_complete:
            success = self.wait_condition.wait(self.mutex, int(timeout * 1000) if timeout else -1)
        self.mutex.unlock()
        return success


class UnzipRunner(QThread):
    progress_signal = pyqtSignal(int)
    unzip_paused_signal = pyqtSignal()

    def __init__(self, zip_path, output_path, overwrite_manager=None):
        super().__init__()
        self.zip_path = zip_path
        self.output_path = output_path
        self.extracted_files = []
        self.running = True
        self.paused = False
        self.partial_files = []  # Track files being extracted
        self.overwrite_manager = overwrite_manager

    def _should_preserve_folder_structure(self, zip_ref):
        """
        Determine if folder structure should be preserved based on zip contents.
        Returns (should_preserve, common_root_folder)
        """
        zip_base_name = os.path.splitext(os.path.basename(self.zip_path))[0]
        file_list = zip_ref.infolist()
        
        if not file_list:
            return False, None
            
        # Get all top-level entries (files and directories)
        top_level_entries = set()
        for info in file_list:
            # Normalize path separators
            normalized_path = info.filename.replace('\\', '/')
            # Skip empty entries
            if not normalized_path or normalized_path == '/':
                continue
            # Get the first path component
            first_component = normalized_path.split('/')[0]
            if first_component:
                top_level_entries.add(first_component)
        
        # If there's exactly one top-level directory, check if it differs from zip name
        if len(top_level_entries) == 1:
            top_level_dir = list(top_level_entries)[0]
            
            # Check if this top-level entry is actually a directory
            # (look for files that are inside this directory)
            is_directory = any(
                info.filename.replace('\\', '/').startswith(top_level_dir + '/')
                for info in file_list
                if info.filename.replace('\\', '/') != top_level_dir
            )
            
            if is_directory and top_level_dir != zip_base_name:
                # Removed "Preserving folder structure" print to clean up logs
                return True, top_level_dir
        
        # Removed "Flattening structure" print to clean up logs
        return False, None

    def _get_extraction_path(self, info, preserve_structure, common_root):
        """
        Get the extraction path for a file based on preservation settings.
        """
        if preserve_structure:
            # Preserve the full directory structure
            normalized_path = info.filename.replace('\\', '/')
            return os.path.join(self.output_path, normalized_path)
        else:
            # Flatten the structure (original behavior)
            return os.path.join(self.output_path, os.path.basename(info.filename))

    def run(self):
        if not self.zip_path.lower().endswith('.zip'):
            print(f"File {self.zip_path} is not a .zip file. Skipping unzip.")
            return

        # Check if the zip file exists before trying to open it
        if not os.path.exists(self.zip_path):
            print(f"Error: Zip file does not exist: {self.zip_path}")
            return

        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                total_size = sum([info.file_size for info in zip_ref.infolist()])
                extracted_size = 0

                # Determine extraction strategy
                preserve_structure, common_root = self._should_preserve_folder_structure(zip_ref)

                # Get list of files in the zip
                file_list = zip_ref.infolist()
                file_count = len([info for info in file_list if not (info.filename.endswith('/') or info.filename.endswith('\\'))])
                processed_files = 0
                
                for info in file_list:
                    # Skip directory entries (they don't contain actual file data)
                    if info.filename.endswith('/') or info.filename.endswith('\\'):
                        continue
                        
                    # Check if we are paused
                    if self.paused:
                        # Unzip paused, cleanup will be handled
                        self.cleanup_partial_files()
                        self.unzip_paused_signal.emit()
                        return
                    
                    # Check if we are stopped
                    if not self.running:
                        # Unzip stopped
                        self.cleanup_partial_files()  # Clean up when stopped too
                        return
                    file_out_path = self._get_extraction_path(info, preserve_structure, common_root)
                    
                    # Create directories if needed for structure preservation
                    os.makedirs(os.path.dirname(file_out_path), exist_ok=True)
                    
                    # Check for existing file and handle conflicts
                    if os.path.exists(file_out_path):
                        existing_size = os.path.getsize(file_out_path)
                        
                        # Skip if file already exists and is complete (for resuming)
                        if existing_size == info.file_size:
                            # File already exists and is complete, skipping
                            self.extracted_files.append(file_out_path)
                            extracted_size += info.file_size
                            processed_files += 1
                            
                            # Update progress for skipped files too
                            size_progress = (extracted_size / total_size) * 100 if total_size > 0 else 0
                            file_progress = (processed_files / file_count) * 100 if file_count > 0 else 0
                            progress_percent = max(size_progress, file_progress)
                            self.progress_signal.emit(int(min(progress_percent, 100)))
                            continue
                        
                        # Handle file conflict with overwrite manager if available
                        if self.overwrite_manager:
                            from gui.overwrite_dialog import OverwriteDialog
                            
                            conflict_info = {
                                'path': file_out_path,
                                'existing_size': existing_size,
                                'new_size': info.file_size
                            }
                            
                            choice, _ = self.overwrite_manager.handle_conflict(
                                conflict_info, "extraction", None  # No parent widget in thread
                            )
                            
                            if choice == OverwriteDialog.CANCEL:
                                # Stop extraction
                                self.running = False
                                return
                            elif choice == OverwriteDialog.SKIP:
                                # Skip this file, keep existing
                                self.extracted_files.append(file_out_path)
                                extracted_size += info.file_size  # Count as processed
                                processed_files += 1
                                
                                # Update progress for skipped files
                                size_progress = (extracted_size / total_size) * 100 if total_size > 0 else 0
                                file_progress = (processed_files / file_count) * 100 if file_count > 0 else 0
                                progress_percent = max(size_progress, file_progress)
                                self.progress_signal.emit(int(min(progress_percent, 100)))
                                continue
                            elif choice == OverwriteDialog.RENAME:
                                # Generate unique filename
                                file_out_path = self._generate_unique_filename(file_out_path)
                            # If OVERWRITE, continue with normal extraction (will overwrite)
                    
                    # Add to partial files since we're going to extract it
                    self.partial_files.append(file_out_path)
                    
                    try:
                        with zip_ref.open(info) as source, open(file_out_path, 'wb') as target:
                            # Use a buffer size of 8MB for faster copying
                            buffer_size = 8 * 1024 * 1024  # 8MB chunks
                            bytes_written = 0
                            file_size = info.file_size
                            
                            while self.running and not self.paused:  # Check flags in loop
                                chunk = source.read(buffer_size)
                                if not chunk:
                                    break
                                target.write(chunk)
                                bytes_written += len(chunk)
                                
                                # For large files, emit progress updates during extraction
                                if file_size > 50 * 1024 * 1024:  # Files larger than 50MB
                                    file_progress_within = (bytes_written / file_size) if file_size > 0 else 0
                                    overall_file_progress = (processed_files + file_progress_within) / file_count if file_count > 0 else 0
                                    overall_size_progress = (extracted_size + bytes_written) / total_size if total_size > 0 else 0
                                    
                                    progress_percent = max(overall_file_progress * 100, overall_size_progress * 100)
                                    self.progress_signal.emit(int(min(progress_percent, 100)))
                                
                                # Periodically check if we should stop
                                QApplication.processEvents()
                    except Exception as e:
                        print(f"Error extracting {info.filename}: {e}")
                        # Mark the file as incomplete
                        if file_out_path in self.partial_files:
                            self.partial_files.remove(file_out_path)
                        continue

                    if self.running and not self.paused:  # Only count if not stopped/paused
                        self.extracted_files.append(file_out_path)
                        extracted_size += info.file_size
                        processed_files += 1
                        
                        # Emit progress based on both size and file count for more responsive updates
                        size_progress = (extracted_size / total_size) * 100 if total_size > 0 else 0
                        file_progress = (processed_files / file_count) * 100 if file_count > 0 else 0
                        
                        # Use the maximum of the two progress calculations for better responsiveness
                        progress_percent = max(size_progress, file_progress)
                        self.progress_signal.emit(int(min(progress_percent, 100)))
        except FileNotFoundError as e:
            print(f"Error during unzip operation: {str(e)}")
            # No need to clean up since the file doesn't exist
        except Exception as e:
            print(f"Error during unzip operation: {str(e)}")
            self.cleanup_partial_files()

    def cleanup_partial_files(self):
        """Remove partially extracted files and empty directories"""
        for file_path in self.partial_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    # Removed partial file during cleanup
                    
                    # Try to remove empty parent directories
                    parent_dir = os.path.dirname(file_path)
                    while parent_dir and parent_dir != self.output_path:
                        try:
                            if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                                os.rmdir(parent_dir)
                                # Removed empty directory during cleanup
                                parent_dir = os.path.dirname(parent_dir)
                            else:
                                break
                        except OSError:
                            break
            except Exception as e:
                print(f"Error removing partial file {file_path}: {e}")
        
        self.partial_files = []  # Clear the list after cleanup

    def stop(self):
        """Stop the extraction process"""
        self.running = False
        # Don't call wait() here - let the caller handle waiting

    def pause(self):
        """Pause the extraction process"""
        self.paused = True

    def resume(self):
        """Resume the extraction process"""
        self.paused = False
    
    def _generate_unique_filename(self, file_path):
        """Generate a unique filename by adding a suffix."""
        return generate_unique_filename(file_path)
