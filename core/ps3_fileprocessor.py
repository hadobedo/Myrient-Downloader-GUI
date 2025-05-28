import os
import platform
import subprocess
import shutil
import sys
import tempfile
from PyQt5.QtCore import QEventLoop
from threads.processing_threads import CommandRunner, SplitPkgThread
class PS3FileProcessor:
    """Handles PS3-specific file processing operations like decrypting ISOs and splitting PKGs."""
    
    def __init__(self, settings_manager, output_window, parent=None):
        """Initialize PS3FileProcessor with required dependencies."""
        self.settings_manager = settings_manager
        self.output_window = output_window
        self.parent = parent
        self.progress_callback = None
        
    def set_progress_callback(self, callback):
        """Set a callback function for progress updates."""
        self.progress_callback = callback
    
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
        
        # Connect the output signal to output_window for proper formatting
        runner.output_signal.connect(lambda text: self.output_window.append(text))
        runner.error_signal.connect(lambda text: self.output_window.append(f"ERROR: {text}"))
        
        # Connect progress if callback is available
        if self.progress_callback:
            runner.output_signal.connect(self._parse_progress_from_output)
        
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
                self.output_window.append(f"Warning: Decryption may have failed, decrypted file not found at {dec_path}")
                return iso_path
            
            # Rename the original ISO file to .iso.enc
            enc_path = f"{iso_path}.enc"
            os.rename(iso_path, enc_path)
            
            # Rename the decrypted file
            os.rename(dec_path, iso_path)
            
            return enc_path
        except Exception as e:
            self.output_window.append(f"Error in decrypt_iso: {str(e)}")
            # If there's an error, return the original path so downstream code has something to work with
            return iso_path
    
    def split_pkg(self, pkg_path):
        """Split a PS3 PKG file for FAT32 filesystems."""
        if os.path.getsize(pkg_path) < 4294967295:
            self.output_window.append(f"File {pkg_path} is smaller than 4GB. Skipping split.")
            return False
            
        split_pkg_thread = SplitPkgThread(pkg_path)
        split_pkg_thread.progress.connect(self._print_progress)
        if self.progress_callback:
            split_pkg_thread.progress.connect(lambda text: self._parse_split_progress(text))
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
                self.output_window.append("extractps3iso tool not found. Please install it.")
                return (False, expected_extraction_dir)

            self.output_window.append(f"Extracting PS3 ISO using extractps3iso: {iso_path}")
            
            # Run the extractps3iso command - extract to parent directory
            # Let extractps3iso create the folder structure naturally
            cmd = [extract_tool, iso_path, parent_dir]
            
            if self.progress_callback:
                # Start extraction with progress tracking
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # Monitor output for progress
                output_lines = []
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        output_lines.append(output.strip())
                        self._parse_extraction_progress(output.strip())
                
                # Get any remaining output
                stdout, stderr = process.communicate()
                if stdout:
                    output_lines.extend(stdout.strip().split('\n'))
                    
                # Combine all output
                process.stdout = '\n'.join(output_lines)
                process.stderr = stderr
                process.returncode = process.poll()
            else:
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False
                )
            
            # Check if the extraction was successful
            if process.returncode != 0:
                self.output_window.append(f"extractps3iso failed with return code {process.returncode}:")
                self.output_window.append(process.stderr)
                return (False, expected_extraction_dir)

            # Log the output
            self.output_window.append(process.stdout)
            
            # Check if extraction actually produced files in the expected directory
            if os.path.exists(expected_extraction_dir) and any(os.scandir(expected_extraction_dir)):
                self.output_window.append(f"Successfully extracted PS3 ISO to {expected_extraction_dir}")
                return (True, expected_extraction_dir)
            else:
                # Look for any directory that was created by extractps3iso
                potential_dirs = [d for d in os.listdir(parent_dir) 
                               if os.path.isdir(os.path.join(parent_dir, d)) and 
                               (d.startswith(base_name) or base_name.lower() in d.lower())]
                
                if potential_dirs:
                    actual_dir = os.path.join(parent_dir, potential_dirs[0])
                    self.output_window.append(f"Found extraction at {actual_dir}")
                    return (True, actual_dir)

                self.output_window.append("extractps3iso didn't extract any files.")
                return (False, expected_extraction_dir)
                
        except Exception as e:
            self.output_window.append(f"Error extracting ISO: {str(e)}")
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
    
    def _print_progress(self, text):
        """Print progress updates."""
        self.output_window.append(text)
    
    def _parse_progress_from_output(self, text):
        """Parse progress information from ps3dec output."""
        if self.progress_callback:
            # ps3dec typically shows progress as percentages
            # Look for patterns like "Progress: 50%" or similar
            import re
            
            # Common progress patterns in ps3dec output
            progress_patterns = [
                r'(\d+)%',
                r'Progress:\s*(\d+)%',
                r'(\d+)/(\d+)',
                r'Decrypting.*?(\d+)%'
            ]
            
            for pattern in progress_patterns:
                match = re.search(pattern, text)
                if match:
                    try:
                        if len(match.groups()) == 1:
                            # Simple percentage
                            progress = int(match.group(1))
                            if 0 <= progress <= 100:
                                self.progress_callback(progress)
                                break
                        elif len(match.groups()) == 2:
                            # Fraction format like "50/100"
                            current = int(match.group(1))
                            total = int(match.group(2))
                            if total > 0:
                                progress = int((current / total) * 100)
                                if 0 <= progress <= 100:
                                    self.progress_callback(progress)
                                    break
                    except (ValueError, ZeroDivisionError):
                        continue
    
    def _parse_split_progress(self, text):
        """Parse progress information from split operations."""
        if self.progress_callback:
            import re
            
            # Look for split progress patterns like "Splitting file: part 1/5 complete"
            progress_patterns = [
                r'part\s+(\d+)/(\d+)\s+complete',
                r'(\d+)/(\d+)\s+complete',
                r'Splitting.*?(\d+)%'
            ]
            
            for pattern in progress_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        if len(match.groups()) == 2:
                            # Fraction format like "part 1/5"
                            current = int(match.group(1))
                            total = int(match.group(2))
                            if total > 0:
                                progress = int((current / total) * 100)
                                if 0 <= progress <= 100:
                                    self.progress_callback(progress)
                                    break
                        elif len(match.groups()) == 1:
                            # Simple percentage
                            progress = int(match.group(1))
                            if 0 <= progress <= 100:
                                self.progress_callback(progress)
                                break
                    except (ValueError, ZeroDivisionError):
                        continue
   
    def _parse_extraction_progress(self, text):
        """Parse progress information from extractps3iso output."""
        if self.progress_callback:
            import re
            
            # Look for extraction progress patterns
            # extractps3iso might show file counts or percentages
            progress_patterns = [
                r'(\d+)%',
                r'(\d+)/(\d+)\s+files',
                r'Extracting.*?(\d+)%',
                r'(\d+)\s+of\s+(\d+)'
            ]
            
            for pattern in progress_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        if len(match.groups()) == 1:
                            # Simple percentage
                            progress = int(match.group(1))
                            if 0 <= progress <= 100:
                                self.progress_callback(progress)
                                break
                        elif len(match.groups()) == 2:
                            # Fraction format
                            current = int(match.group(1))
                            total = int(match.group(2))
                            if total > 0:
                                progress = int((current / total) * 100)
                                if 0 <= progress <= 100:
                                    self.progress_callback(progress)
                                    break
                    except (ValueError, ZeroDivisionError):
                        continue
