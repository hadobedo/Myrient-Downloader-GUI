import os
import shutil
import platform
import urllib.request
import zipfile
import tempfile
from PyQt5.QtCore import QSettings

class SettingsManager:
    """Manages application settings and configuration."""
    
    def __init__(self, config_manager=None):
        self.settings = QSettings('./myrientDownloaderGUI.ini', QSettings.IniFormat)
        
        # Store config_manager if provided
        self.config_manager = config_manager
        
        # Load settings with defaults
        self.ps3dec_binary = self.settings.value('ps3dec_binary', '')
        self.ps3iso_dir = self.settings.value('ps3iso_dir', 'MyrientDownloads/PS3ISO')
        self.psn_pkg_dir = self.settings.value('psn_pkg_dir', 'MyrientDownloads/packages')
        self.psn_rap_dir = self.settings.value('psn_rap_dir', 'MyrientDownloads/exdata')
        self.ps2iso_dir = self.settings.value('ps2iso_dir', 'MyrientDownloads/PS2ISO')
        self.psxiso_dir = self.settings.value('psxiso_dir', 'MyrientDownloads/PSXISO')
        self.pspiso_dir = self.settings.value('pspiso_dir', 'MyrientDownloads/PSPISO')
        
        # Determine the base MyrientDownloads directory from existing paths
        self.myrient_base_dir = self._determine_base_dir()
        
        # Set processing directory inside MyrientDownloads
        self.processing_dir = self.settings.value('processing_dir', 
                                               os.path.join(self.myrient_base_dir, 'processing'))
        
        # Load checkbox settings with defaults
        self.decrypt_iso = self._load_bool_setting('decrypt_iso', True)
        self.split_large_files = self._load_bool_setting('split_large_files', True)
        self.keep_encrypted_iso = self._load_bool_setting('keep_encrypted_iso', False)
        self.keep_dkey_file = self._load_bool_setting('keep_dkey_file', False)
        self.keep_unsplit_file = self._load_bool_setting('keep_unsplit_file', False)
        self.split_pkg = self._load_bool_setting('split_pkg', True)
        self.extract_ps3_iso = self._load_bool_setting('extract_ps3_iso', False)  # New setting, default to False
        self.keep_decrypted_iso_after_extraction = self._load_bool_setting('keep_decrypted_iso_after_extraction', True)  # New setting
        
        # Load binary paths
        self.extractps3iso_binary = self.settings.value('extractps3iso_binary', '')
        
        # Create directories
        self.create_directories()
        
        # Check binaries
        self.check_ps3dec_binary()
        self.check_extractps3iso_binary()
    
    def _determine_base_dir(self):
        """Determine the base MyrientDownloads directory from existing paths."""
        # Check if paths like ps3iso_dir have a common parent directory
        dirs = [
            self.ps3iso_dir,
            self.ps2iso_dir,
            self.psxiso_dir,
            self.pspiso_dir,
            self.psn_pkg_dir
        ]
        
        # Filter out paths that don't exist yet or are absolute
        existing_dirs = [d for d in dirs if d and not os.path.isabs(d)]
        
        if existing_dirs:
            # Look for common parent directory 'MyrientDownloads'
            for path in existing_dirs:
                parts = path.split(os.sep)
                if 'MyrientDownloads' in parts:
                    # Found a path with MyrientDownloads, use it as base
                    return os.path.join(*parts[:parts.index('MyrientDownloads')+1])
                
            # If no directory contains 'MyrientDownloads', use parent of first existing dir
            base_dir = os.path.dirname(existing_dirs[0])
            if base_dir:
                return base_dir
        
        # Default to MyrientDownloads in current directory
        return 'MyrientDownloads'
    
    def _load_bool_setting(self, key, default):
        """Load a boolean setting with proper type conversion."""
        value = self.settings.value(f"Checkboxes/{key}", default)
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
        return bool(value) if value is not None else default
    
    def create_directories(self):
        """Create all necessary directories if they don't exist."""
        # Create standard directories
        os.makedirs(self.ps3iso_dir, exist_ok=True)
        os.makedirs(self.psn_pkg_dir, exist_ok=True)
        os.makedirs(self.psn_rap_dir, exist_ok=True)
        os.makedirs(self.ps2iso_dir, exist_ok=True)
        os.makedirs(self.psxiso_dir, exist_ok=True)
        os.makedirs(self.pspiso_dir, exist_ok=True)
        os.makedirs(self.processing_dir, exist_ok=True)
        
        # Create directories for additional platforms from config
        if self.config_manager is None:
            # Only import and create a new ConfigManager if one wasn't provided
            from core.config_manager import ConfigManager
            self.config_manager = ConfigManager()
            
        for platform_id in self.config_manager.get_platforms().keys():
            if platform_id not in ['ps3', 'ps2', 'psx', 'psp', 'psn']:
                # Use the current value from settings if available, else default
                platform_dir = f'MyrientDownloads/{platform_id.upper()}'
                dir_path = self.settings.value(f'{platform_id}_dir', platform_dir)
                setattr(self, f'{platform_id}_dir', dir_path)
                os.makedirs(dir_path, exist_ok=True)
    
    def check_ps3dec_binary(self):
        """Check if ps3dec binary exists and is valid."""
        if not os.path.isfile(self.ps3dec_binary):
            self.ps3dec_binary = ''
            self.settings.setValue('ps3dec_binary', '')

        # Check if ps3dec is in PATH
        ps3dec_in_path = shutil.which("ps3dec") or shutil.which("PS3Dec") or shutil.which("ps3dec.exe") or shutil.which("PS3Dec.exe")
        
        if ps3dec_in_path:
            self.ps3dec_binary = ps3dec_in_path
            self.settings.setValue('ps3dec_binary', self.ps3dec_binary)
    
    def check_extractps3iso_binary(self):
        """Check if extractps3iso binary exists and is valid."""
        if not os.path.isfile(self.extractps3iso_binary):
            self.extractps3iso_binary = ''
            self.settings.setValue('extractps3iso_binary', '')
        
        # Binary name based on platform
        binary_name = "extractps3iso.exe" if platform.system() == 'Windows' else "extractps3iso"
        
        # Check if extractps3iso is in PATH
        extractps3iso_in_path = shutil.which("extractps3iso") or shutil.which("extractps3iso.exe")
        
        if extractps3iso_in_path:
            self.extractps3iso_binary = extractps3iso_in_path
            self.settings.setValue('extractps3iso_binary', self.extractps3iso_binary)
        else:
            # Check if it's in the current directory
            local_binary = os.path.join(os.getcwd(), binary_name)
            if os.path.isfile(local_binary):
                self.extractps3iso_binary = local_binary
                self.settings.setValue('extractps3iso_binary', self.extractps3iso_binary)
    
    def is_valid_binary(self, path, binary_name):
        """Check if the path points to a valid binary."""
        if path and os.path.isfile(path):
            filename = os.path.basename(path)
            if platform.system() == 'Windows':
                return filename.lower() == f"{binary_name}.exe"
            else:
                return filename.lower() == binary_name.lower()
        return False
    
    def download_ps3dec(self):
        """Download the PS3Dec binary (Windows only)."""
        if platform.system() == 'Windows':
            try:
                print("Downloading PS3Dec from GitHub...")
                urllib.request.urlretrieve(
                    "https://github.com/Redrrx/ps3dec/releases/download/0.1.0/ps3dec.exe", 
                    "ps3dec.exe"
                )
                self.ps3dec_binary = os.path.join(os.getcwd(), "ps3dec.exe")
                self.settings.setValue('ps3dec_binary', self.ps3dec_binary)
                print("PS3Dec downloaded successfully")
                return True
            except Exception as e:
                print(f"Error downloading PS3Dec: {str(e)}")
                return False
        return False
        
    def download_extractps3iso(self):
        """Download the extractps3iso binary."""
        if platform.system() == 'Windows':
            try:
                print("Downloading extractps3iso from GitHub...")
                
                # Create a temporary file to store the ZIP
                with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
                    temp_path = temp_file.name
                
                # Download the ZIP file
                urllib.request.urlretrieve(
                    "https://github.com/bucanero/ps3iso-utils/releases/download/277db7de/ps3iso-277db7de-Win64.zip",
                    temp_path
                )
                
                # Extract the ZIP file
                with zipfile.ZipFile(temp_path, 'r') as zip_ref:
                    # Extract only the extractps3iso.exe file
                    for file in zip_ref.namelist():
                        if file.lower().endswith('extractps3iso.exe'):
                            source = zip_ref.open(file)
                            target = open(os.path.join(os.getcwd(), "extractps3iso.exe"), "wb")
                            with source, target:
                                shutil.copyfileobj(source, target)
                            break
                
                # Delete the temporary ZIP file
                os.unlink(temp_path)
                
                # Update the binary path
                self.extractps3iso_binary = os.path.join(os.getcwd(), "extractps3iso.exe")
                self.settings.setValue('extractps3iso_binary', self.extractps3iso_binary)
                
                print("extractps3iso downloaded and extracted successfully")
                return True
            except Exception as e:
                print(f"Error downloading extractps3iso: {str(e)}")
                return False
        else:
            # For Linux/macOS, we can't easily download and install
            # Should suggest to the user to install it manually
            print("On Linux/macOS, please install extractps3iso manually")
            return False
    
    def update_setting(self, key, value):
        """Update a setting and save it."""
        # Check if this is a checkbox setting
        checkbox_settings = {
            'decrypt_iso', 'split_large_files', 'keep_encrypted_iso', 
            'keep_dkey_file', 'keep_unsplit_file', 'split_pkg', 'extract_ps3_iso',
            'keep_decrypted_iso_after_extraction'  # Added new setting
        }
        
        if key in checkbox_settings:
            # Save checkbox settings to the Checkboxes section
            self.settings.setValue(f"Checkboxes/{key}", value)
        else:
            # Save other settings to the General section
            self.settings.setValue(key, value)
        
        # Update instance variables
        if key == 'ps3dec_binary':
            self.ps3dec_binary = value
        elif key == 'extractps3iso_binary':
            self.extractps3iso_binary = value
        elif key == 'ps3iso_dir':
            self.ps3iso_dir = value
        elif key == 'psn_pkg_dir':
            self.psn_pkg_dir = value
        elif key == 'psn_rap_dir':
            self.psn_rap_dir = value
        elif key == 'ps2iso_dir':
            self.ps2iso_dir = value
        elif key == 'psxiso_dir':
            self.psxiso_dir = value
        elif key == 'pspiso_dir':
            self.pspiso_dir = value
        elif key == 'processing_dir':
            self.processing_dir = value
        elif key == 'decrypt_iso':
            self.decrypt_iso = value
        elif key == 'split_large_files':
            self.split_large_files = value
        elif key == 'keep_encrypted_iso':
            self.keep_encrypted_iso = value
        elif key == 'keep_dkey_file':
            self.keep_dkey_file = value
        elif key == 'keep_unsplit_file':
            self.keep_unsplit_file = value
        elif key == 'split_pkg':
            self.split_pkg = value
        elif key == 'extract_ps3_iso':
            self.extract_ps3_iso = value
        elif key == 'keep_decrypted_iso_after_extraction':
            self.keep_decrypted_iso_after_extraction = value
