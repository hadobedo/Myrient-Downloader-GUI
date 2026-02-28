import os
import shutil
import platform
import urllib.request
import zipfile
import tarfile
import tempfile
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QGroupBox, QFormLayout,
    QMessageBox, QScrollArea, QWidget, QTabWidget, QDialogButtonBox, QCheckBox
)
class UnifiedBinaryDetectionDialog(QDialog):
    """Simple unified dialog to detect and manage PS3 tools."""
    
    def __init__(self, missing_binaries, parent=None):
        super().__init__(parent)
        self.missing_binaries = missing_binaries  # List of missing binary names
        self.results = {}  # Store user choices for each binary
        self.is_windows = platform.system() == 'Windows'
        self.do_not_remind = False  # Store checkbox state
        
        self.setWindowTitle("Configure PS3 Tools")
        self.setMinimumWidth(600)
        self.setFixedHeight(180 + (len(missing_binaries) * 40))  # Increased height for checkbox
        
        self.initUI()
    
    def initUI(self):
        """Initialize the simple unified binary detection UI."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Simple explanation
        explanation = QLabel("Please configure the required PS3 tools binaries:")
        explanation.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(explanation)
        
        # Binary configuration rows
        self.binary_inputs = {}
        
        for binary in self.missing_binaries:
            binary_layout = self._create_binary_row(binary)
            layout.addLayout(binary_layout)
        
        # Add "Do not remind me" checkbox
        self.do_not_remind_checkbox = QCheckBox("Do not remind me about missing binaries")
        self.do_not_remind_checkbox.setStyleSheet("margin-top: 10px; margin-bottom: 5px;")
        layout.addWidget(self.do_not_remind_checkbox)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # Skip button
        skip_btn = QPushButton("Skip")
        skip_btn.clicked.connect(self._skip_setup)
        button_layout.addWidget(skip_btn)
        
        # OK button
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def _create_binary_row(self, binary):
        """Create a simple row for a specific binary."""
        layout = QHBoxLayout()
        
        # Binary label
        if binary == "ps3dec":
            label_text = "PS3Dec binary:"
        elif binary == "extractps3iso":
            label_text = "extractps3iso binary:"
        else:
            label_text = f"{binary} binary:"
        
        label = QLabel(label_text)
        label.setMinimumWidth(150)
        layout.addWidget(label)
        
        # Path input box
        path_input = QLineEdit()
        path_input.setPlaceholderText("Path to binary...")
        layout.addWidget(path_input)
        self.binary_inputs[binary] = path_input
        
        # Browse button
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(lambda: self._browse_binary(binary))
        layout.addWidget(browse_btn)
        
        # Download button (Windows only)
        if self.is_windows:
            download_btn = QPushButton("Download")
            download_btn.setFixedWidth(70)
            download_btn.clicked.connect(lambda: self._download_binary(binary))
            layout.addWidget(download_btn)
        
        return layout
    
    def _browse_binary(self, binary):
        """Browse for a specific binary."""
        title = f"Select {binary} executable"
        file_filter = "All Files (*)" if os.name == 'posix' else "Executables (*.exe);;All Files (*)"
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, title, os.path.expanduser("~"), file_filter
        )
        
        if file_path and os.path.isfile(file_path):
            # Update the input field
            self.binary_inputs[binary].setText(file_path)
            self._configure_binary(binary, file_path, "manually located")
    
    def _download_binary(self, binary):
        """Download a specific binary."""
        if not self.is_windows:
            return
        
        # Get settings manager
        settings_manager = None
        if hasattr(self.parent(), 'settings_manager'):
            settings_manager = self.parent().settings_manager
        else:
            from core.settings import SettingsManager
            settings_manager = SettingsManager()
        
        success = False
        if binary == "ps3dec":
            success = settings_manager.download_ps3dec()
        elif binary == "extractps3iso":
            success = settings_manager.download_extractps3iso()
        
        if success:
            # Get the path that was set by the download
            binary_path = getattr(settings_manager, f"{binary}_binary", "")
            self.binary_inputs[binary].setText(binary_path)
            self._configure_binary(binary, binary_path, "downloaded")
        else:
            self._show_error(f"Failed to download {binary}",
                           "Please check your internet connection and try again.")
    
    def _configure_binary(self, binary, path, source):
        """Configure a binary with the given path."""
        if not path or not os.path.isfile(path):
            return
        
        # Update settings
        settings_manager = None
        if hasattr(self.parent(), 'settings_manager'):
            settings_manager = self.parent().settings_manager
        else:
            from core.settings import SettingsManager
            settings_manager = SettingsManager()
        
        settings_manager.update_setting(f"{binary}_binary", path)
        
        # Store result
        self.results[binary] = {
            'path': path,
            'source': source,
            'configured': True
        }
    def accept(self):
        """Handle OK button - process any manually entered paths."""
        # Save the "do not remind me" setting
        self.do_not_remind = self.do_not_remind_checkbox.isChecked()
        self._save_do_not_remind_setting()
        
        # Check for manually entered paths
        for binary, input_widget in self.binary_inputs.items():
            path = input_widget.text().strip()
            if path and os.path.isfile(path):
                self._configure_binary(binary, path, "manually entered")
            elif binary not in self.results:
                # No path provided and not already configured
                self.results[binary] = {
                    'path': '',
                    'source': 'skipped',
                    'configured': False
                }
        
        super().accept()
    
    def _skip_setup(self):
        """Skip the binary setup."""
        # Save the "do not remind me" setting
        self.do_not_remind = self.do_not_remind_checkbox.isChecked()
        self._save_do_not_remind_setting()
        
        for binary in self.missing_binaries:
            self.results[binary] = {
                'path': '',
                'source': 'skipped',
                'configured': False
            }
        self.accept()
    
    def _save_do_not_remind_setting(self):
        """Save the 'do not remind me' setting to the INI file."""
        try:
            # Get settings manager
            settings_manager = None
            if hasattr(self.parent(), 'settings_manager'):
                settings_manager = self.parent().settings_manager
            else:
                from core.settings import SettingsManager
                settings_manager = SettingsManager()
            
            # Save the setting
            settings_manager.settings.setValue('notifications/do_not_remind_missing_binaries', self.do_not_remind)
            settings_manager.settings.sync()
        except Exception as e:
            print(f"Warning: Could not save 'do not remind me' setting: {str(e)}")
    
    def _show_error(self, title, message):
        """Show an error message."""
        try:
            from myrientDownloaderGUI import show_styled_message_box
            show_styled_message_box(QMessageBox.Critical, title, message, self)
        except ImportError:
            QMessageBox.critical(self, title, message)


class BinaryValidationDialog(QDialog):
    """Legacy dialog for backward compatibility."""
    
    def __init__(self, binary_type, parent=None):
        super().__init__(parent)
        self.binary_type = binary_type
        
        # Configure dialog based on binary type
        if binary_type == "ps3dec":
            self.setWindowTitle("PS3Dec Required")
            message_text = (
                "PS3Dec is required to decrypt PS3 ISOs.\n\n"
                "This tool was not found on your system. Would you like to download it now?\n\n"
                "Note: The download is approximately 233KB and will be saved to the application directory."
            )
        elif binary_type == "extractps3iso":
            self.setWindowTitle("extractps3iso Required")
            message_text = (
                "extractps3iso is required to extract PS3 ISO contents.\n\n"
                "This tool was not found on your system. Would you like to download it now?\n\n"
                "Note: The download is approximately 600KB and will be saved to the application directory."
            )
        else:
            self.setWindowTitle("Binary Required")
            message_text = f"The {binary_type} tool is required but was not found on your system."
        
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Add explanation text
        message = QLabel(message_text)
        message.setWordWrap(True)
        layout.addWidget(message)
        
        # Add buttons
        buttons = QDialogButtonBox()
        download_button = QPushButton(f"Download {binary_type}")
        cancel_button = QPushButton("Cancel")
        
        buttons.addButton(download_button, QDialogButtonBox.AcceptRole)
        buttons.addButton(cancel_button, QDialogButtonBox.RejectRole)
        
        layout.addWidget(buttons)
        self.setLayout(layout)
        
        # Connect signals
        download_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        cancel_button.clicked.connect(self.reject)

class BinaryValidationManager:
    """Manages unified startup validation for PS3 binaries across all operating systems."""
    
    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
    
    def validate_startup_binaries(self, parent_widget=None):
        """
        Perform unified startup validation for PS3Dec and extractps3iso.
        Shows a consolidated dialog for missing binaries on all operating systems.
        Returns True to continue application startup.
        """
        missing_binaries = []
        
        # Check PS3Dec
        if not self._is_binary_available('ps3dec'):
            missing_binaries.append('ps3dec')
        
        # Check extractps3iso
        if not self._is_binary_available('extractps3iso'):
            missing_binaries.append('extractps3iso')
        
        # If no missing binaries, continue normally
        if not missing_binaries:
            return True
        
        # Check if user has chosen not to be reminded about missing binaries
        do_not_remind = self.settings_manager.settings.value('notifications/do_not_remind_missing_binaries', False)
        if isinstance(do_not_remind, str):
            do_not_remind = do_not_remind.lower() in ('true', 'yes', '1', 'on')
        
        if do_not_remind:
            # User doesn't want to be reminded, skip the dialog
            return True
        
        # Show unified binary detection dialog
        dialog = UnifiedBinaryDetectionDialog(missing_binaries, parent_widget)
        
        # Apply theme styling if needed
        try:
            from myrientDownloaderGUI import style_dialog_for_theme
            style_dialog_for_theme(dialog)
        except ImportError:
            pass  # No styling available
        
        result = dialog.exec_()
        
        # Process results and show summary
        if result == QDialog.Accepted:
            self._show_setup_summary(dialog.results, parent_widget)
        
        # Always continue application startup
        return True
    
    def _is_binary_available(self, binary_type):
        """Check if a binary is available in configuration or PATH."""
        if binary_type == 'ps3dec':
            binary_path = self.settings_manager.ps3dec_binary
            if binary_path and os.path.isfile(binary_path):
                return True
            # Check PATH
            return shutil.which("ps3dec") or shutil.which("PS3Dec") or shutil.which("ps3dec.exe") or shutil.which("PS3Dec.exe")
        
        elif binary_type == 'extractps3iso':
            binary_path = self.settings_manager.extractps3iso_binary
            if binary_path and os.path.isfile(binary_path):
                return True
            # Check PATH
            return shutil.which("extractps3iso") or shutil.which("extractps3iso.exe")
        
        return False
    
    def _show_setup_summary(self, results, parent_widget):
        """Show a summary of the binary setup results."""
        configured_count = sum(1 for r in results.values() if r.get('configured', False))
        total_count = len(results)
        
        # Show a message if any binaries are missing
        if configured_count < total_count:
            # Get the names of missing binaries
            missing_binaries = [bin_name for bin_name, result in results.items() 
                               if not result.get('configured', False)]
            
            # Format the missing binaries list
            missing_text = ""
            for binary in missing_binaries:
                binary_display_name = binary.upper() if binary == "ps3dec" else binary
                missing_text += f"• {binary_display_name}\n"
            
            # Create appropriate message based on platform
            is_windows = platform.system() == 'Windows'
            
            title = "Missing PS3 Tools"
            message = (
                f"The following PS3 tool(s) are missing or not configured:\n\n"
                f"{missing_text}\n"
                f"PS3 decryption & extraction functionality may be limited.\n\n"
            )
            
            if is_windows:
                message += "You can download these tools automatically through Settings → Binaries."
            else:
                message += "You can configure these tools through Settings → Binaries."
            
            icon = QMessageBox.Warning
            
            try:
                from myrientDownloaderGUI import show_styled_message_box
                show_styled_message_box(icon, title, message, parent_widget)
            except ImportError:
                QMessageBox.warning(parent_widget, title, message)

def get_explanation_style():
    """Get appropriate styling for explanation text based on current theme."""
    # Import here to avoid circular imports
    try:
        from myrientDownloaderGUI import is_dark_mode
        if is_dark_mode():
            return "QLabel { background-color: #404040; color: #ffffff; padding: 10px; border-radius: 5px; border: 1px solid #555555; }"
        else:
            return "QLabel { background-color: #f5f5f5; color: #2c2c2c; padding: 10px; border-radius: 5px; border: 1px solid #d0d0d0; }"
    except (ImportError, TypeError):
        # Fallback to light theme if can't determine
        return "QLabel { background-color: #f5f5f5; color: #2c2c2c; padding: 10px; border-radius: 5px; border: 1px solid #d0d0d0; }"

class DirectoryManager:
    """Manages hierarchical directory structure for Myrient downloads."""
    
    def __init__(self, settings, config_manager=None):
        self.settings = settings
        self.config_manager = config_manager
        
        # Root directory - configurable base for all downloads
        self.root_dir = self.settings.value('directories/root_dir', 'MyrientDownloads')
        
        # Processing directory - inside root download directory for better organization
        self.processing_dir = self.settings.value('directories/processing_dir', os.path.join(self.root_dir, 'processing'))
        
        # Initialize directory structure
        self._init_directory_structure()
    
    def _init_directory_structure(self):
        """Initialize the hierarchical directory structure."""
        # PlayStation 3 content
        self.ps3iso_dir = self.settings.value(
            'directories/ps3iso_dir',
            os.path.join(self.root_dir, 'PS3ISO')
        )
        
        # PlayStation 2 content
        self.ps2iso_dir = self.settings.value(
            'directories/ps2iso_dir',
            os.path.join(self.root_dir, 'PS2ISO')
        )
        
        # PlayStation 1/PSX content
        self.psxiso_dir = self.settings.value(
            'directories/psxiso_dir',
            os.path.join(self.root_dir, 'PSXISO')
        )
        
        # PlayStation Portable content
        self.pspiso_dir = self.settings.value(
            'directories/pspiso_dir',
            os.path.join(self.root_dir, 'PSPISO')
        )
        
        # PlayStation Network content - hierarchical structure
        psn_base = os.path.join(self.root_dir, 'PSN')
        self.psn_rap_dir = self.settings.value(
            'directories/psn_rap_dir',
            os.path.join(psn_base, 'exdata')
        )
        self.psn_pkg_dir = self.settings.value(
            'directories/psn_pkg_dir',
            os.path.join(psn_base, 'packages')
        )
        
        # Dynamic platform directories from configuration
        self._init_dynamic_platform_dirs()
    
    def _init_dynamic_platform_dirs(self):
        """Initialize directories for platforms defined in myrient_urls.yaml."""
        if not self.config_manager:
            return
            
        platforms = self.config_manager.get_platforms()
        for platform_id in platforms.keys():
            # Skip predefined platforms
            if platform_id in ['ps3', 'ps2', 'psx', 'psp', 'psn']:
                continue
                
            # Create dynamic directory using uppercase platform identifier
            attr_name = f"{platform_id.lower()}_dir"
            default_dir = os.path.join(self.root_dir, platform_id.upper())
            
            directory = self.settings.value(f'directories/{platform_id}_dir', default_dir)
            setattr(self, attr_name, directory)
    
    def get_platform_directory(self, platform_id):
        """Get the output directory for a specific platform."""
        # Handle Xbox 360 variants - they should use the same base directory unless specifically configured
        if platform_id in ['xbox360digital', 'xbox360tu']:
            # Check if there's a specific directory configured for this variant
            attr_name = f"{platform_id.lower()}_dir"
            if hasattr(self, attr_name):
                return getattr(self, attr_name)
            # Fall back to the main xbox360 directory
            elif hasattr(self, 'xbox360_dir'):
                return getattr(self, 'xbox360_dir')
            else:
                # Create based on the variant name
                return os.path.join(self.root_dir, platform_id.upper())
        
        # Standard platform handling
        attr_name = f"{platform_id.lower()}_dir"
        if hasattr(self, attr_name):
            return getattr(self, attr_name)
        
        # Fallback for unknown platforms
        return os.path.join(self.root_dir, platform_id.upper())
    
    def create_all_directories(self):
        """Create all configured directories."""
        directories_to_create = [
            self.root_dir,
            self.processing_dir,
            self.ps3iso_dir,
            self.ps2iso_dir,
            self.psxiso_dir,
            self.pspiso_dir,
            self.psn_rap_dir,
            self.psn_pkg_dir
        ]
        
        # Add dynamic platform directories
        if self.config_manager:
            platforms = self.config_manager.get_platforms()
            for platform_id in platforms.keys():
                if platform_id not in ['ps3', 'ps2', 'psx', 'psp', 'psn']:
                    attr_name = f"{platform_id.lower()}_dir"
                    if hasattr(self, attr_name):
                        directories_to_create.append(getattr(self, attr_name))
        
        # Create directories with error handling
        failed_dirs = []
        for directory in directories_to_create:
            if directory:  # Only create if directory path is not empty
                try:
                    os.makedirs(directory, exist_ok=True)
                except Exception as e:
                    failed_dirs.append((directory, str(e)))
        
        return failed_dirs
    
    def validate_directory_path(self, path):
        """Validate a directory path and return validation result."""
        if not path:
            return False, "Directory path cannot be empty"
        
        try:
            # Normalize the path
            normalized_path = os.path.normpath(os.path.abspath(path))
            
            # Check if we can create the directory
            os.makedirs(normalized_path, exist_ok=True)
            
            # Check if we can write to it
            test_file = os.path.join(normalized_path, '.write_test')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
            except Exception:
                return False, "Directory is not writable"
            
            return True, normalized_path
            
        except Exception as e:
            return False, f"Invalid directory path: {str(e)}"
    
    def update_directory(self, directory_type, new_path):
        """Update a directory path and save to settings."""
        valid, result = self.validate_directory_path(new_path)
        if not valid:
            raise ValueError(result)
        
        # Save to settings
        self.settings.setValue(f'directories/{directory_type}', result)
        
        # Update instance attribute
        if directory_type == 'root_dir':
            old_root = self.root_dir
            self.root_dir = result
            # Update related platform directories if they were using default structure
            self._update_platform_dirs_on_root_change(old_root, result)
        elif directory_type == 'processing_dir':
            self.processing_dir = result
        elif hasattr(self, directory_type):
            setattr(self, directory_type, result)
        return result
    
    def _update_platform_dirs_on_root_change(self, old_root, new_root):
        """Update platform directories when root directory changes."""
        if not old_root or not new_root or old_root == new_root:
            return
        
        # Define default platform directory structures
        platform_mappings = {
            'ps3iso_dir': 'PS3ISO',
            'ps2iso_dir': 'PS2ISO',
            'psxiso_dir': 'PSXISO',
            'pspiso_dir': 'PSPISO',
            'psn_pkg_dir': os.path.join('PSN', 'packages'),
            'psn_rap_dir': os.path.join('PSN', 'exdata'),
            'processing_dir': 'processing'
        }
        
        # Add dynamic platform directories
        if self.config_manager:
            platforms = self.config_manager.get_platforms()
            for platform_id in platforms.keys():
                if platform_id not in ['ps3', 'ps2', 'psx', 'psp', 'psn']:
                    attr_name = f"{platform_id.lower()}_dir"
                    platform_mappings[attr_name] = platform_id.upper()
        
        # Update directories that are using the default structure
        for attr_name, subdir in platform_mappings.items():
            if hasattr(self, attr_name):
                current_path = getattr(self, attr_name)
                
                # Check multiple possible old root paths that might be in use
                possible_old_paths = [
                    os.path.join(old_root, subdir),
                    os.path.join('MyrientDownloads', subdir),  # Default fallback
                    os.path.join('/home/nick/Myrient-Downloader-GUI/MyrientDownloads', subdir)  # Full path fallback
                ]
                
                # Check if current path matches any of the old default structures
                should_update = False
                for expected_old_path in possible_old_paths:
                    if (current_path == expected_old_path or
                        current_path == os.path.normpath(expected_old_path)):
                        should_update = True
                        break
                
                if should_update:
                    # Update to new root structure
                    new_path = os.path.join(new_root, subdir)
                    setattr(self, attr_name, new_path)
                    
                    # Update in settings - use correct key format
                    self.settings.setValue(f'directories/{attr_name}', new_path)
                    
                    # Clean up any old entries in the General section
                    try:
                        self.settings.remove(f'General/{attr_name}')
                    except Exception:
                        pass  # Ignore if the key doesn't exist

class SettingsManager:
    """Manages application settings and configuration."""
    
    def __init__(self, config_manager=None):
        self.settings = QSettings('./config/myrientDownloaderGUI.ini', QSettings.IniFormat)
        
        # Store config_manager if provided
        self.config_manager = config_manager
        
        # Initialize directory manager
        self.directory_manager = DirectoryManager(self.settings, config_manager)
        
        # Expose directory properties for backwards compatibility
        self._setup_directory_properties()
        
        # Load checkbox settings with defaults
        self.decrypt_iso = self._load_bool_setting('decrypt_iso', True)
        self.split_large_files = self._load_bool_setting('split_large_files', True)
        self.keep_encrypted_iso = self._load_bool_setting('keep_encrypted_iso', False)
        self.keep_dkey_file = self._load_bool_setting('keep_dkey_file', False)
        self.keep_unsplit_file = self._load_bool_setting('keep_unsplit_file', False)
        self.split_pkg = self._load_bool_setting('split_pkg', True)
        self.extract_ps3_iso = self._load_bool_setting('extract_ps3_iso', False)
        self.keep_decrypted_iso_after_extraction = self._load_bool_setting('keep_decrypted_iso_after_extraction', True)
        
        # Universal content organization setting (now applies to all platforms)
        self.organize_content_to_folders = self._load_bool_setting('organize_content_to_folders', False)
        
        # Load binary paths
        self.ps3dec_binary = self.settings.value('binaries/ps3dec_binary', '')
        self.extractps3iso_binary = self.settings.value('binaries/extractps3iso_binary', '')
        
        # Initialize binary validation manager
        self.binary_validator = BinaryValidationManager(self)
        
        # Clean up duplicate entries from old versions
        self._clean_up_duplicate_entries()
        
        # Create directories
        self.create_directories()
        
        # Check binaries
        self.check_ps3dec_binary()
        self.check_extractps3iso_binary()
    
    def validate_startup_prerequisites(self, parent_widget=None):
        """
        Validate startup prerequisites for Windows systems.
        This should be called during application startup.
        """
        return self.binary_validator.validate_startup_binaries(parent_widget)
    
    def _setup_directory_properties(self):
        """Setup directory properties for backwards compatibility."""
        # Root and processing directories
        self.myrient_base_dir = self.directory_manager.root_dir
        self.processing_dir = self.directory_manager.processing_dir
        
        # Platform-specific directories
        self.ps3iso_dir = self.directory_manager.ps3iso_dir
        self.ps2iso_dir = self.directory_manager.ps2iso_dir
        self.psxiso_dir = self.directory_manager.psxiso_dir
        self.pspiso_dir = self.directory_manager.pspiso_dir
        self.psn_rap_dir = self.directory_manager.psn_rap_dir
        self.psn_pkg_dir = self.directory_manager.psn_pkg_dir
        
        # Dynamic platform directories
        if self.config_manager:
            platforms = self.config_manager.get_platforms()
            for platform_id in platforms.keys():
                if platform_id not in ['ps3', 'ps2', 'psx', 'psp', 'psn']:
                    attr_name = f"{platform_id.lower()}_dir"
                    if hasattr(self.directory_manager, attr_name):
                        setattr(self, attr_name, getattr(self.directory_manager, attr_name))
    
    def _clean_up_duplicate_entries(self):
        """Clean up duplicate directory entries from the General section."""
        # List of directory keys that should only be in the directories section
        directory_keys = [
            'gamecube_dir', 'processing_dir', 'ps2_dir', 'ps2iso_dir', 'ps3_dir', 'ps3iso_dir',
            'psn_pkg_dir', 'psn_rap_dir', 'psp_dir', 'pspiso_dir', 'psx_dir', 'psxiso_dir',
            'wii_dir', 'root_dir'
        ]
        
        # Add dynamic platform directories if config manager is available
        if self.config_manager:
            platforms = self.config_manager.get_platforms()
            for platform_id in platforms.keys():
                if platform_id not in ['ps3', 'ps2', 'psx', 'psp', 'psn']:
                    directory_keys.append(f"{platform_id.lower()}_dir")
        
        # Remove duplicate entries from General section
        for key in directory_keys:
            if self.settings.contains(f'General/{key}'):
                # If there's no corresponding entry in directories section, move it
                if not self.settings.contains(f'directories/{key}'):
                    value = self.settings.value(f'General/{key}')
                    if value:
                        self.settings.setValue(f'directories/{key}', value)
                
                # Remove from General section
                self.settings.remove(f'General/{key}')
        
        # Also clean up binary entries that might be in wrong section
        binary_keys = ['extractps3iso_binary', 'ps3dec_binary']
        for key in binary_keys:
            if self.settings.contains(f'General/{key}'):
                # If there's no corresponding entry in binaries section, move it
                if not self.settings.contains(f'binaries/{key}'):
                    value = self.settings.value(f'General/{key}')
                    if value:
                        self.settings.setValue(f'binaries/{key}', value)
                
                # Remove from General section
                self.settings.remove(f'General/{key}')
        
        # Sync changes to file
        self.settings.sync()
    
    def _load_bool_setting(self, key, default):
        """Load a boolean setting with proper type conversion."""
        value = self.settings.value(f"Checkboxes/{key}", default)
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
        return bool(value) if value is not None else default
    
    def create_directories(self):
        """Create all necessary directories if they don't exist."""
        failed_dirs = self.directory_manager.create_all_directories()
        if failed_dirs:
            error_msg = "Failed to create the following directories:\n"
            for directory, error in failed_dirs:
                error_msg += f"  {directory}: {error}\n"
            raise Exception(error_msg)
    
    def get_platform_directory(self, platform_id):
        """Get the output directory for a specific platform."""
        return self.directory_manager.get_platform_directory(platform_id)
    
    def validate_and_update_directory(self, directory_type, new_path):
        """Validate and update a directory path."""
        return self.directory_manager.update_directory(directory_type, new_path)
    
    def check_ps3dec_binary(self):
        """Check if ps3dec binary exists and is valid."""
        if not os.path.isfile(self.ps3dec_binary):
            self.ps3dec_binary = ''
            self.settings.setValue('binaries/ps3dec_binary', '')

        # Check if ps3dec is in PATH
        ps3dec_in_path = shutil.which("ps3dec") or shutil.which("PS3Dec") or shutil.which("ps3dec.exe") or shutil.which("PS3Dec.exe")
        
        if ps3dec_in_path:
            self.ps3dec_binary = ps3dec_in_path
            self.settings.setValue('binaries/ps3dec_binary', self.ps3dec_binary)
        else:
            # Check if it's in the config directory
            config_dir = os.path.join(os.getcwd(), 'config')
            config_binary = os.path.join(config_dir, "ps3dec.exe")
            if os.path.isfile(config_binary):
                self.ps3dec_binary = config_binary
                self.settings.setValue('binaries/ps3dec_binary', self.ps3dec_binary)
    
    def check_extractps3iso_binary(self):
        """Check if extractps3iso binary exists and is valid."""
        if not os.path.isfile(self.extractps3iso_binary):
            self.extractps3iso_binary = ''
            self.settings.setValue('binaries/extractps3iso_binary', '')
        
        # Binary name based on platform
        binary_name = "extractps3iso.exe" if platform.system() == 'Windows' else "extractps3iso"
        
        # Check if extractps3iso is in PATH
        extractps3iso_in_path = shutil.which("extractps3iso") or shutil.which("extractps3iso.exe")
        
        if extractps3iso_in_path:
            self.extractps3iso_binary = extractps3iso_in_path
            self.settings.setValue('binaries/extractps3iso_binary', self.extractps3iso_binary)
        else:
            # Check if it's in the config directory first
            config_dir = os.path.join(os.getcwd(), 'config')
            config_binary = os.path.join(config_dir, binary_name)
            if os.path.isfile(config_binary):
                self.extractps3iso_binary = config_binary
                self.settings.setValue('binaries/extractps3iso_binary', self.extractps3iso_binary)
            else:
                # Check if it's in the current directory (legacy location)
                local_binary = os.path.join(os.getcwd(), binary_name)
                if os.path.isfile(local_binary):
                    self.extractps3iso_binary = local_binary
                    self.settings.setValue('binaries/extractps3iso_binary', self.extractps3iso_binary)
    
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
                import hashlib
                print("Downloading PS3Dec from GitHub...")
                
                # Ensure config directory exists
                config_dir = os.path.join(os.getcwd(), 'config')
                os.makedirs(config_dir, exist_ok=True)
                
                # Download to config directory
                ps3dec_path = os.path.join(config_dir, "ps3dec.exe")
                urllib.request.urlretrieve(
                    "https://github.com/Redrrx/ps3dec/releases/download/0.1.0/ps3dec.exe",
                    ps3dec_path
                )

                # Verify SHA-256 integrity
                EXPECTED_SHA256 = None  # TODO: pin actual hash after first verified download
                if EXPECTED_SHA256:
                    sha256 = hashlib.sha256()
                    with open(ps3dec_path, 'rb') as f:
                        for block in iter(lambda: f.read(8192), b''):
                            sha256.update(block)
                    if sha256.hexdigest() != EXPECTED_SHA256:
                        os.unlink(ps3dec_path)
                        print(f"SHA-256 mismatch for ps3dec.exe! Expected {EXPECTED_SHA256}, got {sha256.hexdigest()}")
                        return False

                self.ps3dec_binary = ps3dec_path
                self.settings.setValue('binaries/ps3dec_binary', self.ps3dec_binary)
                print(f"PS3Dec downloaded successfully to {ps3dec_path}")
                return True
            except Exception as e:
                print(f"Error downloading PS3Dec: {str(e)}")
                return False
        return False
        
    def download_extractps3iso(self):
        """Download the extractps3iso binary with improved error handling and nested archive support."""
        if platform.system() == 'Windows':
            # Use the specific fallback download URL directly
            download_url = "https://github.com/bucanero/ps3iso-utils/releases/download/277db7de/ps3iso-277db7de-Win64.zip"
            
            try:
                print(f"Downloading extractps3iso from GitHub using URL: {download_url}...")
                
                # Create temporary files for ZIP and TAR.GZ
                with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
                    temp_zip_path = temp_zip.name
                
                # Download the ZIP file with better error handling
                try:
                    urllib.request.urlretrieve(download_url, temp_zip_path)
                except urllib.error.HTTPError as e:
                    print(f"HTTP Error {e.code}: {e.reason}")
                    raise
                except urllib.error.URLError as e:
                    print(f"URL Error: {e.reason}")
                    raise
                
                # Extract the ZIP file and look for build.tar.gz
                extractps3iso_found = False
                with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                    # List all files to debug
                    all_files = zip_ref.namelist()
                    print(f"Files in ZIP: {all_files}")
                    
                    # Look for build.tar.gz
                    tar_gz_file = None
                    for file in all_files:
                        if file.lower().endswith('build.tar.gz'):
                            tar_gz_file = file
                            break
                    
                    if tar_gz_file:
                        print(f"Found nested archive: {tar_gz_file}")
                        
                        # Extract build.tar.gz to a temporary location
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as temp_tar:
                            temp_tar_path = temp_tar.name
                        
                        # Extract the tar.gz from the zip
                        with zip_ref.open(tar_gz_file) as tar_source:
                            with open(temp_tar_path, 'wb') as tar_target:
                                shutil.copyfileobj(tar_source, tar_target)
                        
                        # Now extract the tar.gz and look for extractps3iso.exe
                        import tarfile
                        try:
                            with tarfile.open(temp_tar_path, 'r:gz') as tar_ref:
                                tar_files = tar_ref.getnames()
                                print(f"Files in TAR.GZ: {tar_files}")
                                
                                # Look for extractps3iso.exe in the tar
                                for tar_file in tar_files:
                                    tar_file_lower = tar_file.lower()
                                    if ('extractps3iso.exe' in tar_file_lower or
                                        tar_file_lower.endswith('extractps3iso.exe') or
                                        (tar_file_lower.endswith('.exe') and 'extractps3iso' in tar_file_lower)):
                                        
                                        print(f"Found extractps3iso binary in TAR: {tar_file}")
                                        
                                        # Ensure config directory exists
                                        config_dir = os.path.join(os.getcwd(), 'config')
                                        os.makedirs(config_dir, exist_ok=True)
                                        
                                        # Extract the specific file to config directory
                                        member = tar_ref.getmember(tar_file)
                                        member.name = "extractps3iso.exe"  # Rename to standard name
                                        tar_ref.extract(member, config_dir)
                                        
                                        extractps3iso_found = True
                                        break
                        except Exception as tar_error:
                            print(f"Error extracting TAR.GZ: {str(tar_error)}")
                        finally:
                            # Clean up tar.gz temp file
                            try:
                                os.unlink(temp_tar_path)
                            except Exception:
                                pass
                    else:
                        # Fallback: try direct extraction from ZIP (old behavior)
                        print("build.tar.gz not found, trying direct extraction from ZIP...")
                        for file in all_files:
                            file_lower = file.lower()
                            if ('extractps3iso.exe' in file_lower or
                                file_lower.endswith('extractps3iso.exe') or
                                (file_lower.endswith('.exe') and 'extractps3iso' in file_lower)):
                                
                                print(f"Found extractps3iso binary: {file}")
                                
                                # Ensure config directory exists
                                config_dir = os.path.join(os.getcwd(), 'config')
                                os.makedirs(config_dir, exist_ok=True)
                                
                                # Extract the file to config directory
                                source = zip_ref.open(file)
                                target_path = os.path.join(config_dir, "extractps3iso.exe")
                                
                                with source, open(target_path, "wb") as target:
                                    shutil.copyfileobj(source, target)
                                
                                extractps3iso_found = True
                                break
                
                # Delete the temporary ZIP file
                try:
                    os.unlink(temp_zip_path)
                except Exception:
                    pass  # Ignore cleanup errors
                
                if extractps3iso_found:
                    # Update the binary path to config directory
                    config_dir = os.path.join(os.getcwd(), 'config')
                    extractps3iso_path = os.path.join(config_dir, "extractps3iso.exe")
                    
                    self.extractps3iso_binary = extractps3iso_path
                    self.settings.setValue('binaries/extractps3iso_binary', self.extractps3iso_binary)
                    
                    print(f"extractps3iso downloaded and extracted successfully to {extractps3iso_path}")
                    return True
                else:
                    print("extractps3iso.exe not found in the downloaded archive")
                    return False
            
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
            'keep_decrypted_iso_after_extraction', 'organize_content_to_folders'
        }
        
        if key in checkbox_settings:
            # Save checkbox settings to the Checkboxes section
            self.settings.setValue(f"Checkboxes/{key}", value)
        elif key in ['ps3dec_binary', 'extractps3iso_binary']:
            # Save binary settings to the binaries section
            self.settings.setValue(f"binaries/{key}", value)
        elif key.endswith('_dir') or key in ['root_dir', 'processing_dir']:
            # Save directory settings to the directories section
            if key == 'myrient_base_dir':
                key = 'root_dir'  # Normalize legacy key name
            
            try:
                self.validate_and_update_directory(key, value)
            except ValueError as e:
                raise ValueError(f"Invalid directory path for {key}: {str(e)}")
        else:
            # Save other settings to the General section
            self.settings.setValue(key, value)
        
        # Update instance variables for backwards compatibility
        if key == 'ps3dec_binary':
            self.ps3dec_binary = value
        elif key == 'extractps3iso_binary':
            self.extractps3iso_binary = value
        elif key in ['myrient_base_dir', 'root_dir']:
            old_root = self.myrient_base_dir
            self.myrient_base_dir = value
            # Update platform directories if they were using default structure
            self.directory_manager._update_platform_dirs_on_root_change(old_root, value)
            
            # Update the exposed properties for backward compatibility
            self._setup_directory_properties()
        elif key == 'processing_dir':
            self.processing_dir = value
            self.directory_manager.processing_dir = value
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
        elif key == 'organize_content_to_folders':
            self.organize_content_to_folders = value
        elif key.endswith('_dir'):
            # Handle directory updates through directory manager
            setattr(self, key, value)
            if hasattr(self.directory_manager, key):
                setattr(self.directory_manager, key, value)


class SettingsDialog(QDialog):
    """Dialog for configuring application settings with hierarchical directory management."""
    
    def __init__(self, settings_manager, config_manager, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.settings_manager = settings_manager
        self.config_manager = config_manager
        self.platforms = config_manager.get_platforms()
        
        self.setWindowTitle("Myrient Downloader Settings")
        self.setMinimumWidth(700)
        
        # Dictionary to store all input widgets
        self.directory_inputs = {}
        self.binary_inputs = {}
        self.appearance_inputs = {}
        
        self.initUI()
        
        # Adjust size to fit content dynamically
        self.adjustSize()
    
    def initUI(self):
        """Initialize the UI components with tabbed interface."""
        main_layout = QVBoxLayout(self)
        
        # Create tab widget for better organization
        tab_widget = QTabWidget()
        
        # Directory Management Tab
        directories_tab = self.create_directories_tab()
        tab_widget.addTab(directories_tab, "Directory Structure")
        
        # Binary Tools Tab
        binaries_tab = self.create_binaries_tab()
        tab_widget.addTab(binaries_tab, "Binaries")
        
        # Appearance Tab
        appearance_tab = self.create_appearance_tab()
        tab_widget.addTab(appearance_tab, "Appearance")
        
        main_layout.addWidget(tab_widget)
        
        # Create OK and Cancel buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        
        # Add reset to defaults button
        reset_button = QPushButton("Reset to Defaults")
        reset_button.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(reset_button)
        
        save_settings_button = QPushButton("Save Settings")
        save_settings_button.clicked.connect(self.save_settings)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(save_settings_button)
        button_layout.addWidget(cancel_button)
        
        main_layout.addLayout(button_layout)
    
    def create_directories_tab(self):
        """Create the directories configuration tab."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # Root Configuration Section
        root_group = QGroupBox("Root Directory Configuration")
        root_group.setStyleSheet("QGroupBox { font-weight: bold; padding-top: 15px; margin-top: 5px; }")
        root_layout = QFormLayout()
        
        # Root Directory (MyrientDownloads)
        self.root_dir_input = QLineEdit(self.settings_manager.myrient_base_dir)
        root_browse = QPushButton("Browse...")
        root_browse.clicked.connect(lambda: self.browse_directory(self.root_dir_input))
        
        # Connect root directory changes to update platform directories
        self.root_dir_input.textChanged.connect(self.update_platform_directories_on_root_change)
        
        root_dir_layout = QHBoxLayout()
        root_dir_layout.addWidget(self.root_dir_input)
        root_dir_layout.addWidget(root_browse)
        
        root_layout.addRow("Root Download Directory:", root_dir_layout)
        self.directory_inputs['root_dir'] = self.root_dir_input
        
        # Store original root for change detection
        self._original_root = self.settings_manager.myrient_base_dir
        
        # Processing Directory
        self.processing_dir_input = QLineEdit(self.settings_manager.processing_dir)
        processing_browse = QPushButton("Browse...")
        processing_browse.clicked.connect(lambda: self.browse_directory(self.processing_dir_input))
        
        processing_layout = QHBoxLayout()
        processing_layout.addWidget(self.processing_dir_input)
        processing_layout.addWidget(processing_browse)
        
        root_layout.addRow("Temporary Processing Directory:", processing_layout)
        self.directory_inputs['processing_dir'] = self.processing_dir_input
        
        root_group.setLayout(root_layout)
        scroll_layout.addWidget(root_group)
        
        # PlayStation Console Directories Section
        playstation_group = QGroupBox("PlayStation Directories")
        playstation_group.setStyleSheet("QGroupBox { font-weight: bold; padding-top: 15px; margin-top: 5px; }")
        playstation_layout = QFormLayout()
        
        # PlayStation platform directories
        playstation_configs = [
            ('ps3iso_dir', 'PlayStation 3 (PS3ISO):', self.settings_manager.ps3iso_dir),
            ('ps2iso_dir', 'PlayStation 2 (PS2ISO):', self.settings_manager.ps2iso_dir),
            ('psxiso_dir', 'PlayStation 1/PSX (PSXISO):', self.settings_manager.psxiso_dir),
            ('pspiso_dir', 'PlayStation Portable (PSPISO):', self.settings_manager.pspiso_dir),
        ]
        
        for attr_name, label, current_value in playstation_configs:
            line_edit = QLineEdit(current_value)
            browse_button = QPushButton("Browse...")
            browse_button.clicked.connect(lambda _, le=line_edit: self.browse_directory(le))
            
            dir_layout = QHBoxLayout()
            dir_layout.addWidget(line_edit)
            dir_layout.addWidget(browse_button)
            
            playstation_layout.addRow(label, dir_layout)
            self.directory_inputs[attr_name] = line_edit
        
        playstation_group.setLayout(playstation_layout)
        scroll_layout.addWidget(playstation_group)
        
        # PlayStation Network Section
        psn_group = QGroupBox("PlayStation Network (PSN) Content")
        psn_group.setStyleSheet("QGroupBox { font-weight: bold; padding-top: 15px; margin-top: 5px; }")
        psn_layout = QFormLayout()
        
        # PSN directories with hierarchical structure
        psn_configs = [
            ('psn_pkg_dir', 'PKG Files (packages/):', self.settings_manager.psn_pkg_dir),
            ('psn_rap_dir', 'RAP Files (exdata/):', self.settings_manager.psn_rap_dir),
        ]
        
        for attr_name, label, current_value in psn_configs:
            line_edit = QLineEdit(current_value)
            browse_button = QPushButton("Browse...")
            browse_button.clicked.connect(lambda _, le=line_edit: self.browse_directory(le))
            
            dir_layout = QHBoxLayout()
            dir_layout.addWidget(line_edit)
            dir_layout.addWidget(browse_button)
            
            psn_layout.addRow(label, dir_layout)
            self.directory_inputs[attr_name] = line_edit
        
        psn_group.setLayout(psn_layout)
        scroll_layout.addWidget(psn_group)
        
        # Other Gaming Systems Section
        if self.platforms:
            other_platforms = {k: v for k, v in self.platforms.items()
                             if k not in ['ps3', 'ps2', 'psx', 'psp', 'psn']}
            
            if other_platforms:
                other_group = QGroupBox("Other Consoles/Systems")
                other_group.setStyleSheet("QGroupBox { font-weight: bold; padding-top: 15px; margin-top: 5px; }")
                other_layout = QFormLayout()
                
                for platform_id, data in other_platforms.items():
                    attr_name = f"{platform_id.lower()}_dir"
                    tab_name = data.get('tab_name', platform_id.upper())
                    current_value = getattr(self.settings_manager, attr_name,
                                          os.path.join(self.settings_manager.myrient_base_dir, platform_id.upper()))
                    
                    line_edit = QLineEdit(current_value)
                    browse_button = QPushButton("Browse...")
                    browse_button.clicked.connect(lambda _, le=line_edit: self.browse_directory(le))
                    
                    dir_layout = QHBoxLayout()
                    dir_layout.addWidget(line_edit)
                    dir_layout.addWidget(browse_button)
                    
                    other_layout.addRow(f"{tab_name}:", dir_layout)
                    self.directory_inputs[attr_name] = line_edit
                
                other_group.setLayout(other_layout)
                scroll_layout.addWidget(other_group)
        
        scroll_layout.addStretch(1)
        scroll_area.setWidget(scroll_content)
        return scroll_area
    
    def create_binaries_tab(self):
        """Create the binary tools configuration tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Binary Tools Section
        binaries_group = QGroupBox("Binary Locations")
        binaries_group.setStyleSheet("QGroupBox { font-weight: bold; padding-top: 15px; margin-top: 5px; }")
        binaries_layout = QFormLayout()
        
        # PS3Dec Binary
        self.ps3dec_input = QLineEdit(self.settings_manager.ps3dec_binary)
        ps3dec_browse = QPushButton("Browse...")
        ps3dec_browse.clicked.connect(lambda: self.browse_executable("PS3 Decrypter", self.ps3dec_input))
        
        ps3dec_layout = QHBoxLayout()
        ps3dec_layout.addWidget(self.ps3dec_input)
        ps3dec_layout.addWidget(ps3dec_browse)
        
        # Only show download button on Windows
        if platform.system() == 'Windows':
            ps3dec_download = QPushButton("Download")
            ps3dec_download.clicked.connect(self.download_ps3dec)
            ps3dec_layout.addWidget(ps3dec_download)
        
        binaries_layout.addRow("PS3Dec Binary:", ps3dec_layout)
        self.binary_inputs['ps3dec_binary'] = self.ps3dec_input
        
        # extractps3iso Binary
        self.extractps3iso_input = QLineEdit(self.settings_manager.extractps3iso_binary)
        extractps3iso_browse = QPushButton("Browse...")
        extractps3iso_browse.clicked.connect(lambda: self.browse_executable("PS3 ISO Extractor", self.extractps3iso_input))
        
        extractps3iso_layout = QHBoxLayout()
        extractps3iso_layout.addWidget(self.extractps3iso_input)
        extractps3iso_layout.addWidget(extractps3iso_browse)
        
        # Only show download button on Windows
        if platform.system() == 'Windows':
            extractps3iso_download = QPushButton("Download")
            extractps3iso_download.clicked.connect(self.download_extractps3iso)
            extractps3iso_layout.addWidget(extractps3iso_download)
        
        binaries_layout.addRow("extractps3iso Binary:", extractps3iso_layout)
        self.binary_inputs['extractps3iso_binary'] = self.extractps3iso_input
        
        binaries_group.setLayout(binaries_layout)
        layout.addWidget(binaries_group)
        
        # Binary explanation
        binary_explanation = QLabel(
            "Binary Info:\n"
            "• PS3Dec: Required for decrypting PlayStation 3 ISO files\n"
            "  - Author: Redrrx\n"
            "  - Source: https://github.com/Redrrx/ps3dec\n"
            "• extractps3iso: Required for extracting PlayStation 3 ISO contents\n"
            "  - Author: bucanero\n"
            "  - Source: https://github.com/bucanero/ps3iso-utils\n"
            "• Windows: Use the Download buttons to automatically download these tools\n"
            "• Arch Linux: Install ps3iso-utils-git and ps3dec-git from the AUR\n"
            "• These tools will be automatically detected if installed in your system PATH\n"
            "• You can also manually specify their locations using the Browse buttons"
        )
        binary_explanation.setWordWrap(True)
        binary_explanation.setStyleSheet(get_explanation_style())
        layout.addWidget(binary_explanation)
        
        layout.addStretch(1)
        return widget
    
    def create_appearance_tab(self):
        """Create the appearance configuration tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Theme Section
        theme_group = QGroupBox("Theme Settings")
        theme_group.setStyleSheet("QGroupBox { font-weight: bold; padding-top: 15px; margin-top: 5px; }")
        theme_layout = QFormLayout()
        
        # Get current theme setting - avoid creating QSettings if QApplication doesn't exist
        current_theme = 'dark'  # Default to dark theme
        try:
            from PyQt5.QtWidgets import QApplication
            if QApplication.instance():  # Only access QSettings if QApplication exists
                from PyQt5.QtCore import QSettings
                app_settings = QSettings('./config/myrientDownloaderGUI.ini', QSettings.IniFormat)
                current_theme = app_settings.value('appearance/theme', 'dark')
        except Exception:
            current_theme = 'dark'
        
        # Theme selection
        from PyQt5.QtWidgets import QComboBox
        self.theme_combo = QComboBox()
        theme_options = [
            ('auto', 'Auto (Follow System)'),
            ('light', 'Light Theme'),
            ('dark', 'Dark Theme'),
            ('system', 'System Default (Qt Native)')
        ]
        
        for value, display_name in theme_options:
            self.theme_combo.addItem(display_name, value)
        
        # Set current selection
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == current_theme:
                self.theme_combo.setCurrentIndex(i)
                break
        
        theme_layout.addRow("Application Theme:", self.theme_combo)
        self.appearance_inputs['theme'] = self.theme_combo
        
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        
        # Theme explanation
        theme_explanation = QLabel(
            "Theme Options:\n"
            "• Auto: Automatically detects your system's theme preference\n"
            "• Light Theme: Always use the light color scheme\n"
            "• Dark Theme: Always use the dark color scheme\n"
            "• System Default: Use Qt's native system theme\n\n"
            "Changes will take effect after restarting the application."
        )
        theme_explanation.setWordWrap(True)
        theme_explanation.setStyleSheet(get_explanation_style())
        layout.addWidget(theme_explanation)
        
        layout.addStretch(1)
        return widget
    
    
    def update_platform_directories_on_root_change(self):
        """Update platform directories when root directory changes."""
        new_root = self.root_dir_input.text().strip()
        if not new_root:
            return
        
        # Store the original root to detect changes
        original_root = getattr(self, '_original_root', self.settings_manager.myrient_base_dir)
        
        # Only update if the root actually changed
        if new_root == original_root:
            return
        
        # Check if platform directories are using default structure relative to old root
        platform_updates = {}
        
        # PlayStation directories and processing directory
        platform_configs = {
            'ps3iso_dir': 'PS3ISO',
            'ps2iso_dir': 'PS2ISO',
            'psxiso_dir': 'PSXISO',
            'pspiso_dir': 'PSPISO',
            'psn_pkg_dir': os.path.join('PSN', 'packages'),
            'psn_rap_dir': os.path.join('PSN', 'exdata'),
            'processing_dir': 'processing'
        }
        
        # Add dynamic platform directories
        for platform_id in self.platforms:
            if platform_id not in ['ps3', 'ps2', 'psx', 'psp', 'psn']:
                attr_name = f"{platform_id.lower()}_dir"
                platform_configs[attr_name] = platform_id.upper()
        
        # Check each platform directory
        for attr_name, subdir in platform_configs.items():
            if attr_name in self.directory_inputs:
                current_path = self.directory_inputs[attr_name].text().strip()
                expected_old_path = os.path.join(original_root, subdir)
                
                # If the current path matches the old default structure, update it
                if current_path == expected_old_path or current_path == os.path.normpath(expected_old_path):
                    new_path = os.path.join(new_root, subdir)
                    platform_updates[attr_name] = new_path
        
        # Apply updates
        for attr_name, new_path in platform_updates.items():
            self.directory_inputs[attr_name].setText(new_path)
        
        # Update the stored original root
        self._original_root = new_root
    
    def reset_to_defaults(self):
        """Reset all settings to their default values."""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Are you sure you want to reset all directory and binary settings to their default values?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Reset directory inputs to defaults
            default_root = 'MyrientDownloads'
            self.root_dir_input.setText(default_root)
            self.processing_dir_input.setText(os.path.join(default_root, 'processing'))
            
            # Reset PlayStation directories
            self.directory_inputs['ps3iso_dir'].setText(os.path.join(default_root, 'PS3ISO'))
            self.directory_inputs['ps2iso_dir'].setText(os.path.join(default_root, 'PS2ISO'))
            self.directory_inputs['psxiso_dir'].setText(os.path.join(default_root, 'PSXISO'))
            self.directory_inputs['pspiso_dir'].setText(os.path.join(default_root, 'PSPISO'))
            
            # Reset PSN directories
            self.directory_inputs['psn_pkg_dir'].setText(os.path.join(default_root, 'PSN', 'packages'))
            self.directory_inputs['psn_rap_dir'].setText(os.path.join(default_root, 'PSN', 'exdata'))
            
            # Reset other platform directories
            for platform_id in self.platforms:
                if platform_id not in ['ps3', 'ps2', 'psx', 'psp', 'psn']:
                    attr_name = f"{platform_id.lower()}_dir"
                    if attr_name in self.directory_inputs:
                        self.directory_inputs[attr_name].setText(os.path.join(default_root, platform_id.upper()))
            
            # Reset binary inputs
            self.ps3dec_input.setText('')
            self.extractps3iso_input.setText('')
            
            # Reset theme to dark
            if hasattr(self, 'theme_combo'):
                for i in range(self.theme_combo.count()):
                    if self.theme_combo.itemData(i) == 'dark':
                        self.theme_combo.setCurrentIndex(i)
                        break
            
            # Update the original root reference
            self._original_root = default_root
    
    def browse_directory(self, line_edit):
        """Open directory browser dialog and update line edit"""
        current_dir = line_edit.text() or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory", current_dir, QFileDialog.ShowDirsOnly
        )
        if directory:
            line_edit.setText(directory)
    
    def browse_executable(self, title, line_edit):
        """Open file browser dialog for executables and update line edit"""
        current_path = line_edit.text() or os.path.expanduser("~")
        file_filter = "All Files (*)" if os.name == 'posix' else "Executables (*.exe);;All Files (*)"
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Select {title}",
            os.path.dirname(current_path) if current_path else os.path.expanduser("~"),
            file_filter
        )
        
        if file_path:
            line_edit.setText(file_path)
    
    def download_ps3dec(self):
        """Download PS3Dec binary and update the input field."""
        try:
            if self.settings_manager.download_ps3dec():
                self.ps3dec_input.setText(self.settings_manager.ps3dec_binary)
                QMessageBox.information(
                    self,
                    "Download Successful",
                    "PS3Dec has been downloaded successfully!"
                )
            else:
                if platform.system() == 'Windows':
                    QMessageBox.warning(
                        self,
                        "Download Failed",
                        "Failed to download PS3Dec. Please check your internet connection and try again."
                    )
                else:
                    QMessageBox.information(
                        self,
                        "Manual Installation Required",
                        "On Linux/macOS, please install ps3dec manually from your package manager or compile from source."
                    )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Download Error",
                f"An error occurred while downloading PS3Dec:\n{str(e)}"
            )
    
    def download_extractps3iso(self):
        """Download extractps3iso binary and update the input field."""
        try:
            if self.settings_manager.download_extractps3iso():
                self.extractps3iso_input.setText(self.settings_manager.extractps3iso_binary)
                QMessageBox.information(
                    self,
                    "Download Successful",
                    "extractps3iso has been downloaded successfully!"
                )
            else:
                if platform.system() == 'Windows':
                    QMessageBox.warning(
                        self,
                        "Download Failed",
                        "Failed to download extractps3iso. Please check your internet connection and try again."
                    )
                else:
                    QMessageBox.information(
                        self,
                        "Manual Installation Required",
                        "On Linux/macOS, please install extractps3iso manually from your package manager or compile from source."
                    )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Download Error",
                f"An error occurred while downloading extractps3iso:\n{str(e)}"
            )
    
    def save_settings(self):
        """Save all settings and close dialog"""
        try:
            # Validate and save all directory settings
            error_messages = []
            
            # Save root and processing directories first
            for key, input_widget in self.directory_inputs.items():
                directory = input_widget.text().strip()
                if directory:
                    try:
                        if key == 'root_dir':
                            self.settings_manager.update_setting('myrient_base_dir', directory)
                        else:
                            self.settings_manager.update_setting(key, directory)
                    except ValueError as e:
                        error_messages.append(f"{key}: {str(e)}")
            
            # Save binary settings
            for key, input_widget in self.binary_inputs.items():
                binary_path = input_widget.text().strip()
                self.settings_manager.update_setting(key, binary_path)
            
            # Save appearance settings
            if hasattr(self, 'appearance_inputs'):
                for key, input_widget in self.appearance_inputs.items():
                    if key == 'theme':
                        theme_value = input_widget.currentData()
                        if theme_value:
                            from PyQt5.QtCore import QSettings
                            app_settings = QSettings('./config/myrientDownloaderGUI.ini', QSettings.IniFormat)
                            app_settings.setValue('appearance/theme', theme_value)
                            app_settings.sync()
            
            # Show errors if any occurred
            if error_messages:
                QMessageBox.warning(
                    self,
                    "Directory Validation Errors",
                    "The following directory paths are invalid:\n\n" + "\n".join(error_messages)
                )
                return
            
            # Update directories on disk
            self.settings_manager.create_directories()
            
            # Accept and close the dialog
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Saving Settings",
                f"An error occurred while saving settings:\n{str(e)}"
            )
