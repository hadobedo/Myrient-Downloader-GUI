import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QFileDialog, QGroupBox, QFormLayout,
    QMessageBox, QScrollArea, QWidget
)
from PyQt5.QtCore import Qt


class SettingsDialog(QDialog):
    """Dialog for configuring application settings"""
    
    def __init__(self, settings_manager, config_manager, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.settings_manager = settings_manager
        self.config_manager = config_manager
        self.platforms = config_manager.get_platforms()
        
        self.setWindowTitle("Settings")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        self.initUI()
    
    def initUI(self):
        """Initialize the UI components"""
        main_layout = QVBoxLayout(self)
        
        # Create a scroll area for potentially many platforms
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # Create a group for general settings
        general_group = QGroupBox("General Settings")
        general_layout = QFormLayout()
        
        # PS3Dec path setting
        self.ps3dec_path = QLineEdit(self.settings_manager.ps3dec_binary)
        ps3dec_browse = QPushButton("Browse...")
        ps3dec_browse.clicked.connect(lambda: self.browse_executable("PS3 Decrypter", self.ps3dec_path))
        
        ps3dec_layout = QHBoxLayout()
        ps3dec_layout.addWidget(self.ps3dec_path)
        ps3dec_layout.addWidget(ps3dec_browse)
        
        general_layout.addRow("PS3Dec Binary:", ps3dec_layout)
        
        # Add extractps3iso binary setting
        self.extractps3iso_path = QLineEdit(self.settings_manager.extractps3iso_binary)
        extractps3iso_browse = QPushButton("Browse...")
        extractps3iso_browse.clicked.connect(lambda: self.browse_executable("PS3 ISO Extractor", self.extractps3iso_path))
        
        extractps3iso_layout = QHBoxLayout()
        extractps3iso_layout.addWidget(self.extractps3iso_path)
        extractps3iso_layout.addWidget(extractps3iso_browse)
        
        general_layout.addRow("extractps3iso Binary:", extractps3iso_layout)
        
        # Add Processing Directory
        self.processing_path = QLineEdit(self.settings_manager.processing_dir)
        processing_browse = QPushButton("Browse...")
        processing_browse.clicked.connect(lambda: self.browse_directory(self.processing_path))
        
        processing_layout = QHBoxLayout()
        processing_layout.addWidget(self.processing_path)
        processing_layout.addWidget(processing_browse)
        
        general_layout.addRow("Processing Directory:", processing_layout)
        
        general_group.setLayout(general_layout)
        
        scroll_layout.addWidget(general_group)
        
        # Create a group for platform paths
        platform_group = QGroupBox("Platform Output Directories")
        platform_layout = QFormLayout()
        
        # Dictionary to store path line edits
        self.platform_paths = {}
        
        # Traditional platforms (maintain existing convention)
        traditional_platforms = {
            'ps3': 'PS3ISO Directory:',
            'psn': 'PSN PKG Directory:',
            'psn_rap': 'PSN RAP Directory:', # Special case for PSN RAP files
            'ps2': 'PS2ISO Directory:',
            'psx': 'PSXISO Directory:',
            'psp': 'PSPISO Directory:',
        }
        
        # Add line edits and browse buttons for traditional platforms
        for platform_id, label_text in traditional_platforms.items():
            if platform_id == 'psn_rap':
                # Special case for PSN RAP files
                attr_name = 'psn_rap_dir'
            else:
                # Standard platform directory
                attr_name = f"{platform_id}_dir" if platform_id != 'psn' else 'psn_pkg_dir'
                
            path_value = getattr(self.settings_manager, attr_name, "")
            
            line_edit = QLineEdit(path_value)
            browse_button = QPushButton("Browse...")
            browse_button.clicked.connect(lambda _, le=line_edit: self.browse_directory(le))
            
            path_layout = QHBoxLayout()
            path_layout.addWidget(line_edit)
            path_layout.addWidget(browse_button)
            
            platform_layout.addRow(label_text, path_layout)
            self.platform_paths[attr_name] = line_edit
        
        # Dynamically add entries for additional platforms from YAML
        for platform_id, data in self.platforms.items():
            # Skip the traditional platforms we already added
            if platform_id in ['ps3', 'psn', 'ps2', 'psx', 'psp']:
                continue
            
            # Get the tab name as a user-friendly label
            tab_name = data.get('tab_name', platform_id.upper())
            
            # Attribute name for this platform directory
            attr_name = f"{platform_id}_dir"
            
            # Get the current path from settings manager
            path_value = getattr(self.settings_manager, attr_name, f"MyrientDownloads/{platform_id.upper()}")
            
            line_edit = QLineEdit(path_value)
            browse_button = QPushButton("Browse...")
            browse_button.clicked.connect(lambda _, le=line_edit: self.browse_directory(le))
            
            path_layout = QHBoxLayout()
            path_layout.addWidget(line_edit)
            path_layout.addWidget(browse_button)
            
            platform_layout.addRow(f"{tab_name} Directory:", path_layout)
            self.platform_paths[attr_name] = line_edit
        
        platform_group.setLayout(platform_layout)
        scroll_layout.addWidget(platform_group)
        
        # Add any additional space at the bottom
        scroll_layout.addStretch(1)
        
        # Set the scroll content
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Create OK and Cancel buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.save_settings)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        main_layout.addLayout(button_layout)
    
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
    
    def save_settings(self):
        """Save all settings and close dialog"""
        try:
            # Save PS3Dec path
            self.settings_manager.update_setting('ps3dec_binary', self.ps3dec_path.text())
            
            # Save extractps3iso binary path
            self.settings_manager.update_setting('extractps3iso_binary', self.extractps3iso_path.text())
            
            # Save processing directory
            self.settings_manager.update_setting('processing_dir', self.processing_path.text())
            
            # Save all platform paths
            for attr_name, line_edit in self.platform_paths.items():
                # Ensure the directory exists
                directory = line_edit.text()
                if directory and not os.path.exists(directory):
                    try:
                        os.makedirs(directory, exist_ok=True)
                    except Exception as e:
                        QMessageBox.warning(
                            self, 
                            "Error Creating Directory", 
                            f"Could not create directory: {directory}\nError: {str(e)}"
                        )
                
                # Update the setting
                self.settings_manager.update_setting(attr_name, directory)
            
            # Accept and close the dialog
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Error Saving Settings", 
                f"An error occurred while saving settings:\n{str(e)}"
            )
