import os
import platform
from PyQt5.QtCore import QEventLoop
from threads.processing_threads import CommandRunner, SplitPkgThread
from core.file_processor_base import FileProcessorBase

class PS3FileProcessor(FileProcessorBase):
    """Handles PS3-specific file processing operations like decrypting ISOs and splitting PKGs."""
    
    def decrypt_iso(self, iso_path, key):
        """Decrypt a PS3 ISO file using ps3dec."""
        if platform.system() == 'Windows':
            thread_count = os.cpu_count() // 2
            command = [
                self.settings_manager.ps3dec_binary, 
                "--iso", iso_path, 
                "--dk", key, 
                "--tc", str(thread_count)
            ]
        else:
            command = [
                self.settings_manager.ps3dec_binary, 
                'd', 'key', key, 
                iso_path
            ]
            
        # Create and start the command runner
        runner = CommandRunner(command)
        
        # Connect the output signal to print so we can see ps3dec output
        runner.output_signal.connect(lambda text: print(text))
        runner.error_signal.connect(lambda text: print(f"ERROR: {text}"))
        
        # Create an event loop to wait for the command to complete
        loop = QEventLoop()
        runner.finished_signal.connect(loop.quit)
        
        # Start the command and wait for completion
        runner.start()
        
        try:
            # Wait for the command to finish
            loop.exec_()
            
            # Make sure the decrypted file exists before renaming
            if platform.system() == 'Windows':
                dec_path = f"{os.path.splitext(iso_path)[0]}.iso_decrypted.iso"
            else:
                dec_path = f"{iso_path}.dec"
                
            if not os.path.exists(dec_path):
                print(f"Warning: Decryption may have failed, decrypted file not found at {dec_path}")
                return iso_path
            
            # Rename the original ISO file to .iso.enc
            enc_path = f"{iso_path}.enc"
            os.rename(iso_path, enc_path)
            
            # Rename the decrypted file
            os.rename(dec_path, iso_path)
            
            return enc_path
        except Exception as e:
            print(f"Error in decrypt_iso: {str(e)}")
            # If there's an error, return the original path so downstream code has something to work with
            return iso_path
    
    def split_pkg(self, pkg_path):
        """Split a PS3 PKG file for FAT32 filesystems."""
        if os.path.getsize(pkg_path) < 4294967295:
            print(f"File {pkg_path} is smaller than 4GB. Skipping split.")
            return False
            
        split_pkg_thread = SplitPkgThread(pkg_path)
        split_pkg_thread.progress.connect(self.print_progress)
        split_pkg_thread.start()
        split_pkg_thread.wait()
        
        return True
    
    # No need to override split_iso anymore as we're using the base class implementation
