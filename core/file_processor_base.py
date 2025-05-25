import os
import shutil
import glob
from PyQt5.QtCore import QEventLoop
from threads.processing_threads import UnzipRunner, SplitIsoThread

class FileProcessorBase:
    """Base class for file processors with common functionality."""
    
    def __init__(self, settings_manager, output_window, progress_bar):
        self.settings_manager = settings_manager
        self.output_window = output_window
        self.progress_bar = progress_bar
    
    def unzip_file(self, zip_path, output_path):
        """Unzip a file and return the list of extracted files."""
        self.progress_bar.reset()
        
        runner = UnzipRunner(zip_path, output_path)
        runner.progress_signal.connect(self.progress_bar.setValue)
        
        # Create an event loop to wait for the thread
        loop = QEventLoop()
        runner.finished.connect(loop.quit)
        
        runner.start()
        loop.exec_()
        
        return runner.extracted_files
    
    def print_progress(self, text):
        """Print progress updates."""
        print(text)
    
    def move_processed_files(self, base_name, source_dir, dest_dir):
        """Move processed files from source directory to destination directory."""
        for file in glob.glob(os.path.join(source_dir, base_name + '*')):
            dest_path = os.path.join(dest_dir, os.path.basename(file))
            if os.path.exists(dest_path):
                print(f"File {dest_path} already exists. Overwriting.")
            shutil.move(file, dest_path)
            
    def split_iso(self, iso_path):
        """Split an ISO file for FAT32 filesystems."""
        if os.path.getsize(iso_path) < 4294967295:
            print(f"File {iso_path} is smaller than 4GB. Skipping split.")
            return False
            
        split_iso_thread = SplitIsoThread(iso_path)
        split_iso_thread.progress.connect(self.print_progress)
        split_iso_thread.start()
        split_iso_thread.wait()
        
        return True
