import os
import shutil
import glob
import zipfile
from PyQt5.QtCore import QObject, pyqtSignal, QEventLoop
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtGui import QColor

from core.ps3_fileprocessor import PS3FileProcessor
from threads.processing_threads import UnzipRunner, CommandRunner, SplitIsoThread, SplitPkgThread
from core.settings import BinaryValidationDialog


class ProcessingManager(QObject):
    """Manages all file processing operations separate from GUI."""
    
    # Signals for GUI updates
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    processing_complete = pyqtSignal()
    processing_paused = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, settings_manager, config_manager, output_window, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.config_manager = config_manager
        self.output_window = output_window
        self.current_operation = None
        self.current_file_path = None
        self.unzip_runner = None
        self.processors = {}  # Cache processors by platform
        
    def get_ps3_processor(self):
        """Get or create a PS3 processor."""
        if 'ps3' not in self.processors:
            processor = PS3FileProcessor(
                self.settings_manager, self.output_window, None
            )
            processor.set_progress_callback(self.progress_updated.emit)
            self.processors['ps3'] = processor
        return self.processors['ps3']
    
    def split_iso(self, iso_path):
        """Split an ISO file for FAT32 filesystems."""
        if os.path.getsize(iso_path) < 4294967295:
            self.output_window.append(f"File {iso_path} is smaller than 4GB. Skipping split.")
            return False
            
        split_iso_thread = SplitIsoThread(iso_path)
        split_iso_thread.progress.connect(self._print_progress)
        split_iso_thread.start()
        split_iso_thread.wait()
        
        return True
    
    def _print_progress(self, text):
        """Print progress updates."""
        self.output_window.append(text)
    
    def process_ps3_files(self, extracted_files, base_name, queue_position, settings, queue_item=None):
        """Process PS3 ISO files with decryption and extraction."""
        try:
            processor = self.get_ps3_processor()
            
            # Check if we should organize content into game folders (universal setting)
            organize_content = settings.get('organize_content_to_folders', False)
            
            if organize_content:
                # Create a folder with the game's name and put all content inside it
                game_folder_path = os.path.join(self.settings_manager.ps3iso_dir, base_name)
                os.makedirs(game_folder_path, exist_ok=True)
                final_target_dir = game_folder_path
                self.output_window.append(f"({queue_position}) Organizing PS3 content into game folder: {base_name}")
            else:
                # Put files directly in the PS3 directory (original behavior)
                final_target_dir = self.settings_manager.ps3iso_dir
            
            # Handle dkey file if needed
            if settings.get('decrypt_iso') or settings.get('keep_dkey_file'):
                dkey_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}.dkey")
                if not os.path.isfile(dkey_path):
                    self._download_dkey_file(base_name, queue_position)

            # Decrypt ISO if needed
            if settings.get('decrypt_iso'):
                iso_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}.iso")
                if os.path.isfile(os.path.join(self.settings_manager.processing_dir, f"{base_name}.dkey")):
                    self.status_updated.emit("DECRYPTING")
                    
                    with open(os.path.join(self.settings_manager.processing_dir, f"{base_name}.dkey"), 'r') as file:
                        key = file.read(32)
                    
                    self.output_window.append(f"({queue_position}) Decrypting ISO for {base_name}...")
                    # processor.decrypt_iso returns the path to the original encrypted file (now .enc)
                    # and modifies iso_path to be the decrypted ISO.
                    original_encrypted_iso_path = processor.decrypt_iso(iso_path, key) # iso_path is now decrypted

                    decrypted_iso_exists = os.path.exists(iso_path)

                    if settings.get('extract_ps3_iso') and decrypted_iso_exists:
                        # _extract_ps3_iso will handle moving the extracted content
                        # and the decrypted ISO (if kept) to final_target_dir
                        self._extract_ps3_iso(processor, iso_path, base_name, queue_position, settings, final_target_dir, organize_content)
                    elif decrypted_iso_exists:
                        # Not extracting, just move the decrypted ISO to final location
                        if organize_content:
                            self._move_content_to_game_folder(iso_path, final_target_dir, queue_position, is_directory=False)
                        else:
                            self._move_file_to_directory(iso_path, final_target_dir, queue_position)
                    
                    # Handle the original encrypted ISO (which is now likely base_name.iso.enc)
                    if os.path.exists(original_encrypted_iso_path):
                        if settings.get('keep_encrypted_iso'):
                            if organize_content:
                                self._move_content_to_game_folder(original_encrypted_iso_path, final_target_dir, queue_position, is_directory=False)
                            else:
                                self._move_file_to_directory(original_encrypted_iso_path, final_target_dir, queue_position)
                        else:
                            try:
                                os.remove(original_encrypted_iso_path)
                                self.output_window.append(f"({queue_position}) Deleted original encrypted ISO: {original_encrypted_iso_path}")
                            except Exception as e:
                                self.output_window.append(f"({queue_position}) Warning: Could not delete original encrypted ISO: {e}")
            else:
                # Not decrypting, but the ISO might still be in processing_dir from unzipping.
                # Move the (still encrypted) ISO to the final directory.
                iso_path_in_processing = os.path.join(self.settings_manager.processing_dir, f"{base_name}.iso")
                if os.path.exists(iso_path_in_processing):
                    if organize_content:
                        self._move_content_to_game_folder(iso_path_in_processing, final_target_dir, queue_position, is_directory=False)
                    else:
                        self._move_file_to_directory(iso_path_in_processing, final_target_dir, queue_position)
            
            # Handle dkey file (move to final_target_dir if kept, else delete from processing_dir)
            self._handle_dkey_file(base_name, queue_position, settings.get('keep_dkey_file'), final_target_dir, organize_content)
            
            # Clean up any remaining .iso files in processing_dir for this base_name if they weren't moved
            # This is a safeguard.
            lingering_iso = os.path.join(self.settings_manager.processing_dir, f"{base_name}.iso")
            if os.path.exists(lingering_iso):
                self.output_window.append(f"({queue_position}) Warning: Lingering ISO found in processing: {lingering_iso}. Deleting.")
                try:
                    os.remove(lingering_iso)
                except Exception as e:
                    self.output_window.append(f"({queue_position}) Failed to delete lingering ISO: {e}")
        except Exception as e:
            self.error_occurred.emit(f"Processing failed for {base_name}: {str(e)}")
    
    def process_psn_files(self, extracted_files, base_name, queue_position, settings, queue_item=None):
        """Process PS3 PSN packages."""
        try:
            processor = self.get_ps3_processor()
            
            # Check if we should organize content into game folders (universal setting)
            organize_content = settings.get('organize_content_to_folders', False)
            
            if organize_content:
                # Create a folder with the game's name and put all content inside it
                game_folder_path_pkg = os.path.join(self.settings_manager.psn_pkg_dir, base_name)
                game_folder_path_rap = os.path.join(self.settings_manager.psn_rap_dir, base_name)
                os.makedirs(game_folder_path_pkg, exist_ok=True)
                os.makedirs(game_folder_path_rap, exist_ok=True)
                final_pkg_target_dir = game_folder_path_pkg
                final_rap_target_dir = game_folder_path_rap
                self.output_window.append(f"({queue_position}) Organizing PSN content into game folder: {base_name}")
            else:
                # Put files directly in the PSN directories (original behavior)
                final_pkg_target_dir = self.settings_manager.psn_pkg_dir
                final_rap_target_dir = self.settings_manager.psn_rap_dir
            
            # Process each extracted file
            for file in extracted_files:
                if file.endswith('.pkg'):
                    new_file_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}{os.path.splitext(file)[1]}")
                    os.rename(file, new_file_path)
                    
                    # Split PKG if needed
                    if settings.get('split_pkg'):
                        self.status_updated.emit("SPLITTING")
                        processor.split_pkg(new_file_path)
            
            # Move files to output directories with organization support
            self._move_rap_files_with_organization(final_rap_target_dir, organize_content, queue_position)
            self._move_pkg_files_with_organization(final_pkg_target_dir, organize_content, queue_position)
            
        except Exception as e:
            self.error_occurred.emit(f"Processing failed for {base_name}: {str(e)}")
    
    def process_ps2_files(self, extracted_files, base_name, queue_position, settings, queue_item=None):
        """Process PS2 ISO files."""
        try:
            # Check if we should organize content into game folders (universal setting)
            organize_content = settings.get('organize_content_to_folders', False)
            
            if organize_content:
                # Create a folder with the game's name and put all content inside it
                game_folder_path = os.path.join(self.settings_manager.ps2iso_dir, base_name)
                os.makedirs(game_folder_path, exist_ok=True)
                final_target_dir = game_folder_path
                self.output_window.append(f"({queue_position}) Organizing PS2 content into game folder: {base_name}")
            else:
                # Put files directly in the PS2 directory (original behavior)
                final_target_dir = self.settings_manager.ps2iso_dir
            
            # Process each extracted file
            for file in extracted_files:
                if file.endswith('.iso'):
                    # Split ISO if needed
                    if settings.get('split_large_files') and os.path.getsize(file) >= 4294967295:
                        self.status_updated.emit("SPLITTING")
                        self.output_window.append(f"({queue_position}) Splitting ISO for {base_name}...")
                        split_success = self.split_iso(file)
                        
                        # Delete unsplit ISO from processing_dir if not keeping it
                        if split_success and not settings.get('keep_unsplit_file'):
                            if os.path.exists(file): # 'file' is in processing_dir
                                os.remove(file)
                        
                        # Move split files from processing_dir to final_target_dir
                        # The split_iso method in the processor should place split files in processing_dir first.
                        for split_part_name in glob.glob(os.path.join(self.settings_manager.processing_dir, base_name + '*.iso.*')):
                            if organize_content:
                                self._move_content_to_game_folder(split_part_name, final_target_dir, queue_position, is_directory=False)
                            else:
                                self._move_file_to_directory(split_part_name, final_target_dir, queue_position)
                        
                        # If keeping unsplit file and it was split, ensure the original (if it still exists in processing) is moved.
                        if split_success and settings.get('keep_unsplit_file') and os.path.exists(file):
                            if organize_content:
                                self._move_content_to_game_folder(file, final_target_dir, queue_position, is_directory=False)
                            else:
                                self._move_file_to_directory(file, final_target_dir, queue_position)

                    else:
                        # Not splitting, or split failed, or file too small. Move the ISO directly.
                        # 'file' is path in processing_dir
                        if organize_content:
                            self._move_content_to_game_folder(file, final_target_dir, queue_position, is_directory=False)
                        else:
                            self._move_file_to_directory(file, final_target_dir, queue_position)
                
                # Handle .bin and .cue files, moving from processing_dir to final_target_dir
                elif file.endswith('.bin') or file.endswith('.cue'): # 'file' is path in processing_dir
                    if organize_content:
                        self._move_content_to_game_folder(file, final_target_dir, queue_position, is_directory=False)
                    else:
                        self._move_file_to_directory(file, final_target_dir, queue_position)
            
        except Exception as e:
            self.error_occurred.emit(f"Processing failed for {base_name}: {str(e)}")
    
    def process_psx_files(self, extracted_files, base_name, queue_position, settings, queue_item=None):
        """Process PSX ISO files."""
        try:
            # Check if we should organize content into game folders (universal setting)
            organize_content = settings.get('organize_content_to_folders', False)
            
            if organize_content:
                # Create a folder with the game's name and put all content inside it
                game_folder_path = os.path.join(self.settings_manager.psxiso_dir, base_name)
                os.makedirs(game_folder_path, exist_ok=True)
                final_target_dir = game_folder_path
                self.output_window.append(f"({queue_position}) Organizing PSX content into game folder: {base_name}")
            else:
                # Put files directly in the PSX directory (original behavior)
                final_target_dir = self.settings_manager.psxiso_dir
            
            # Move all related files (e.g., .bin, .cue) from processing_dir to final_target_dir
            for file_in_processing in glob.glob(os.path.join(self.settings_manager.processing_dir, base_name + '*')):
                if os.path.isfile(file_in_processing): # Ensure it's a file
                    if organize_content:
                        self._move_content_to_game_folder(file_in_processing, final_target_dir, queue_position, is_directory=False)
                    else:
                        self._move_file_to_directory(file_in_processing, final_target_dir, queue_position)
                
        except Exception as e:
            self.error_occurred.emit(f"Processing failed for {base_name}: {str(e)}")
    
    def process_psp_files(self, extracted_files, base_name, queue_position, settings, queue_item=None):
        """Process PSP ISO files."""
        try:
            # Check if we should organize content into game folders (universal setting)
            organize_content = settings.get('organize_content_to_folders', False)
            
            if organize_content:
                # Create a folder with the game's name and put all content inside it
                game_folder_path = os.path.join(self.settings_manager.pspiso_dir, base_name)
                os.makedirs(game_folder_path, exist_ok=True)
                final_target_dir = game_folder_path
                self.output_window.append(f"({queue_position}) Organizing PSP content into game folder: {base_name}")
            else:
                # Put files directly in the PSP directory (original behavior)
                final_target_dir = self.settings_manager.pspiso_dir
            
            # Path to the ISO if it exists in processing_dir
            iso_path_in_processing = os.path.join(self.settings_manager.processing_dir, f"{base_name}.iso")

            if settings.get('split_large_files') and os.path.exists(iso_path_in_processing) and os.path.getsize(iso_path_in_processing) >= 4294967295:
                self.status_updated.emit("SPLITTING")
                self.output_window.append(f"({queue_position}) Splitting ISO for {base_name}...")
                # processor.split_iso should operate on iso_path_in_processing and place splits in processing_dir
                split_success = self.split_iso(iso_path_in_processing)
                
                if split_success:
                    # Move split parts to final_target_dir
                    for split_part_name in glob.glob(os.path.join(self.settings_manager.processing_dir, base_name + '*.iso.*')):
                        if organize_content:
                            self._move_content_to_game_folder(split_part_name, final_target_dir, queue_position, is_directory=False)
                        else:
                            self._move_file_to_directory(split_part_name, final_target_dir, queue_position)

                    # Handle original unsplit ISO in processing_dir
                    if os.path.exists(iso_path_in_processing):
                        if not settings.get('keep_unsplit_file'):
                            os.remove(iso_path_in_processing)
                        else: # Keep unsplit file, so move it to final_target_dir
                            if organize_content:
                                self._move_content_to_game_folder(iso_path_in_processing, final_target_dir, queue_position, is_directory=False)
                            else:
                                self._move_file_to_directory(iso_path_in_processing, final_target_dir, queue_position)
                else: # Splitting failed or not needed, move original if it exists
                    if os.path.exists(iso_path_in_processing):
                        if organize_content:
                            self._move_content_to_game_folder(iso_path_in_processing, final_target_dir, queue_position, is_directory=False)
                        else:
                            self._move_file_to_directory(iso_path_in_processing, final_target_dir, queue_position)
            
            elif os.path.exists(iso_path_in_processing): # Not splitting, but ISO exists
                if organize_content:
                    self._move_content_to_game_folder(iso_path_in_processing, final_target_dir, queue_position, is_directory=False)
                else:
                    self._move_file_to_directory(iso_path_in_processing, final_target_dir, queue_position)

            # Move any other related files for this base_name from processing to final_target_dir
            # This handles cases where the primary file might not be .iso or if there are companion files.
            for other_file_in_processing in glob.glob(os.path.join(self.settings_manager.processing_dir, base_name + '*')):
                if os.path.isfile(other_file_in_processing) and not other_file_in_processing.endswith('.iso') and not other_file_in_processing.endswith('.iso.*'):
                     # Avoid re-moving ISOs/splits if already handled
                    if organize_content:
                        self._move_content_to_game_folder(other_file_in_processing, final_target_dir, queue_position, is_directory=False)
                    else:
                        self._move_file_to_directory(other_file_in_processing, final_target_dir, queue_position)
            
        except Exception as e:
            self.error_occurred.emit(f"Processing failed for {base_name}: {str(e)}")
    def process_xbox360_files(self, extracted_files, base_name, queue_position, settings, queue_item=None):
        """Process Xbox 360 files - now just calls generic processing."""
        # Xbox 360 processing is now handled by generic processing
        platform_id = getattr(queue_item, 'platform_id', 'xbox360') if queue_item else 'xbox360'
        self.process_generic_files(extracted_files, base_name, queue_position, platform_id, settings, queue_item)
    
    def process_generic_files(self, extracted_files, base_name, queue_position, platform_id, settings, queue_item=None):
        """Generic file processing for any platform with optional content organization."""
        try:
            # Use the new directory management system to get the output directory
            final_output_dir_for_platform = self.settings_manager.get_platform_directory(platform_id)
            
            if not final_output_dir_for_platform:
                self.error_occurred.emit(f"Configuration error: Output directory for platform '{platform_id}' is empty or invalid.")
                # Clean up extracted files from processing_dir to prevent clutter
                for f_path in extracted_files:
                    if os.path.exists(f_path) and os.path.isfile(f_path):
                        try:
                            os.remove(f_path)
                        except Exception as e_rem:
                            self.output_window.append(f"({queue_position}) Error cleaning up {f_path}: {e_rem}")
                    elif os.path.exists(f_path) and os.path.isdir(f_path):
                        try:
                            shutil.rmtree(f_path)
                        except Exception as e_rem_dir:
                            self.output_window.append(f"({queue_position}) Error cleaning up directory {f_path}: {e_rem_dir}")
                return

            # Check if we should organize content into game folders (universal setting)
            organize_content = settings.get('organize_content_to_folders', False)
            
            if organize_content:
                # Create a folder with the game's name and put all content inside it
                game_folder_path = os.path.join(final_output_dir_for_platform, base_name)
                os.makedirs(game_folder_path, exist_ok=True)
                final_target_dir = game_folder_path
                self.output_window.append(f"({queue_position}) Organizing content into game folder: {base_name}")
            else:
                # Put files directly in the platform directory (original behavior)
                final_target_dir = final_output_dir_for_platform

            # Track what we've moved to avoid duplicates
            moved_items = set()
            
            # Process all extracted files and directories
            for path_in_processing in extracted_files:
                if not os.path.exists(path_in_processing):
                    continue
                    
                # Skip if we've already moved this item
                if path_in_processing in moved_items:
                    continue
                
                # Get the relative path from processing directory
                rel_path = os.path.relpath(path_in_processing, self.settings_manager.processing_dir)
                path_parts = rel_path.split(os.sep)
                
                # Determine what to move - we want to move top-level items
                if len(path_parts) > 1:
                    # This is a file/dir inside a subdirectory
                    # Move the top-level directory instead of individual files if organizing content
                    top_level_dir = os.path.join(self.settings_manager.processing_dir, path_parts[0])
                    if os.path.isdir(top_level_dir) and top_level_dir not in moved_items:
                        if organize_content:
                            # Use game folder organization method
                            self._move_content_to_game_folder(top_level_dir, final_target_dir, queue_position, is_directory=True)
                        else:
                            # Use traditional method
                            self._move_directory_structure(top_level_dir, final_target_dir, queue_position)
                        moved_items.add(top_level_dir)
                        # Mark all files in this directory as moved
                        for extracted_file in extracted_files:
                            if extracted_file.startswith(top_level_dir + os.sep) or extracted_file == top_level_dir:
                                moved_items.add(extracted_file)
                    elif os.path.isfile(path_in_processing) and path_in_processing not in moved_items:
                        # Individual file not in a directory structure
                        self._move_individual_file(path_in_processing, final_target_dir, queue_position, settings, organize_content)
                        moved_items.add(path_in_processing)
                else:
                    # This is a top-level file or directory
                    if path_in_processing not in moved_items:
                        if os.path.isdir(path_in_processing):
                            if organize_content:
                                # Use game folder organization method
                                self._move_content_to_game_folder(path_in_processing, final_target_dir, queue_position, is_directory=True)
                            else:
                                # Use traditional method
                                self._move_directory_structure(path_in_processing, final_target_dir, queue_position)
                        else:
                            # Individual file
                            self._move_individual_file(path_in_processing, final_target_dir, queue_position, settings, organize_content)
                        moved_items.add(path_in_processing)
            
            # Clean up any empty directories left behind in processing_dir
            self._cleanup_empty_directories_in_processing(queue_position)

        except Exception as e:
            self.error_occurred.emit(f"Processing failed for {base_name} (platform {platform_id}): {str(e)}")
    
    def unzip_file_with_pause_support(self, zip_path, output_path, queue_position, base_name):
        """Unzip a file with pause support and return the list of extracted files."""
        self.current_operation = 'unzip'
        self.current_file_path = zip_path
        
        # Check if the file exists before attempting to unzip
        if not os.path.exists(zip_path):
            self.output_window.append(f"({queue_position}) Error: File to unzip doesn't exist: {zip_path}")
            return []
        
        self.status_updated.emit("UNZIPPING")
        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")
        self.progress_updated.emit(0)
        
        self.unzip_runner = UnzipRunner(zip_path, output_path)
        # Connect progress signal to ensure unzip progress shows in progress bar
        self.unzip_runner.progress_signal.connect(self.progress_updated.emit)
        self.unzip_runner.unzip_paused_signal.connect(self.processing_paused.emit)
        
        # Create an event loop to wait for the thread
        loop = QEventLoop()
        self.unzip_runner.finished.connect(loop.quit)
        
        self.unzip_runner.start()
        loop.exec_()
        
        # Ensure progress shows 100% when unzipping is complete
        if not self.unzip_runner.paused and self.unzip_runner.running:
            self.progress_updated.emit(100)
        
        return self.unzip_runner.extracted_files
    
    def pause_processing(self):
        """Pause the current processing operation."""
        if self.unzip_runner and self.current_operation == 'unzip':
            self.unzip_runner.pause()
    
    def resume_processing(self):
        """Resume a previously paused processing operation."""
        if self.unzip_runner and self.current_operation == 'unzip':
            self.unzip_runner.resume()
    
    def stop_processing(self):
        """Stop the current processing operation."""
        if self.unzip_runner:
            self.unzip_runner.stop()
    
    def _download_dkey_file(self, base_name, queue_position):
        """Download the dkey file for PS3 decryption."""
        from threads.download_threads import DownloadThread
        
        dkey_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}.dkey")
        self.output_window.append(f"({queue_position}) Getting dkey for {base_name}...")
        dkey_zip = os.path.join(self.settings_manager.processing_dir, f"{base_name}.zip")
        dkey_url = self.config_manager.get_url('ps3', 'dkeys')
        
        if not dkey_url:
            self.error_occurred.emit("ERROR: Missing URL configuration for PS3 disc keys")
            return
            
        # Download dkey zip
        dkey_url = f"{dkey_url}/{base_name}.zip"
        download_thread = DownloadThread(dkey_url, dkey_zip)
        download_thread.progress_signal.connect(self.progress_updated.emit)
        
        loop = QEventLoop()
        download_thread.finished.connect(loop.quit)
        download_thread.start()
        loop.exec_()
        
        # Extract dkey
        with zipfile.ZipFile(dkey_zip, 'r') as zip_ref:
            zip_ref.extractall(self.settings_manager.processing_dir)
        os.remove(dkey_zip)
    
    def _extract_ps3_iso(self, processor, iso_path, base_name, queue_position, settings, final_target_dir, organize_content):
        """Extract PS3 ISO contents."""
        if not os.path.isfile(self.settings_manager.extractps3iso_binary):
            # Need to check/download extractps3iso using the new validation system
            from core.settings import BinaryValidationDialog
            dialog = BinaryValidationDialog("extractps3iso", self.parent())
            if dialog.exec_():
                if not self.settings_manager.download_extractps3iso():
                    self.output_window.append(f"({queue_position}) Failed to download extractps3iso. ISO extraction will not be available.")
                    return
            else:
                self.output_window.append(f"({queue_position}) extractps3iso is required for extraction but was not downloaded.")
                return
        
        self.status_updated.emit("EXTRACTING")
        self.output_window.append(f"({queue_position}) Extracting ISO contents for {base_name}...")
        
        # iso_path is the path to the decrypted ISO in processing_dir
        # processor.extract_iso should extract into a subdirectory within processing_dir
        success, extracted_content_path_in_processing = processor.extract_iso(iso_path) # e.g., processing_dir/GameName_extracted
        
        if success and os.path.exists(extracted_content_path_in_processing):
            # Move extracted content using appropriate method
            if organize_content:
                self._move_content_to_game_folder(extracted_content_path_in_processing, final_target_dir, queue_position, is_directory=True)
            else:
                # Determine final path for the extracted content in final_target_dir
                final_extracted_content_name = os.path.basename(extracted_content_path_in_processing)
                final_target_path_for_extracted = os.path.join(final_target_dir, final_extracted_content_name)

                if os.path.exists(final_target_path_for_extracted):
                    # Basic overwrite: remove existing if it's a directory
                    if os.path.isdir(final_target_path_for_extracted):
                        try:
                            shutil.rmtree(final_target_path_for_extracted)
                            self.output_window.append(f"({queue_position}) Removed existing extracted content at {final_target_path_for_extracted}")
                        except Exception as e:
                            self.output_window.append(f"({queue_position}) Warning: Could not remove existing extracted content: {e}")
                    else: # It's a file, remove it
                         os.remove(final_target_path_for_extracted)

                try:
                    shutil.move(extracted_content_path_in_processing, final_target_path_for_extracted)
                    self.output_window.append(f"({queue_position}) Extracted ISO contents moved to {final_target_path_for_extracted}")
                except Exception as e:
                    self.output_window.append(f"({queue_position}) Error moving extracted ISO contents: {e}")
                    # If move failed, extracted content is still in processing_dir. It might be cleaned up later or retried.
        elif not success:
            self.output_window.append(f"({queue_position}) Failed to extract ISO contents for {iso_path}")

        # Handle the decrypted ISO file itself (iso_path, which is in processing_dir)
        if os.path.exists(iso_path): # Check if it still exists (e.g. wasn't corrupted or deleted by processor)
            if settings.get('extract_ps3_iso') and success: # If we extracted successfully
                if settings.get('keep_decrypted_iso_after_extraction'):
                    if organize_content:
                        self._move_content_to_game_folder(iso_path, final_target_dir, queue_position, is_directory=False)
                    else:
                        self._move_file_to_directory(iso_path, final_target_dir, queue_position)
                else: # Not keeping it, so delete from processing_dir
                    try:
                        os.remove(iso_path)
                        self.output_window.append(f"({queue_position}) Deleted decrypted ISO from processing dir after extraction.")
                    except Exception as e:
                        self.output_window.append(f"({queue_position}) Warning: Could not delete decrypted ISO from processing: {e}")
            else: # Not extracting, or extraction failed. Move the decrypted ISO to final location.
                if organize_content:
                    self._move_content_to_game_folder(iso_path, final_target_dir, queue_position, is_directory=False)
                else:
                    self._move_file_to_directory(iso_path, final_target_dir, queue_position)
    
    def _move_file_to_directory(self, source_file_path, target_final_dir, queue_position):
        """
        Move a file from source_file_path (expected to be in processing_dir or elsewhere)
        to the target_final_dir. Handles existing files in the target.
        """
        if not os.path.exists(source_file_path):
            self.output_window.append(f"({queue_position}) Source file for move does not exist: {source_file_path}")
            return

        target_file_path = os.path.join(target_final_dir, os.path.basename(source_file_path))
        
        # Ensure target directory exists
        os.makedirs(target_final_dir, exist_ok=True)

        if os.path.exists(target_file_path):
            try:
                # Simple overwrite: remove existing file at destination
                os.remove(target_file_path)
                self.output_window.append(f"({queue_position}) Removed existing file at destination: {target_file_path}")
            except Exception as e:
                self.output_window.append(f"({queue_position}) Warning: Could not remove existing file at {target_file_path}: {e}. Move may fail.")
                # Optionally, could append a suffix or skip, but overwrite is simpler for now.
        
        try:
            shutil.move(source_file_path, target_file_path) # Move to target_file_path to place it IN the dir
            self.output_window.append(f"({queue_position}) Moved {os.path.basename(source_file_path)} to {target_final_dir}")
        except Exception as e:
            self.output_window.append(f"({queue_position}) Error moving file {source_file_path} to {target_final_dir}: {e}")
            # If move fails, source_file_path remains.
    
    def _handle_dkey_file(self, base_name, queue_position, keep_dkey, final_target_dir=None, organize_content=False):
        """Handle dkey file deletion or moving."""
        dkey_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}.dkey")
        
        if os.path.exists(dkey_path):
            if not keep_dkey:
                try:
                    os.remove(dkey_path)
                    self.output_window.append(f"({queue_position}) Deleted dkey file from processing directory.")
                except Exception as e:
                    self.output_window.append(f"({queue_position}) Warning: Could not delete dkey file: {e}")
            else:
                target_dir = final_target_dir if final_target_dir else self.settings_manager.ps3iso_dir
                if organize_content:
                    self._move_content_to_game_folder(dkey_path, target_dir, queue_position, is_directory=False)
                else:
                    self._move_file_to_directory(dkey_path, target_dir, queue_position)
    
    def _move_rap_files(self):
        """Move RAP files from processing_dir to PSN RAP directory."""
        for file_in_processing in glob.glob(os.path.join(self.settings_manager.processing_dir, '*.rap')):
            self._move_file_to_directory(file_in_processing, self.settings_manager.psn_rap_dir, "RAP")
    
    def _move_pkg_files(self):
        """Move PKG files (and split parts) from processing_dir to PSN PKG directory."""
        for file_in_processing in glob.glob(os.path.join(self.settings_manager.processing_dir, '*.pkg*')):
            self._move_file_to_directory(file_in_processing, self.settings_manager.psn_pkg_dir, "PKG")
    
    def _move_rap_files_with_organization(self, final_target_dir, organize_content, queue_position):
        """Move RAP files from processing_dir to target directory with organization support."""
        for file_in_processing in glob.glob(os.path.join(self.settings_manager.processing_dir, '*.rap')):
            if organize_content:
                self._move_content_to_game_folder(file_in_processing, final_target_dir, queue_position, is_directory=False)
            else:
                self._move_file_to_directory(file_in_processing, final_target_dir, queue_position)
    
    def _move_pkg_files_with_organization(self, final_target_dir, organize_content, queue_position):
        """Move PKG files (and split parts) from processing_dir to target directory with organization support."""
        for file_in_processing in glob.glob(os.path.join(self.settings_manager.processing_dir, '*.pkg*')):
            if organize_content:
                self._move_content_to_game_folder(file_in_processing, final_target_dir, queue_position, is_directory=False)
            else:
                self._move_file_to_directory(file_in_processing, final_target_dir, queue_position)
    
    def _move_content_to_game_folder(self, source_path, target_dir, queue_position, is_directory=False):
        """Move content to the target directory, handling both files and directories."""
        try:
            source_name = os.path.basename(source_path)
            target_path = os.path.join(target_dir, source_name)
            
            # Ensure target directory exists
            os.makedirs(target_dir, exist_ok=True)
            
            # Remove existing target if it exists
            if os.path.exists(target_path):
                if os.path.isdir(target_path):
                    self.output_window.append(f"({queue_position}) Target directory {target_path} already exists. Removing before move.")
                    try:
                        shutil.rmtree(target_path)
                    except Exception as e_rm:
                        self.output_window.append(f"({queue_position}) Failed to remove existing target directory {target_path}: {e_rm}. Move may fail.")
                else:
                    self.output_window.append(f"({queue_position}) Target file {target_path} already exists. Removing before move.")
                    try:
                        os.remove(target_path)
                    except Exception as e_rm:
                        self.output_window.append(f"({queue_position}) Failed to remove existing target file {target_path}: {e_rm}. Move may fail.")
            
            # Move the content
            if os.path.exists(source_path):
                try:
                    shutil.move(source_path, target_path)
                    content_type = "directory" if is_directory else "file"
                    self.output_window.append(f"({queue_position}) Moved {content_type} '{source_name}' to game folder")
                except Exception as e_mv:
                    self.output_window.append(f"({queue_position}) Error moving {source_path} to {target_path}: {e_mv}")
            
        except Exception as e:
            self.output_window.append(f"({queue_position}) Error in _move_content_to_game_folder: {e}")

    def _move_directory_structure(self, source_dir, target_dir, queue_position):
        """Move a directory structure using traditional method (preserve structure)."""
        try:
            target_path = os.path.join(target_dir, os.path.basename(source_dir))
            if os.path.exists(target_path):
                self.output_window.append(f"({queue_position}) Target directory {target_path} already exists. Removing before move.")
                try:
                    shutil.rmtree(target_path)
                except Exception as e_rm:
                    self.output_window.append(f"({queue_position}) Failed to remove existing target directory {target_path}: {e_rm}. Move may fail.")
            
            try:
                shutil.move(source_dir, target_path)
                self.output_window.append(f"({queue_position}) Moved directory structure {os.path.basename(source_dir)} to {target_dir}")
            except Exception as e_mv:
                self.output_window.append(f"({queue_position}) Error moving directory {source_dir} to {target_path}: {e_mv}")
        except Exception as e:
            self.output_window.append(f"({queue_position}) Error in _move_directory_structure: {e}")

    def _move_individual_file(self, source_file, target_dir, queue_position, settings, organize_content):
        """Move an individual file, handling splitting if needed."""
        try:
            # Handle splitting for .iso files
            if source_file.endswith('.iso') and settings.get('split_large_files') and os.path.getsize(source_file) >= 4294967295:
                self.status_updated.emit("SPLITTING")
                self.output_window.append(f"({queue_position}) Splitting ISO {os.path.basename(source_file)}...")
                split_success = self.split_iso(source_file)
                
                if split_success:
                    original_iso_base_name = os.path.splitext(os.path.basename(source_file))[0]
                    split_parts_glob = os.path.join(self.settings_manager.processing_dir, original_iso_base_name + '*.iso.*')
                    
                    for split_part_path in glob.glob(split_parts_glob):
                        if organize_content:
                            self._move_content_to_game_folder(split_part_path, target_dir, queue_position, is_directory=False)
                        else:
                            self._move_file_to_directory(split_part_path, target_dir, queue_position)
                    
                    if os.path.exists(source_file):
                        if not settings.get('keep_unsplit_file'):
                            os.remove(source_file)
                        else:
                            if organize_content:
                                self._move_content_to_game_folder(source_file, target_dir, queue_position, is_directory=False)
                            else:
                                self._move_file_to_directory(source_file, target_dir, queue_position)
                else:
                    # Splitting failed, move original
                    if organize_content:
                        self._move_content_to_game_folder(source_file, target_dir, queue_position, is_directory=False)
                    else:
                        self._move_file_to_directory(source_file, target_dir, queue_position)
            else:
                # Regular file move
                if organize_content:
                    self._move_content_to_game_folder(source_file, target_dir, queue_position, is_directory=False)
                else:
                    self._move_file_to_directory(source_file, target_dir, queue_position)
        except Exception as e:
            self.output_window.append(f"({queue_position}) Error in _move_individual_file: {e}")

    def _cleanup_empty_directories_in_processing(self, queue_position):
        """Remove any empty directories left in processing_dir after moving files."""
        try:
            for root, dirs, files in os.walk(self.settings_manager.processing_dir, topdown=False):
                # Skip the processing_dir itself
                if root == self.settings_manager.processing_dir:
                    continue
                    
                # Try to remove empty directories
                if not files and not dirs:
                    try:
                        os.rmdir(root)
                        self.output_window.append(f"({queue_position}) Cleaned up empty directory: {os.path.relpath(root, self.settings_manager.processing_dir)}")
                    except OSError as e:
                        # Directory might not be empty due to hidden files or permissions
                        pass
        except Exception as e:
            self.output_window.append(f"({queue_position}) Warning: Error during directory cleanup: {e}")

    def clear_current_operation(self):
        """Clear current operation state."""
        self.current_operation = None
        self.current_file_path = None