from core.file_processor_base import FileProcessorBase
from core.ps3_fileprocessor import PS3FileProcessor
import os
import subprocess

class ProcessorFactory:
    """Factory for creating the appropriate file processor."""
    
    @staticmethod
    def create_processor(platform_id, settings_manager, output_window, progress_bar):
        """Create and return the appropriate processor for the given platform."""
        if platform_id == 'ps3' or platform_id == 'psn':
            return PS3FileProcessor(settings_manager, output_window, progress_bar)
        else:
            return FileProcessorBase(settings_manager, output_window, progress_bar)

class PS3Processor:
    """Processor for PS3 ISO files."""
    
    def __init__(self, settings_manager, output_window, progress_bar):
        self.settings_manager = settings_manager
        self.output_window = output_window
        self.progress_bar = progress_bar
    
    def extract_iso(self, iso_path):
        """Extract PS3 ISO contents."""
        try:
            # Get the binary path from settings
            extractps3iso_binary = self.settings_manager.extractps3iso_binary
            
            if not extractps3iso_binary or not os.path.isfile(extractps3iso_binary):
                self.output_window.append("Error: extractps3iso binary not found.")
                return False, None
            
            # Create extract directory
            extract_dir = iso_path.rsplit('.', 1)[0]
            os.makedirs(extract_dir, exist_ok=True)
            
            # Build command
            cmd = [extractps3iso_binary, iso_path, extract_dir]
            
            # Run command
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            # Monitor output
            for line in process.stdout:
                self.output_window.append(line.strip())
            
            # Wait for process to complete
            process.wait()
            
            # Check if extraction was successful
            if process.returncode == 0:
                return True, extract_dir
            else:
                self.output_window.append(f"Error: extractps3iso exited with code {process.returncode}")
                return False, None
                
        except Exception as e:
            self.output_window.append(f"Error extracting ISO: {str(e)}")
            return False, None
