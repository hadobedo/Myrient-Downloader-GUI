import os
import subprocess
import zipfile
import platform
import threading
import time
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
from PyQt5.QtWidgets import QApplication


class SplitPkgThread(QThread):
    progress = pyqtSignal(str)
    status = pyqtSignal(bool)

    def __init__(self, file_path):
        QThread.__init__(self)
        self.file_path = file_path

    def run(self):
        file_size = os.path.getsize(self.file_path)
        if file_size < 4294967295:
            self.status.emit(False)
            return
        else:
            chunk_size = 4294967295
            num_parts = -(-file_size // chunk_size)
            with open(self.file_path, 'rb') as f:
                i = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    with open(f"{Path(self.file_path).stem}.pkg.666{str(i).zfill(2)}", 'wb') as chunk_file:
                        chunk_file.write(chunk)
                    progress_text = f"Splitting {self.file_path}: part {i+1}/{num_parts} complete"
                    # print(progress_text)  # Removed: This will be handled by the connected signal
                    self.progress.emit(progress_text)
                    i += 1
            os.remove(self.file_path)
            self.status.emit(True)


class SplitIsoThread(QThread):
    progress = pyqtSignal(str)
    status = pyqtSignal(bool)

    def __init__(self, file_path):
        QThread.__init__(self)
        self.file_path = file_path

    def run(self):
        file_size = os.path.getsize(self.file_path)
        if file_size < 4294967295:
            self.status.emit(False)
            return
        else:
            chunk_size = 4294967295
            num_parts = -(-file_size // chunk_size)
            with open(self.file_path, 'rb') as f:
                i = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    with open(f"{os.path.splitext(self.file_path)[0]}.iso.{str(i)}", 'wb') as chunk_file:
                        chunk_file.write(chunk)
                    progress_text = f"Splitting {self.file_path}: part {i+1}/{num_parts} complete"
                    # print(progress_text)  # Removed: This will be handled by the connected signal
                    self.progress.emit(progress_text)
                    i += 1
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
                print(error_msg)
                self.output_signal.emit(error_msg)
                self.error_signal.emit(error_msg)
        except Exception as e:
            error_msg = f"Exception in command execution: {str(e)}"
            print(error_msg)
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

    def __init__(self, zip_path, output_path):
        super().__init__()
        self.zip_path = zip_path
        self.output_path = output_path
        self.extracted_files = []
        self.running = True
        self.paused = False
        self.partial_files = []  # Track files being extracted

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

                # Get list of files in the zip
                file_list = zip_ref.infolist()
                
                for info in file_list:
                    # Check if we are paused
                    if self.paused:
                        print("Unzip paused, cleaning up partial files...")
                        self.cleanup_partial_files()
                        self.unzip_paused_signal.emit()
                        return
                    
                    # Check if we are stopped
                    if not self.running:
                        print("Unzip stopped")
                        self.cleanup_partial_files()  # Clean up when stopped too
                        return

                    file_out_path = os.path.join(self.output_path, os.path.basename(info.filename))
                    
                    # Skip if file already exists and is complete (for resuming)
                    if os.path.exists(file_out_path) and os.path.getsize(file_out_path) == info.file_size:
                        print(f"File {file_out_path} already exists and is complete. Skipping.")
                        self.extracted_files.append(file_out_path)
                        extracted_size += info.file_size
                        self.progress_signal.emit(int((extracted_size / total_size) * 100))
                        continue
                    
                    # Add to partial files since we're going to extract it
                    self.partial_files.append(file_out_path)
                    
                    try:
                        with zip_ref.open(info) as source, open(file_out_path, 'wb') as target:
                            # Use a buffer size of 8MB for faster copying
                            buffer_size = 8 * 1024 * 1024  # 8MB chunks
                            while self.running and not self.paused:  # Check flags in loop
                                chunk = source.read(buffer_size)
                                if not chunk:
                                    break
                                target.write(chunk)
                                
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
                        self.progress_signal.emit(int((extracted_size / total_size) * 100))
        except FileNotFoundError as e:
            print(f"Error during unzip operation: {str(e)}")
            # No need to clean up since the file doesn't exist
        except Exception as e:
            print(f"Error during unzip operation: {str(e)}")
            self.cleanup_partial_files()

    def cleanup_partial_files(self):
        """Remove partially extracted files"""
        for file_path in self.partial_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Removed partial file: {file_path}")
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
