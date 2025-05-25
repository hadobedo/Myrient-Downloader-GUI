import os
import shutil
import platform
import urllib.request
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
        self.processing_dir = 'processing'
        
        # Create directories
        self.create_directories()
        
        # Check ps3dec binary
        self.check_ps3dec_binary()
    
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
            urllib.request.urlretrieve(
                "https://github.com/Redrrx/ps3dec/releases/download/0.1.0/ps3dec.exe", 
                "ps3dec.exe"
            )
            self.ps3dec_binary = os.path.join(os.getcwd(), "ps3dec.exe")
            self.settings.setValue('ps3dec_binary', self.ps3dec_binary)
            return True
        return False
    
    def update_setting(self, key, value):
        """Update a setting and save it."""
        self.settings.setValue(key, value)
        
        # Update instance variables
        if key == 'ps3dec_binary':
            self.ps3dec_binary = value
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
