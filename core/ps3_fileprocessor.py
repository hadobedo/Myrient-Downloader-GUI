import os
import platform
import subprocess
import shutil
import sys
import tempfile
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
    
    def extract_iso(self, iso_path):
        """
        Extract contents of a PS3 ISO to a folder with the same name using extractps3iso tool.
        Returns a tuple of (success, extraction_path)
        """
        # Get the base name for the folder (remove extension)
        base_name = os.path.splitext(os.path.basename(iso_path))[0]
        parent_dir = os.path.dirname(iso_path)
        expected_extraction_dir = os.path.join(parent_dir, base_name)
        
        try:
            # Check if extractps3iso is available
            extract_tool = shutil.which('extractps3iso')
            
            if not extract_tool:
                print("extractps3iso tool not found. Please install it.")
                return (False, expected_extraction_dir)
            
            print(f"Extracting PS3 ISO using extractps3iso: {iso_path}")
            
            # Run the extractps3iso command - extract to parent directory
            # Let extractps3iso create the folder structure naturally
            cmd = [extract_tool, iso_path, parent_dir]
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            # Check if the extraction was successful
            if process.returncode != 0:
                print(f"extractps3iso failed with return code {process.returncode}:")
                print(process.stderr)
                return (False, expected_extraction_dir)
            
            # Log the output
            print(process.stdout)
            
            # Check if extraction actually produced files in the expected directory
            if os.path.exists(expected_extraction_dir) and any(os.scandir(expected_extraction_dir)):
                print(f"Successfully extracted PS3 ISO to {expected_extraction_dir}")
                return (True, expected_extraction_dir)
            else:
                # Look for any directory that was created by extractps3iso
                potential_dirs = [d for d in os.listdir(parent_dir) 
                               if os.path.isdir(os.path.join(parent_dir, d)) and 
                               (d.startswith(base_name) or base_name.lower() in d.lower())]
                
                if potential_dirs:
                    actual_dir = os.path.join(parent_dir, potential_dirs[0])
                    print(f"Found extraction at {actual_dir}")
                    return (True, actual_dir)
                
                print("extractps3iso didn't extract any files.")
                return (False, expected_extraction_dir)
                
        except Exception as e:
            print(f"Error extracting ISO: {str(e)}")
            return (False, expected_extraction_dir)
    
    def _format_size(self, size_bytes):
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} bytes"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.2f} KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes/1024**2:.2f} MB"
        else:
            return f"{size_bytes/1024**3:.2f} GB"
    
    def _safe_decode(self, data):
        """Safely decode binary data to string."""
        if isinstance(data, str):
            return data
        elif isinstance(data, bytes):
            try:
                return data.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    return data.decode('latin1')
                except:
                    # Last resort: replace invalid characters
                    return data.decode('utf-8', errors='replace')
        else:
            return str(data)
