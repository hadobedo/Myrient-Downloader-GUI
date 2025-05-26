import os
import pickle
import signal
import platform
import urllib.parse
import shutil
import zipfile
import glob
import re
import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
    QPushButton, QLineEdit, QListWidget, QLabel, QCheckBox, 
    QFileDialog, QDialog, QGroupBox, QProgressBar, QTabWidget, QAbstractItemView,
    QMessageBox, QListWidgetItem, QFormLayout, QDialogButtonBox, QGridLayout
)
from PyQt5.QtCore import Qt, QSettings, QThread, pyqtSignal, QEventLoop
from PyQt5.QtGui import QFont, QBrush, QColor

from gui.output_window import OutputWindow
from gui.check_prereq_binaries_dialog import PrereqBinaryDialog
from core.settings import SettingsManager
from core.downloader import Downloader
from core.state_manager import StateManager
from core.config_manager import ConfigManager
from core.processor_factory import ProcessorFactory
from threads.download_threads import GetSoftwareListThread, DownloadThread
from threads.processing_threads import UnzipRunner, CommandRunner, SplitIsoThread, SplitPkgThread


class SettingsDialog(QDialog):
    def __init__(self, settings_manager, config_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings_manager = settings_manager
        self.config_manager = config_manager

        # Use a grid layout instead of form layout for columns
        self.layout = QGridLayout(self)
        self.inputs = {}

        # Add PS3Dec Binary and extractps3iso Binary on the same row
        row = 0
        self.layout.addWidget(QLabel("PS3Dec Binary"), row, 0)
        ps3dec_le = QLineEdit(str(getattr(settings_manager, "ps3dec_binary", "")))
        self.layout.addWidget(ps3dec_le, row, 1)
        self.inputs["ps3dec_binary"] = ps3dec_le
        
        # Add browse button for PS3Dec Binary
        ps3dec_browse_btn = QPushButton("Browse")
        ps3dec_browse_btn.clicked.connect(lambda: self.browse_file(ps3dec_le))
        self.layout.addWidget(ps3dec_browse_btn, row, 2)

        # Add extractps3iso Binary on same row
        self.layout.addWidget(QLabel("extractps3iso Binary"), row, 3)
        extractps3iso_le = QLineEdit(str(getattr(settings_manager, "extractps3iso_binary", "")))
        self.layout.addWidget(extractps3iso_le, row, 4)
        self.inputs["extractps3iso_binary"] = extractps3iso_le
        
        # Add browse button for extractps3iso Binary
        extractps3iso_browse_btn = QPushButton("Browse")
        extractps3iso_browse_btn.clicked.connect(lambda: self.browse_file(extractps3iso_le))
        self.layout.addWidget(extractps3iso_browse_btn, row, 5)
        row += 1

        # Hardcoded platforms and their settings keys (excluding the binaries which we've already added)
        hardcoded = [
            ("PS3 ISO Directory", "ps3iso_dir"),
            ("PSN PKG Directory", "psn_pkg_dir"),
            ("PSN RAP Directory", "psn_rap_dir"),
            ("PS2 ISO Directory", "ps2iso_dir"),
            ("PSX ISO Directory", "psxiso_dir"),
            ("PSP ISO Directory", "pspiso_dir"),
        ]

        # First column (left side)
        for i, (label, key) in enumerate(hardcoded[:3]):
            value = getattr(settings_manager, key, "")
            self.layout.addWidget(QLabel(label), row + i, 0)
            le = QLineEdit(str(value))
            self.layout.addWidget(le, row + i, 1)
            self.inputs[key] = le
            
            # Add browse button
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(lambda checked=False, le=le: self.browse_directory(le))
            self.layout.addWidget(browse_btn, row + i, 2)

        # Second column (right side)
        for i, (label, key) in enumerate(hardcoded[3:]):
            value = getattr(settings_manager, key, "")
            self.layout.addWidget(QLabel(label), row + i, 3)
            le = QLineEdit(str(value))
            self.layout.addWidget(le, row + i, 4)
            self.inputs[key] = le
            
            # Add browse button
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(lambda checked=False, le=le: self.browse_directory(le))
            self.layout.addWidget(browse_btn, row + i, 5)

        row += max(len(hardcoded[:3]), len(hardcoded[3:]))

        # Dynamically add new platforms from config (excluding hardcoded)
        known = {"ps3", "ps2", "psx", "psp", "psn"}
        dynamic_platforms = [(platform_id, data) for platform_id, data in config_manager.get_platforms().items() 
                             if platform_id not in known]
        
        # Split dynamic platforms into two columns
        first_half = dynamic_platforms[:len(dynamic_platforms)//2 + len(dynamic_platforms)%2]
        second_half = dynamic_platforms[len(dynamic_platforms)//2 + len(dynamic_platforms)%2:]
        
        # First column for dynamic platforms
        for i, (platform_id, data) in enumerate(first_half):
            key = f"{platform_id}_dir"
            label = f"{platform_id.upper()} Directory"
            value = getattr(settings_manager, key, f"MyrientDownloads/{platform_id.upper()}")
            self.layout.addWidget(QLabel(label), row + i, 0)
            le = QLineEdit(str(value))
            self.layout.addWidget(le, row + i, 1)
            self.inputs[key] = le
            
            # Add browse button
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(lambda checked=False, le=le: self.browse_directory(le))
            self.layout.addWidget(browse_btn, row + i, 2)

        # Second column for dynamic platforms
        for i, (platform_id, data) in enumerate(second_half):
            key = f"{platform_id}_dir"
            label = f"{platform_id.upper()} Directory"
            value = getattr(settings_manager, key, f"MyrientDownloads/{platform_id.upper()}")
            self.layout.addWidget(QLabel(label), row + i, 3)
            le = QLineEdit(str(value))
            self.layout.addWidget(le, row + i, 4)
            self.inputs[key] = le
            
            # Add browse button
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(lambda checked=False, le=le: self.browse_directory(le))
            self.layout.addWidget(browse_btn, row + i, 5)

        row += max(len(first_half), len(second_half))

        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons, row, 0, 1, 6)  # span all columns
        
    def browse_directory(self, line_edit):
        """Open a directory selection dialog and update the line edit with the selected path."""
        current_path = line_edit.text()
        directory = QFileDialog.getExistingDirectory(self, "Select Directory", current_path)
        if directory:
            line_edit.setText(directory)
    
    def browse_file(self, line_edit):
        """Open a file selection dialog and update the line edit with the selected file path."""
        current_path = line_edit.text()
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select PS3Dec Binary",
            current_path,
            "Executables (*.exe);;All Files (*)" if os.name == 'nt' else "All Files (*)"
        )
        if file_path:
            line_edit.setText(file_path)

    def get_settings(self):
        return {k: v.text() for k, v in self.inputs.items()}


class GUIDownloader(QWidget):
    """The main GUI window for the Myrient Downloader application."""
    
    def __init__(self):
        super().__init__()
        
        # Create output window first to capture all output
        self.output_window = OutputWindow(self)
        self.output_window.set_as_stdout()  # Redirect stdout early in initialization
        
        # Initialize configuration manager first
        self.config_manager = ConfigManager()
        
        # Pass config_manager to SettingsManager to avoid duplicate initialization
        self.settings_manager = SettingsManager(config_manager=self.config_manager)
        
        # For queue handling
        self.processed_items = 0
        self.total_items = 0
        self.original_queue = []
        
        # For pause/resume functionality
        self.is_paused = False
        self.current_operation = None
        self.current_item = None  # Will store the original name
        self.current_position = None
        self.current_file_path = None
        
        # Get platforms from configuration
        self.platforms = self.config_manager.get_platforms()
        
        # Load software lists
        self.init_software_lists()
        
        # Load the queue
        self.load_queue()
        
        # Initialize the UI
        self.initUI()
        
        # Add the entries from queue to the UI with formatting
        for item_text in self.queue:
            # Create an item with rich text formatting 
            self.add_formatted_item_to_queue(item_text)
        
        # Add signal handler for SIGINT
        signal.signal(signal.SIGINT, self.closeEvent)
        
        # Check if we need to resume a paused download
        self.check_for_paused_download()
    
    def init_software_lists(self):
        """Initialize software lists and start download threads."""
        # Initialize platform lists and threads
        self.platform_lists = {}
        self.platform_threads = {}
        
        # Create initial lists with loading message
        for platform_id in self.platforms.keys():
            self.platform_lists[platform_id] = ['Loading... this will take a moment']
        
        # Start threads to download software lists
        for platform_id, data in self.platforms.items():
            json_filename = f"{platform_id}_filelist.json"
            thread = self.load_software_list(
                data['url'],
                json_filename,
                lambda items, pid=platform_id: self.set_platform_list(pid, items)
            )
            self.platform_threads[platform_id] = thread
            thread.start()

    def load_software_list(self, url, json_filename, setter):
        """Create and return a thread to load a software list."""
        thread = GetSoftwareListThread(url, json_filename)
        thread.signal.connect(setter)
        return thread
    
    def set_platform_list(self, platform_id, items):
        """Set the list of items for a specific platform."""
        self.platform_lists[platform_id] = items
        
        # Find the correct tab index for this platform and update it
        for i in range(self.result_list.count()):
            if self.result_list.tabText(i) == self.platforms[platform_id]['tab_name']:
                self.result_list.widget(i).clear()
                self.result_list.widget(i).addItems(items)
                break

    def load_queue(self):
        """Load the download queue from file."""
        # Set path to queue file in config directory
        config_dir = "config"
        queue_file = os.path.join(config_dir, "queue.txt")
        
        # First check if the new location exists
        if os.path.exists(queue_file):
            try:
                with open(queue_file, 'rb') as file:
                    self.queue = pickle.load(file)
            except Exception as e:
                print(f"Error loading {queue_file}: {e}. Starting with an empty queue.")
                self.queue = []
        else:
            # Check for old file in root directory
            old_queue_file = "queue.txt"
            if os.path.exists(old_queue_file):
                try:
                    # Load from old location
                    with open(old_queue_file, 'rb') as file:
                        self.queue = pickle.load(file)
                    
                    # Ensure config directory exists
                    os.makedirs(config_dir, exist_ok=True)
                    
                    # Save to new location
                    with open(queue_file, 'wb') as file:
                        pickle.dump(self.queue, file)
                    
                    # Remove old file after successful migration
                    os.remove(old_queue_file)
                    print(f"Migrated queue from root to {queue_file}")
                except Exception as e:
                    print(f"Error migrating queue: {str(e)}")
                    self.queue = []
            else:
                self.queue = []
    
    def save_queue(self):
        """Save the current queue to file."""
        # Ensure config directory exists
        config_dir = "config"
        os.makedirs(config_dir, exist_ok=True)
        
        # Save to new location in config directory
        queue_file = os.path.join(config_dir, "queue.txt")
        
        with open(queue_file, 'wb') as file:
            # Save original names (Qt.UserRole data)
            queue_items = []
            for i in range(self.queue_list.count()):
                item = self.queue_list.item(i)
                # Get original name from UserRole if it exists, otherwise use displayed text
                if item.data(Qt.UserRole):
                    queue_items.append(item.data(Qt.UserRole))
                else:
                    queue_items.append(item.text())
            pickle.dump(queue_items, file)

    def initUI(self):
        """Initialize the user interface."""
        vbox = QVBoxLayout()

        # Add a header for the software list
        iso_list_header = QLabel('Software')
        vbox.addWidget(iso_list_header)

        # Create a search box
        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText('Search...')
        self.search_box.textChanged.connect(self.update_results)
        vbox.addWidget(self.search_box)

        # Create a list for results (software list)
        self.result_list = QTabWidget(self)
        
        # Create tabs based on the platforms configuration
        for platform_id, data in self.platforms.items():
            list_widget = QListWidget()
            list_widget.addItems(self.platform_lists[platform_id])
            list_widget.itemSelectionChanged.connect(self.update_add_to_queue_button)
            list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.result_list.addTab(list_widget, data['tab_name'])
        
        self.result_list.currentChanged.connect(self.update_add_to_queue_button)
        # Connect tab change to update checkboxes visibility
        self.result_list.currentChanged.connect(self.update_checkboxes_for_platform)
        vbox.addWidget(self.result_list)

        # Connect the itemSelectionChanged signal to the update_add_to_queue_button method
        for i in range(self.result_list.count()):
            self.result_list.widget(i).itemSelectionChanged.connect(self.update_add_to_queue_button)

        # Allow selecting multiple items
        for i in range(self.result_list.count()):
            self.result_list.widget(i).setSelectionMode(QAbstractItemView.ExtendedSelection)

        # Create a horizontal box layout
        hbox = QHBoxLayout()

        # Create a button to add to queue
        self.add_to_queue_button = QPushButton('Add to Queue', self)
        self.add_to_queue_button.clicked.connect(self.add_to_queue)
        self.add_to_queue_button.setEnabled(False)  # Disable button initially
        hbox.addWidget(self.add_to_queue_button)

        # Create a button to remove from queue
        self.remove_from_queue_button = QPushButton('Remove from Queue', self)
        self.remove_from_queue_button.clicked.connect(self.remove_from_queue)
        self.remove_from_queue_button.setEnabled(False)  # Disable button initially
        hbox.addWidget(self.remove_from_queue_button)

        # Add the horizontal box layout to the vertical box layout
        vbox.addLayout(hbox)

        # Add a header for the Queue
        queue_header = QLabel('Queue')
        vbox.addWidget(queue_header)

        # Create queue list with visual formatting instead of HTML
        self.queue_list = QListWidget(self)
        self.queue_list.setSelectionMode(QAbstractItemView.MultiSelection)  
        self.queue_list.itemSelectionChanged.connect(self.update_remove_from_queue_button)
        self.queue_list.setWordWrap(True)
        
        vbox.addWidget(self.queue_list)

        # Create a grid layout for the options
        options_layout = QVBoxLayout()

        # Add headers and options
        self.create_options_grid(options_layout)

        # Create a group box to contain the options layout
        group_box = QGroupBox()
        group_box.setLayout(options_layout)
        vbox.addWidget(group_box)

        # Create buttons for settings and start
        self.settings_button = QPushButton('Settings', self)
        self.settings_button.clicked.connect(self.open_settings)
        vbox.addWidget(self.settings_button)

        self.start_pause_button = QPushButton('Start', self)
        self.start_pause_button.clicked.connect(self.start_or_pause_download)
        vbox.addWidget(self.start_pause_button)

        # Add output window and progress indicators
        output_window_header = QLabel('Logs')
        vbox.addWidget(output_window_header)
        
        # Use existing output_window instead of creating a new one
        vbox.addWidget(self.output_window)

        queue_header = QLabel('Progress')
        vbox.addWidget(queue_header)

        self.progress_bar = QProgressBar(self)
        vbox.addWidget(self.progress_bar)

        # Create horizontal layout for download status information
        download_status_layout = QHBoxLayout()
        
        # Left side for speed and ETA
        status_left = QVBoxLayout()
        
        download_info_header = QLabel('Download Speed & ETA')
        status_left.addWidget(download_info_header)
        
        self.download_speed_label = QLabel(self)
        status_left.addWidget(self.download_speed_label)
        
        self.download_eta_label = QLabel(self)
        status_left.addWidget(self.download_eta_label)
        
        download_status_layout.addLayout(status_left)
        
        # Add stretch to push the file size to the right
        download_status_layout.addStretch()
        
        # Right side for file size
        status_right = QVBoxLayout()
        
        filesize_header = QLabel('File Size')
        filesize_header.setAlignment(Qt.AlignRight)
        status_right.addWidget(filesize_header)
        
        self.download_size_label = QLabel(self)
        self.download_size_label.setAlignment(Qt.AlignRight)
        status_right.addWidget(self.download_size_label)
        
        # Add an empty label to align with ETA label
        empty_label = QLabel(self)
        status_right.addWidget(empty_label)
        
        download_status_layout.addLayout(status_right)
        
        # Add the horizontal layout to the main vertical layout
        vbox.addLayout(download_status_layout)

        self.setLayout(vbox)

        self.setWindowTitle('Myrient Downloader')
        self.resize(800, 600)
        
        # Initialize checkbox visibility based on the current platform
        self.update_checkboxes_for_platform()
        
        self.show()
    
    def create_options_grid(self, parent_layout):
        """Create the options layout with sections for general and platform-specific options."""
        # Create group box for general options
        general_options_group = QGroupBox("General Options")
        # Add padding to the group box title with style sheet
        general_options_group.setStyleSheet("QGroupBox { padding-top: 15px; margin-top: 5px; }")
        general_layout = QVBoxLayout()
        
        # Create a grid layout for general options
        general_grid = QGridLayout()
        general_grid.setHorizontalSpacing(20)  # Space between columns
        general_grid.setVerticalSpacing(10)    # Space between rows
        
        # Add general options - Keep related options next to each other
        row = 0
        self.split_checkbox = QCheckBox('Split for FAT32 (if > 4GB)', self)
        self.split_checkbox.setChecked(self.settings_manager.split_large_files)
        general_grid.addWidget(self.split_checkbox, row, 0)
        
        self.keep_unsplit_dec_checkbox = QCheckBox('Keep unsplit file', self)
        self.keep_unsplit_dec_checkbox.setChecked(self.settings_manager.keep_unsplit_file)
        general_grid.addWidget(self.keep_unsplit_dec_checkbox, row, 1)
        
        # Add the grid layout to the main layout
        general_layout.addLayout(general_grid)
        general_options_group.setLayout(general_layout)
        parent_layout.addWidget(general_options_group)
        
        # Create group box for platform-specific options
        self.platform_options_group = QGroupBox("Platform-Specific Options")
        self.platform_options_group.setStyleSheet("QGroupBox { padding-top: 15px; margin-top: 5px; }")
        platform_layout = QVBoxLayout()
        
        # PS3 specific options
        self.ps3_options_widget = QWidget()
        ps3_layout = QVBoxLayout(self.ps3_options_widget)
        ps3_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create a grid layout for PS3 options with better organization and visual hierarchy
        ps3_grid = QGridLayout()
        ps3_grid.setHorizontalSpacing(20)
        ps3_grid.setVerticalSpacing(10)
        
        # First row - main decrypt checkbox with its direct related options
        row = 0
        self.decrypt_checkbox = QCheckBox('Decrypt using PS3Dec', self)
        self.decrypt_checkbox.setChecked(self.settings_manager.decrypt_iso)
        ps3_grid.addWidget(self.decrypt_checkbox, row, 0)
        
        self.keep_enc_checkbox = QCheckBox('Keep encrypted PS3 ISO', self)
        self.keep_enc_checkbox.setChecked(self.settings_manager.keep_encrypted_iso)
        ps3_grid.addWidget(self.keep_enc_checkbox, row, 1)
        
        # Second row - Extract ISO contents checkbox
        row += 1
        self.extract_ps3_checkbox = QCheckBox('Extract ISO contents', self)
        self.extract_ps3_checkbox.setChecked(self.settings_manager.extract_ps3_iso)
        ps3_grid.addWidget(self.extract_ps3_checkbox, row, 0, 1, 2)  # Span 2 columns
        
        # Third row - Keep decrypted ISO checkbox
        row += 1
        self.keep_decrypted_iso_checkbox = QCheckBox('Keep decrypted ISO after extraction', self)
        self.keep_decrypted_iso_checkbox.setChecked(self.settings_manager.keep_decrypted_iso_after_extraction)
        ps3_grid.addWidget(self.keep_decrypted_iso_checkbox, row, 0, 1, 2)  # Span 2 columns
        
        # Separate row just for the dkey checkbox with clear separation
        row += 1
        # Add a small spacer before the dkey checkbox for visual separation
        ps3_grid.setRowMinimumHeight(row, 5)  # 5px spacing
        
        row += 1
        self.keep_dkey_checkbox = QCheckBox('Keep PS3 ISO dkey file', self)
        self.keep_dkey_checkbox.setChecked(self.settings_manager.keep_dkey_file)
        # Place in first column, and make it span two columns for clarity
        ps3_grid.addWidget(self.keep_dkey_checkbox, row, 0, 1, 2)
    
        # Add PS3 grid to PS3 layout
        ps3_layout.addLayout(ps3_grid)
        platform_layout.addWidget(self.ps3_options_widget)
        
        # PSN specific options
        self.psn_options_widget = QWidget()
        psn_layout = QGridLayout(self.psn_options_widget)
        psn_layout.setContentsMargins(0, 0, 0, 0)
        
        self.split_pkg_checkbox = QCheckBox('Split PKG', self)
        self.split_pkg_checkbox.setChecked(self.settings_manager.split_pkg)
        psn_layout.addWidget(self.split_pkg_checkbox, 0, 0)
        
        platform_layout.addWidget(self.psn_options_widget)
        
        # Add stretch to push everything to the top
        platform_layout.addStretch()
        
        self.platform_options_group.setLayout(platform_layout)
        parent_layout.addWidget(self.platform_options_group)
        
        # Connect signals for all checkboxes AFTER all are created
        # Connect General group checkboxes
        self.split_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('split_large_files', state))
        self.keep_unsplit_dec_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('keep_unsplit_file', state))
        
        # Connect PS3 group checkboxes
        self.decrypt_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('decrypt_iso', state))
        self.extract_ps3_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('extract_ps3_iso', state))
        self.keep_enc_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('keep_encrypted_iso', state))
        self.keep_dkey_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('keep_dkey_file', state))
        self.keep_decrypted_iso_checkbox.stateChanged.connect(lambda state: 
            self.handle_checkbox_change('keep_decrypted_iso_after_extraction', state))
    
        # Connect PSN group checkbox
        self.split_pkg_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('split_pkg', state))
        
        # Set initial visibility states for all checkboxes
        self.update_all_checkbox_states()
        
        # Initially hide platform-specific options - they will be shown based on platform
        self.ps3_options_widget.setVisible(False)
        self.psn_options_widget.setVisible(False)

    def handle_checkbox_change(self, setting_name, state):
        """Handle checkbox state changes in a centralized way."""
        try:
            # Convert Qt.CheckState to boolean
            checked = (state == Qt.Checked)
            
            # Special case: if turning on extract_ps3_iso, check if we have extractps3iso binary
            if setting_name == 'extract_ps3_iso' and checked:
                if not os.path.isfile(self.settings_manager.extractps3iso_binary):
                    # Need to check/download extractps3iso
                    dialog = PrereqBinaryDialog("extractps3iso", self)
                    if dialog.exec_():
                        # User wants to download it
                        if not self.settings_manager.download_extractps3iso():
                            # Failed to download
                            QMessageBox.warning(
                                self, 
                                "Download Failed", 
                                "Failed to download extractps3iso. ISO extraction will not be available."
                            )
                            # Uncheck the checkbox since we can't use this feature
                            self.extract_ps3_checkbox.blockSignals(True)
                            self.extract_ps3_checkbox.setChecked(False)
                            self.extract_ps3_checkbox.blockSignals(False)
                            checked = False
                    else:
                        # User canceled download
                        self.extract_ps3_checkbox.blockSignals(True)
                        self.extract_ps3_checkbox.setChecked(False)
                        self.extract_ps3_checkbox.blockSignals(False)
                        checked = False
            
            # Save the setting
            self.settings_manager.update_setting(setting_name, checked)
            
            # Update visibility and state of dependent checkboxes
            self.update_all_checkbox_states()
        except Exception as e:
            print(f"Error handling checkbox change for {setting_name}: {str(e)}")

    def update_all_checkbox_states(self):
        """Update visibility and state of all checkboxes based on dependencies."""
        try:
            # Get current states
            decrypt_checked = self.decrypt_checkbox.isChecked()
            extract_checked = self.extract_ps3_checkbox.isChecked()
            split_checked = self.split_checkbox.isChecked()
            
            # ------ PS3 Specific Options ------
            
            # Rule 1: Everything except the dkey checkbox depends on decrypt being checked
            self.keep_enc_checkbox.setVisible(decrypt_checked)
            self.extract_ps3_checkbox.setVisible(decrypt_checked)
            
            # Rule 2: Keep decrypted ISO checkbox depends on both decrypt AND extract
            self.keep_decrypted_iso_checkbox.setVisible(decrypt_checked and extract_checked)
            
            # Rule 3: If decrypt is unchecked, ensure extract is also unchecked
            if not decrypt_checked and extract_checked:
                self.extract_ps3_checkbox.blockSignals(True)
                self.extract_ps3_checkbox.setChecked(False)
                self.extract_ps3_checkbox.blockSignals(False)
                # Update setting directly without triggering signals
                self.settings_manager.update_setting('extract_ps3_iso', False)
            
            # ------ General Options ------
            
            # Split file related options
            self.keep_unsplit_dec_checkbox.setVisible(split_checked)
            
        except Exception as e:
            print(f"Error updating checkbox states: {str(e)}")

    def update_checkboxes_for_platform(self):
        """Update which checkboxes are visible based on the active platform tab."""
        try:
            current_tab = self.result_list.currentIndex()
            platform_ids = list(self.platforms.keys())
            
            # Default visibility settings
            show_ps3dec = False
            show_pkg_split = False
            
            # Get current platform ID
            if 0 <= current_tab < len(platform_ids):
                current_platform_id = platform_ids[current_tab]
                
                # Get checkbox settings for this platform
                checkbox_settings = self.config_manager.get_platform_checkbox_settings(current_platform_id)
                show_ps3dec = checkbox_settings.get('show_ps3dec', False)
                show_pkg_split = checkbox_settings.get('show_pkg_split', False)
            
            # Update visibility of platform-specific options section
            has_platform_specific_options = show_ps3dec or show_pkg_split
            self.platform_options_group.setVisible(has_platform_specific_options)
            
            # Update visibility based on settings
            self.ps3_options_widget.setVisible(show_ps3dec)
            self.psn_options_widget.setVisible(show_pkg_split)
            
            # After changing platform visibility, update specific checkbox states
            self.update_all_checkbox_states()
        except Exception as e:
            print(f"Error updating checkboxes for platform: {str(e)}")

    def update_results(self):
        """Filter the software list based on the search text."""
        search_term = self.search_box.text().lower().split()
        
        # Get the current platform based on the active tab
        current_tab = self.result_list.currentIndex()
        platform_ids = list(self.platforms.keys())
        if 0 <= current_tab < len(platform_ids):
            current_platform = platform_ids[current_tab]
            list_to_search = self.platform_lists[current_platform]
            
            filtered_list = [item for item in list_to_search if all(word in item.lower() for word in search_term)]
            
            # Clear the current list widget and add the filtered items
            current_list_widget = self.result_list.currentWidget()
            current_list_widget.clear()
            current_list_widget.addItems(filtered_list)
    
    def update_add_to_queue_button(self):
        """Enable or disable the add to queue button based on selection."""
        self.add_to_queue_button.setEnabled(bool(self.result_list.currentWidget().selectedItems()))

    def update_remove_from_queue_button(self):
        """Enable or disable the remove from queue button based on selection."""
        self.remove_from_queue_button.setEnabled(bool(self.queue_list.selectedItems()))
    
    def add_to_queue(self):
        """Add selected items to the download queue."""
        selected_items = self.result_list.currentWidget().selectedItems()
        current_tab = self.result_list.currentIndex()
        platform_ids = list(self.platforms.keys())
        
        if 0 <= current_tab < len(platform_ids):
            current_platform = platform_ids[current_tab]
            platform_name = current_platform.upper()
            
            for item in selected_items:
                item_text = item.text()
                # Format item with platform prefix
                formatted_text = f"({platform_name}) {item_text}"
                
                # Check if item is already in queue by comparing original names
                already_in_queue = False
                for i in range(self.queue_list.count()):
                    queue_item = self.queue_list.item(i)
                    # Compare with original name stored in UserRole
                    if queue_item.data(Qt.UserRole) == formatted_text:
                        already_in_queue = True
                        break
                
                if not already_in_queue:
                    self.add_formatted_item_to_queue(formatted_text)

        # Save the queue to 'queue.txt'
        self.save_queue()
    
    def remove_from_queue(self):
        """Remove selected items from the download queue."""
        selected_items = self.queue_list.selectedItems()
        if not selected_items:
            return
        
        items_to_remove = []
        
        for item in selected_items:
            # Get the original name from the item's data
            original_name = item.data(Qt.UserRole) if item.data(Qt.UserRole) else item.text()
            
            # Check if this is a download in progress or paused
            is_current_download = (self.current_item == original_name and 
                                  self.current_file_path and 
                                  os.path.exists(self.current_file_path))
            
            # If it's a download in progress or paused, show a confirmation dialog
            if is_current_download:
                # Get file size for the confirmation message
                try:
                    # Ensure the file still exists before getting its size
                    if os.path.exists(self.current_file_path):
                        file_size = os.path.getsize(self.current_file_path)
                        size_str = self.format_file_size(file_size)
                    else:
                        # File may have been deleted already
                        size_str = "unknown size (file not found)"
                    
                    status = "paused" if self.is_paused else "in progress"
                    
                    # Show confirmation dialog with options to keep or delete the file
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Question)
                    msg_box.setWindowTitle("Confirm Removal")
                    msg_box.setText(f"'{self.get_filename_from_queue_item(original_name)}' has a {status} download ({size_str}).")
                    msg_box.setInformativeText("Do you want to delete the incomplete download file?")
                    
                    delete_btn = msg_box.addButton("Delete File", QMessageBox.YesRole)
                    keep_btn = msg_box.addButton("Keep File", QMessageBox.NoRole)
                    cancel_btn = msg_box.addButton(QMessageBox.Cancel)
                    
                    msg_box.exec_()
                    
                    if msg_box.clickedButton() == cancel_btn:
                        # User canceled, skip this item
                        continue
                    
                    if msg_box.clickedButton() == delete_btn:
                        # User chose to delete the partial download
                        if os.path.exists(self.current_file_path):
                            try:
                                os.remove(self.current_file_path)
                                position = self.current_position if self.current_position else ""
                                self.output_window.append(f"({position}) Deleted incomplete download: {self.current_file_path}\n")
                            except Exception as e:
                                self.output_window.append(f"Error deleting file: {str(e)}\n")
                        else:
                            position = self.current_position if self.current_position else ""
                            self.output_window.append(f"({position}) File already deleted: {self.current_file_path}\n")
                    else:
                        # User chose to keep the file
                        self.output_window.append(f"Kept incomplete download: {self.current_file_path}")
                
                except Exception as e:
                    self.output_window.append(f"Error getting file info: {str(e)}\n")
                    # Continue with dialog without size info
                # If this is the current operation, reset state
                if self.current_item == original_name:
                    # Reset pause state if this was a paused download
                    if self.is_paused:
                        StateManager.clear_pause_state()
                        self.is_paused = False
                    
                    # Stop any running download thread
                    if hasattr(self, 'download_thread') and self.download_thread:
                        self.download_thread.stop()
                    
                    # Reset current state
                    self.current_item = None
                    self.current_operation = None
                    self.current_file_path = None
                    
                    # Update button text
                    self.start_pause_button.setText('Start')
                    
                    # Reset progress indicators
                    self.progress_bar.reset()
                    self.download_speed_label.setText("")
                    self.download_eta_label.setText("")
                
                # Mark item for removal
                items_to_remove.append(item)
            else:
                # Regular item, mark for removal
                items_to_remove.append(item)
        
        # Remove all marked items
        for item in items_to_remove:
            self.queue_list.takeItem(self.queue_list.row(item))
        
        # Save the updated queue
        self.save_queue()
        
        # Update button state
        self.update_remove_from_queue_button()
    
    def open_settings(self):
        """Open the settings dialog."""
        dlg = SettingsDialog(self.settings_manager, self.config_manager, self)
        if dlg.exec_():
            new_settings = dlg.get_settings()
            for key, value in new_settings.items():
                self.settings_manager.update_setting(key, value)
            QMessageBox.information(self, "Settings", "Settings updated successfully.")
            # Optionally, update directories on disk if changed
            self.settings_manager.create_directories()
    
    def check_for_paused_download(self):
        """Check if there is a paused download to resume and restore it to the queue."""
        pause_state = StateManager.load_pause_state()
        if not pause_state:
            return
            
        # Remove the message about restored download
        # self.output_window.append(f"Restored paused download: {pause_state['current_item']} ({pause_state['operation']})")
        
        # Clear the current queue
        self.queue_list.clear()
        
        # Add the current paused item first with (PAUSED) status
        current_item_text = pause_state['current_item']
        paused_item = self.add_formatted_item_to_queue(current_item_text)
        
        # Update the item to show it's paused with yellow highlight
        paused_text = f"{current_item_text} (PAUSED)"
        paused_item.setText(paused_text)
        font = QFont()
        font.setBold(True)
        paused_item.setFont(font)
        paused_item.setForeground(QBrush(QColor(255, 215, 0)))  # Gold/Yellow color
        
        # Add any remaining items from the saved queue
        if 'remaining_queue' in pause_state and isinstance(pause_state['remaining_queue'], list):
            for item_text in pause_state['remaining_queue']:
                if item_text != current_item_text:  # Avoid duplicates
                    self.add_formatted_item_to_queue(item_text)
        
        # Set up the state from the saved data
        self.current_item = pause_state['current_item']
        self.current_operation = pause_state['operation']
        self.current_position = pause_state['queue_position']
        self.current_file_path = pause_state['file_path']
        self.processed_items = pause_state['processed_items']
        self.total_items = pause_state['total_items']
        
        # Make sure the queue position makes sense
        if self.total_items < self.queue_list.count() + self.processed_items - 1:
            # Update the total if it's inconsistent
            self.total_items = self.queue_list.count() + self.processed_items - 1
    
        # Set the paused state and update the button to show "Resume"
        self.is_paused = True
        self.start_pause_button.setText('Resume')
        
        # Save the queue to ensure it's current
        self.save_queue()

    def closeEvent(self, event):
        """Handle the close event."""
        try:
            # Check if there's an active download or operation
            has_active_operation = (hasattr(self, 'download_thread') and self.download_thread and 
                                   self.download_thread.isRunning() and not self.is_paused)
            
            # If there's an active operation, pause it first
            if has_active_operation:
                self.output_window.append("Pausing active operation before exit...")
                self.pause_download()
                
                # Give a brief moment to the pause to register
                from PyQt5.QtCore import QTimer
                loop = QEventLoop()
                QTimer.singleShot(500, loop.quit)  # Wait 500ms for pause to complete
                loop.exec_()
            
            # Now proceed with normal shutdown
            self._stop_all_threads()
            
            if self.is_paused:
                # Get the remaining queue items using original names
                remaining_items = []
                for i in range(self.queue_list.count()):
                    item = self.queue_list.item(i)
                    if item.data(Qt.UserRole):
                        remaining_items.append(item.data(Qt.UserRole))
                    else:
                        remaining_items.append(item.text())
                
                StateManager.save_pause_state(
                    self.current_item,  # original name 
                    self.current_position, 
                    self.current_operation, 
                    self.current_file_path, 
                    self.processed_items, 
                    self.total_items,
                    remaining_items
                )
            else:
                # Not paused, make sure any old pause state is cleared
                StateManager.clear_pause_state()
            
            # Save the queue to 'queue.txt'
            self.save_queue()
            
            # Restore stdout/stderr to their original values
            if hasattr(self, 'output_window'):
                self.output_window.restore_stdout()
            
        except Exception as e:
            print(f"Error during shutdown: {str(e)}")
            
        event.accept()
        
        # Schedule application quit after a short delay to allow cleanup
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, QApplication.instance().quit)
    
    def _stop_all_threads(self):
        """Stop all running threads gracefully."""
        # Stop download thread if running
        if hasattr(self, 'download_thread') and self.download_thread:
            try:
                if self.download_thread.isRunning():
                    # Make sure to pause first if not already paused
                    if not self.is_paused and self.current_operation == 'download':
                        self.download_thread.pause()
                    
                    # Now stop the thread
                    self.download_thread.stop()
                    self.download_thread.wait(1000)  # Wait up to 1 second
            except Exception as e:
                print(f"Error stopping download thread: {str(e)}")
        
        # Stop unzip runner if running
        if hasattr(self, 'unzip_runner') and self.unzip_runner:
            try:
                if self.unzip_runner.isRunning():
                    # Make sure to pause first if not already paused
                    if not self.is_paused and self.current_operation == 'unzip':
                        self.unzip_runner.pause()
                        
                    # Now stop the thread
                    self.unzip_runner.stop()
                    self.unzip_runner.wait(1000)  # Wait up to 1 second
            except Exception as e:
                print(f"Error stopping unzip thread: {str(e)}")
        
        # Stop platform threads if running
        if hasattr(self, 'platform_threads'):
            for platform_id, thread in self.platform_threads.items():
                try:
                    if thread and thread.isRunning():
                        thread.wait(500)  # Wait up to 0.5 seconds
                except Exception as e:
                    print(f"Error stopping platform thread for {platform_id}: {str(e)}")
    
    def start_or_pause_download(self):
        """Handle start or pause button click based on current state."""
        button_text = self.start_pause_button.text()
        
        if button_text == 'Start':
            self.start_download()
        elif button_text == 'Pause':
            self.pause_download()
        elif button_text == 'Resume':
            self.resume_download()

    def start_download(self):
        """Start downloading the selected items."""
        # Disable the GUI buttons except pause
        self.settings_button.setEnabled(False)
        self.add_to_queue_button.setEnabled(False)
        self.remove_from_queue_button.setEnabled(False)
        self.decrypt_checkbox.setEnabled(False)
        self.split_checkbox.setEnabled(False)
        self.keep_dkey_checkbox.setEnabled(False)
        self.keep_enc_checkbox.setEnabled(False)
        self.keep_unsplit_dec_checkbox.setEnabled(False)
        self.split_pkg_checkbox.setEnabled(False)
        self.extract_ps3_checkbox.setEnabled(False)
        self.keep_decrypted_iso_checkbox.setEnabled(False)  # Add this line
        
        # Change button to Pause
        self.start_pause_button.setText('Pause')
        
        # Reset pause state
        self.is_paused = False
        
        is_resuming_session = bool(self.current_item) # True if self.current_item was set by check_for_paused_download

        try:
            # Get the total number of items in the queue only if we're starting fresh
            if not is_resuming_session:  # Not resuming / Fresh start
                # Reset counters
                self.processed_items = 0 # Will be incremented before processing the first item
                self.total_items = self.queue_list.count()
                self.original_queue = [self.queue_list.item(i).text() for i in range(self.queue_list.count())]
            # else: Resuming: self.processed_items, self.total_items, self.current_item are already set from pause_state.
            # self.original_queue is not strictly needed for queue counting if total_items is reliable.
            
            first_iteration_in_this_call = True

            # Process queue until empty
            while self.queue_list.count() > 0:
                if self.is_paused:
                    break
                
                # Get the first item in the queue
                current_queue_item = self.queue_list.item(0)
                # Get the original name from item data
                item_original_name = current_queue_item.data(Qt.UserRole) if current_queue_item.data(Qt.UserRole) else current_queue_item.text()
                
                if is_resuming_session and first_iteration_in_this_call:
                    # Check if the current item from pause state matches the queue head
                    if self.current_item != item_original_name:
                        self.output_window.append(f"Warning: Resumed item '{self.current_item}' "
                                                  f"mismatched queue head '{item_original_name}'. "
                                                  "Processing queue head.")
                        self.processed_items += 1
                else:
                    self.processed_items += 1
                
                # Update current item with the original name
                self.current_item = item_original_name
                
                # Update display of the current queue item to show it's being downloaded
                # Create a new formatted string with (DOWNLOADING) appended
                plain_text = item_original_name
                if " (DOWNLOADING)" not in plain_text:
                    downloading_text = f"{plain_text} (DOWNLOADING)"
                else:
                    downloading_text = plain_text
                    
                current_queue_item.setText(downloading_text)
                
                # Make current item bold when downloading
                font = QFont()
                font.setBold(True)
                current_queue_item.setFont(font)
                
                # Add visual indicator for downloading
                current_queue_item.setForeground(QBrush(QColor(0, 128, 255)))  # Blue text
                
                queue_position = f"{self.processed_items}/{self.total_items}"
                self.current_position = queue_position
                
                # Process item based on its type
                found_platform = False
                
                # First try to get platform from the item formatting
                platform_id = self.get_platform_from_queue_item(item_original_name)
                if platform_id and platform_id in self.platform_lists:
                    filename = self.get_filename_from_queue_item(item_original_name)
                    self.download_item(platform_id, filename, queue_position)
                    found_platform = True
                else:
                    # Fall back to the old method of platform detection
                    for platform_id, items in self.platform_lists.items():
                        clean_item = self.get_filename_from_queue_item(item_original_name)
                        if clean_item in items:
                            self.download_item(platform_id, clean_item, queue_position)
                            found_platform = True
                            break
                
                if not found_platform:
                    self.output_window.append(f"ERROR: Could not determine platform for {item_original_name}")
                
                # If we paused during processing, don't remove the item from queue
                if not self.is_paused:
                    self.queue_list.takeItem(0)
                
                first_iteration_in_this_call = False
            
            # Only reset counters if we completed everything (not paused)
            if not self.is_paused:
                self.processed_items = 0
                self.total_items = 0
                self.original_queue = []
                self.current_item = None
                self.current_position = None
                self.current_file_path = None
                
                # Change button back to Start
                self.start_pause_button.setText('Start')
                
                # Clear download status labels
                self.download_speed_label.setText("")
                self.download_eta_label.setText("")
                self.download_size_label.setText("")  # Clear size label
        
        finally:
            # If we're not paused, re-enable all buttons
            if not self.is_paused:
                self._enable_all_buttons()
            else:
                # Keep pause button enabled when paused
                self.start_pause_button.setText('Resume')
    
    def pause_download(self):
        """Pause the current download or extraction process."""
        self.is_paused = True
        
        # Pause the appropriate thread based on current_operation
        if hasattr(self, 'download_thread') and self.current_operation == 'download':
            self.download_thread.pause()
        elif hasattr(self, 'unzip_runner') and self.current_operation == 'unzip':
            self.unzip_runner.pause()
        
        # Change the button text to 'Resume'
        self.start_pause_button.setText('Resume')
        
        # Enable settings and remove from queue buttons when paused
        self.settings_button.setEnabled(True)
        self.remove_from_queue_button.setEnabled(True)
        self.queue_list.setEnabled(True)
        
        # Allow selection in the queue list
        self.queue_list.setSelectionMode(QAbstractItemView.MultiSelection)
        
        # Update the remove from queue button state based on selection
        self.update_remove_from_queue_button()
    
    def resume_download(self):
        """Resume a previously paused download."""
        self.is_paused = False
        self.start_pause_button.setText('Pause')
        
        # Move the queue position to the beginning of the message
        # Add a newline after the resuming message
        self.output_window.append(f"({self.current_position}) Resuming download...\n")
        
        # Find the current item and update its appearance
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            if item.data(Qt.UserRole) == self.current_item:
                # Update text to show DOWNLOADING instead of PAUSED
                if "(PAUSED)" in item.text():
                    downloading_text = item.text().replace("(PAUSED)", "(DOWNLOADING)")
                else:
                    downloading_text = f"{item.data(Qt.UserRole)} (DOWNLOADING)"
                
                item.setText(downloading_text)
                
                # Make it bold and blue for downloading state
                font = QFont()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(QBrush(QColor(0, 128, 255)))  # Blue color for downloads
                break
        
        # Disable these buttons during active downloads
        self.settings_button.setEnabled(False)
        self.remove_from_queue_button.setEnabled(False)
        
        # Set a flag to indicate we're resuming (to avoid redundant URL display)
        self.is_resuming = True
        
        # Continue processing from where we left off
        self.start_download()
        
        # Reset the flag after starting
        self.is_resuming = False
    
    def _enable_all_buttons(self):
        """Re-enable all GUI buttons."""
        self.settings_button.setEnabled(True)
        self.add_to_queue_button.setEnabled(True)
        self.remove_from_queue_button.setEnabled(True)
        self.decrypt_checkbox.setEnabled(True)
        self.split_checkbox.setEnabled(True)
        self.keep_dkey_checkbox.setEnabled(True)
        self.keep_enc_checkbox.setEnabled(True)
        self.keep_unsplit_dec_checkbox.setEnabled(True)
        self.split_pkg_checkbox.setEnabled(True)
        self.extract_ps3_checkbox.setEnabled(True)
        self.keep_decrypted_iso_checkbox.setEnabled(True)  # Add this line
        self.start_pause_button.setEnabled(True)
        self.start_pause_button.setText('Start')

    def downloadhelper(self, selected_iso, queue_position, url):
        """Helper function to download a file."""
        # Set current operation to download
        self.current_operation = 'download'
        
        # selected_iso is the raw filename, e.g., "Game Name (Region).zip"
        # url is the platform's base URL from config, e.g., "https://myrient.erista.me/files/No-Intro/Platform/"

        # Determine the actual base URL to use for downloading this specific file.
        # 'selected_iso' (the filename) is used to test a concrete file URL.
        effective_base_url = Downloader.try_alternative_domains(url, selected_iso)

        # Now, build the final download URL using this effective_base_url and the selected_iso (filename).
        download_url = Downloader.build_download_url(effective_base_url, selected_iso)
        
        # Compute base_name from selected_iso (filename without extension)
        base_name = Downloader.get_base_name(selected_iso)

        # Define the file paths for .iso and .pkg files (post-unzip state)
        iso_file_path = os.path.join(self.settings_manager.processing_dir, base_name + '.iso')
        pkg_file_path = os.path.join(self.settings_manager.processing_dir, base_name + '.pkg')

        # Check if the .iso or .pkg file (final output) already exists
        if os.path.exists(iso_file_path) or os.path.exists(pkg_file_path):
            print(f"Final output file {iso_file_path} or {pkg_file_path} already exists. Skipping download and processing.")
            return iso_file_path if os.path.exists(iso_file_path) else pkg_file_path

        # Define the path for the .zip file to be downloaded
        # selected_iso is the full filename like "Game Name (Region).zip"
        zip_file_path = os.path.join(self.settings_manager.processing_dir, selected_iso)
        self.current_file_path = zip_file_path  # Store for pause state

        # If the .zip file exists, compare its size to that of the remote URL
        if Downloader.check_file_exists(download_url, zip_file_path):
            self.output_window.append(f"({queue_position}) {selected_iso} already exists and matches remote size. Skipping download.")
            return zip_file_path

        # Only show download start and URL messages if not resuming
        if not hasattr(self, 'is_resuming') or not self.is_resuming:
            self.output_window.append(f"({queue_position}) Download started for {base_name}")
            self.output_window.append(f"URL: {download_url}\n")  # Add explicit newline here
            
        self.progress_bar.reset()
        self.download_size_label.setText("")  # Clear size label
        
        self.download_thread = DownloadThread(download_url, zip_file_path)
        self.download_thread.progress_signal.connect(self.progress_bar.setValue)
        self.download_thread.speed_signal.connect(self.download_speed_label.setText)
        self.download_thread.eta_signal.connect(self.download_eta_label.setText)
        self.download_thread.size_signal.connect(self.download_size_label.setText)  # Connect size signal
        self.download_thread.download_paused_signal.connect(self.on_download_paused)
        
        # Create an event loop and wait for download to complete
        loop = QEventLoop()
        self.download_thread.finished.connect(loop.quit)
        self.download_thread.download_complete_signal.connect(loop.quit)
        
        self.download_thread.start()
        loop.exec_()
        
        # Clear current operation if not paused
        if not self.is_paused:
            self.current_operation = None
            self.current_file_path = None
            
        return zip_file_path
    
    def pause_download(self):
        """Pause the current download or extraction process."""
        self.is_paused = True
        
        # Pause the appropriate thread based on current_operation
        if hasattr(self, 'download_thread') and self.current_operation == 'download':
            self.download_thread.pause()
        elif hasattr(self, 'unzip_runner') and self.current_operation == 'unzip':
            self.unzip_runner.pause()
        
        # Change the button text to 'Resume'
        self.start_pause_button.setText('Resume')
        
        # Enable settings and remove from queue buttons when paused
        self.settings_button.setEnabled(True)
        self.remove_from_queue_button.setEnabled(True)
        self.queue_list.setEnabled(True)
        
        # Allow selection in the queue list
        self.queue_list.setSelectionMode(QAbstractItemView.MultiSelection)
        
        # Update the remove from queue button state based on selection
        self.update_remove_from_queue_button()
    
    def on_download_paused(self):
        """Handle download paused signal."""
        # Print the message with queue position and a newline before
        print(f"\n({self.current_position}) Download paused")
        
        # Find the current queue item and update its appearance
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            if item.data(Qt.UserRole) == self.current_item:
                # Update text to show PAUSED instead of DOWNLOADING
                original_text = item.data(Qt.UserRole)
                if "(DOWNLOADING)" in item.text():
                    paused_text = item.text().replace("(DOWNLOADING)", "(PAUSED)")
                else:
                    paused_text = f"{original_text} (PAUSED)"
                
                item.setText(paused_text)
                
                # Make it bold and yellow for paused state
                font = QFont()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(QBrush(QColor(255, 215, 0)))  # Gold/Yellow color
                break

    def unzip_file_with_pause_support(self, zip_path, output_path, queue_position, base_name):
        """Unzip a file with pause support and return the list of extracted files."""
        self.current_operation = 'unzip'  # Set current operation to unzip
        self.current_file_path = zip_path  # Store for pause state
        
        # Check if the file exists before attempting to unzip
        if not os.path.exists(zip_path):
            self.output_window.append(f"({queue_position}) Error: File to unzip doesn't exist: {zip_path}")
            return []
        
        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")
        self.progress_bar.reset()
        
        self.unzip_runner = UnzipRunner(zip_path, output_path)
        self.unzip_runner.progress_signal.connect(self.progress_bar.setValue)
        self.unzip_runner.unzip_paused_signal.connect(self.on_unzip_paused)
        
        # Create an event loop to wait for the thread
        loop = QEventLoop()
        self.unzip_runner.finished.connect(loop.quit)
        
        self.unzip_runner.start()
        loop.exec_()
        
        # If paused during unzip, keep the original zip
        if self.is_paused:
            return []
            
        # Clear current operation if not paused
        self.current_operation = None
        self.current_file_path = None
        
        return self.unzip_runner.extracted_files
    
    def on_unzip_paused(self):
        """Handle unzip paused signal."""
        self.output_window.append(f"({self.current_position}) Unzipping paused!")
        
        # Find the current queue item and update its appearance
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            if item.data(Qt.UserRole) == self.current_item:
                # Update text to show PAUSED instead of DOWNLOADING
                original_text = item.data(Qt.UserRole)
                if "(DOWNLOADING)" in item.text():
                    paused_text = item.text().replace("(DOWNLOADING)", "(PAUSED)")
                else:
                    paused_text = f"{original_text} (PAUSED)"
                
                item.setText(paused_text)
                
                # Make it bold and yellow for paused state
                font = QFont()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(QBrush(QColor(255, 215, 0)))  # Gold/Yellow color
                break

    def downloadps3isozip(self, selected_iso, queue_position):
        """Download and process PS3 ISO files."""
        url = self.config_manager.get_url('ps3', 'url')
        if not url:
            self.output_window.append(f"ERROR: Missing URL configuration for PS3 ISO downloads")
            return
        
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)
        
        # Check if we're paused after download
        if self.is_paused:
            return
            
        # Check if file exists before continuing - file may have been deleted by user
        if not os.path.exists(file_path):
            self.output_window.append(f"({queue_position}) File no longer exists: {file_path}")
            return
            
        # Create processor if it doesn't exist
        if not hasattr(self, 'processor'):
            self.processor = ProcessorFactory.create_processor('ps3', self.settings_manager, self.output_window, self.progress_bar)

        # Unzip the file with pause support
        extracted_files = self.unzip_file_with_pause_support(file_path, self.settings_manager.processing_dir, queue_position, base_name)
        
        # If paused during unzip, return without deleting the zip
        if self.is_paused:
            return
            
        # Delete the zip file only if we successfully unzipped and it still exists
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                self.output_window.append(f"({queue_position}) Warning: Could not delete zip file: {e}")
        
        try:
            # After this point, disable the pause button as we're in operations that shouldn't be paused
            self.start_pause_button.setEnabled(False)

            # Handle dkey file if needed
            if self.decrypt_checkbox.isChecked() or self.keep_dkey_checkbox.isChecked():
                dkey_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}.dkey")
                if not os.path.isfile(dkey_path):
                    # Download the dkey file
                    self.output_window.append(f"({queue_position}) Getting dkey for {base_name}...")
                    dkey_zip = os.path.join(self.settings_manager.processing_dir, f"{base_name}.zip")
                    dkey_url = self.config_manager.get_url('ps3', 'dkeys')
                    if not dkey_url:
                        self.output_window.append(f"ERROR: Missing URL configuration for PS3 disc keys")
                        return
                        
                    # Download dkey zip
                    dkey_url = f"{dkey_url}/{base_name}.zip"
                    self.download_thread = DownloadThread(dkey_url, dkey_zip)
                    self.download_thread.progress_signal.connect(self.progress_bar.setValue)
                    
                    loop = QEventLoop()
                    self.download_thread.finished.connect(loop.quit)
                    self.download_thread.start()
                    loop.exec_()
                    
                    # Extract dkey
                    with zipfile.ZipFile(dkey_zip, 'r') as zip_ref:
                        zip_ref.extractall(self.settings_manager.processing_dir)
                    os.remove(dkey_zip)
        
            # Decrypt ISO if needed
            if self.decrypt_checkbox.isChecked():
                # Check if PS3Dec binary exists
                if not os.path.isfile(self.settings_manager.ps3dec_binary):
                    # Need to check/download PS3Dec
                    dialog = PrereqBinaryDialog("ps3dec", self)
                    if dialog.exec_():
                        # User wants to download it
                        if not self.settings_manager.download_ps3dec():
                            # Failed to download
                            self.output_window.append(f"({queue_position}) Failed to download PS3Dec. ISO decryption will not be available.")
                            # Skip decryption
                            return
                    else:
                        # User canceled download
                        self.output_window.append(f"({queue_position}) PS3Dec is required for decryption but was not downloaded.")
                        # Skip decryption
                        return
                
                iso_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}.iso")
                if os.path.isfile(os.path.join(self.settings_manager.processing_dir, f"{base_name}.dkey")):
                    # Update queue status to show DECRYPTING
                    self.update_queue_status(self.current_item, "DECRYPTING", QColor(0, 170, 0))  # Green color
                    
                    with open(os.path.join(self.settings_manager.processing_dir, f"{base_name}.dkey"), 'r') as file:
                        key = file.read(32)
                    
                    self.output_window.append(f"({queue_position}) Decrypting ISO for {base_name}...")
                    enc_path = self.processor.decrypt_iso(iso_path, key)
                    
                    # Extract ISO if option is checked - ONLY AFTER DECRYPTION IS COMPLETE
                    if self.extract_ps3_checkbox.isChecked() and os.path.exists(iso_path):
                        # Check if extractps3iso binary exists
                        if not os.path.isfile(self.settings_manager.extractps3iso_binary):
                            # Need to check/download extractps3iso
                            dialog = PrereqBinaryDialog("extractps3iso", self)
                            if dialog.exec_():
                                # User wants to download it
                                if not self.settings_manager.download_extractps3iso():
                                    # Failed to download
                                    self.output_window.append(f"({queue_position}) Failed to download extractps3iso. ISO extraction will not be available.")
                                    # Skip extraction
                                    return
                            else:
                                # User canceled download
                                self.output_window.append(f"({queue_position}) extractps3iso is required for extraction but was not downloaded.")
                                # Skip extraction
                                return
                        
                        # Update queue status to show EXTRACTING
                        self.update_queue_status(self.current_item, "EXTRACTING", QColor(0, 170, 0))  # Green color
                        self.output_window.append(f"({queue_position}) Extracting ISO contents for {base_name}...")
                        
                        # Call the extract_iso method on the DECRYPTED iso
                        success, extract_dir = self.processor.extract_iso(iso_path)
                        if success:
                            # Move the extracted directory to PS3ISO directory instead of keeping it in processing dir
                            # Get target path in PS3ISO directory
                            target_dir = os.path.join(self.settings_manager.ps3iso_dir, os.path.basename(extract_dir))
                            
                            # Check if target directory already exists
                            if os.path.exists(target_dir):
                                # If it exists, remove it first to avoid merge issues
                                try:
                                    shutil.rmtree(target_dir)
                                except Exception as e:
                                    self.output_window.append(f"({queue_position}) Warning: Could not remove existing directory: {e}")
                            
                            # Move the extracted folder to PS3ISO directory
                            try:
                                shutil.move(extract_dir, self.settings_manager.ps3iso_dir)
                                self.output_window.append(f"({queue_position}) ISO contents moved to {target_dir}")
                            except Exception as e:
                                self.output_window.append(f"({queue_position}) Error moving extracted directory: {e}")
                                
                            # Handle the decrypted ISO based on user setting
                            if not self.settings_manager.keep_decrypted_iso_after_extraction:
                                try:
                                    os.remove(iso_path)
                                    self.output_window.append(f"({queue_position}) Deleted decrypted ISO after extraction")
                                except Exception as e:
                                    self.output_window.append(f"({queue_position}) Warning: Could not delete decrypted ISO: {e}")
                            else:
                                # Move the ISO to PS3ISO directory as well if we're keeping it
                                ps3iso_iso_path = os.path.join(self.settings_manager.ps3iso_dir, os.path.basename(iso_path))
                                if os.path.exists(ps3iso_iso_path):
                                    try:
                                        os.remove(ps3iso_iso_path)  # Remove existing file
                                    except Exception as e:
                                        self.output_window.append(f"({queue_position}) Warning: Could not remove existing ISO: {e}")
                                    
                                try:
                                    shutil.move(iso_path, self.settings_manager.ps3iso_dir)
                                    self.output_window.append(f"({queue_position}) Moved ISO file to PS3ISO directory")
                                except Exception as e:
                                    self.output_window.append(f"({queue_position}) Error moving ISO file: {e}")
                        else:
                            self.output_window.append(f"({queue_position}) Failed to extract ISO contents")
                            
                            # If extraction failed, still move the ISO to PS3ISO
                            ps3iso_iso_path = os.path.join(self.settings_manager.ps3iso_dir, os.path.basename(iso_path))
                            if os.path.exists(ps3iso_iso_path):
                                try:
                                    os.remove(ps3iso_iso_path)  # Remove existing file
                                except Exception as e:
                                    self.output_window.append(f"({queue_position}) Warning: Could not remove existing ISO: {e}")
                                    
                            try:
                                shutil.move(iso_path, self.settings_manager.ps3iso_dir)
                                self.output_window.append(f"({queue_position}) Moved ISO file to PS3ISO directory")
                            except Exception as e:
                                self.output_window.append(f"({queue_position}) Error moving ISO file: {e}")
                    else:
                        # If not extracting, move the ISO to PS3ISO
                        ps3iso_iso_path = os.path.join(self.settings_manager.ps3iso_dir, os.path.basename(iso_path))
                        if os.path.exists(ps3iso_iso_path):
                            try:
                                os.remove(ps3iso_iso_path)  # Remove existing file
                            except Exception as e:
                                self.output_window.append(f"({queue_position}) Warning: Could not remove existing ISO: {e}")
                                
                        try:
                            shutil.move(iso_path, self.settings_manager.ps3iso_dir)
                            self.output_window.append(f"({queue_position}) Moved ISO file to PS3ISO directory")
                        except Exception as e:
                            self.output_window.append(f"({queue_position}) Error moving ISO file: {e}")
                    
                    # Delete encrypted ISO if not keeping it
                    if not self.keep_enc_checkbox.isChecked() and os.path.exists(enc_path):
                        try:
                            os.remove(enc_path)
                        except Exception as e:
                            self.output_window.append(f"({queue_position}) Warning: Could not delete encrypted ISO: {e}")
            else:
                # If not decrypting, move the ISO to PS3ISO
                iso_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}.iso")
                if os.path.exists(iso_path):
                    ps3iso_iso_path = os.path.join(self.settings_manager.ps3iso_dir, os.path.basename(iso_path))
                    if os.path.exists(ps3iso_iso_path):
                        try:
                            os.remove(ps3iso_iso_path)  # Remove existing file
                        except Exception as e:
                            self.output_window.append(f"({queue_position}) Warning: Could not remove existing ISO: {e}")
                        
                    try:
                        shutil.move(iso_path, self.settings_manager.ps3iso_dir)
                        self.output_window.append(f"({queue_position}) Moved ISO file to PS3ISO directory")
                    except Exception as e:
                        self.output_window.append(f"({queue_position}) Error moving ISO file: {e}")
            
            # Delete dkey file if not keeping it (regardless of whether decryption was performed)
            if not self.keep_dkey_checkbox.isChecked():
                dkey_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}.dkey")
                if os.path.exists(dkey_path):
                    try:
                        os.remove(dkey_path)
                    except Exception as e:
                        self.output_window.append(f"({queue_position}) Warning: Could not delete dkey file: {e}")
                        
            # Move dkey file to PS3ISO if keeping it
            elif self.keep_dkey_checkbox.isChecked():
                dkey_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}.dkey")
                if os.path.exists(dkey_path):
                    ps3iso_dkey_path = os.path.join(self.settings_manager.ps3iso_dir, os.path.basename(dkey_path))
                    if os.path.exists(ps3iso_dkey_path):
                        try:
                            os.remove(ps3iso_dkey_path)  # Remove existing file
                        except Exception as e:
                            self.output_window.append(f"({queue_position}) Warning: Could not remove existing dkey file: {e}")
                            
                    try:
                        shutil.move(dkey_path, self.settings_manager.ps3iso_dir)
                        self.output_window.append(f"({queue_position}) Moved dkey file to PS3ISO directory")
                    except Exception as e:
                        self.output_window.append(f"({queue_position}) Error moving dkey file: {e}")
        
        except Exception as e:
            self.output_window.append(f"ERROR: Processing failed for {base_name}: {str(e)}")
        finally:
            # Always re-enable the pause button when done with critical operations
            self.start_pause_button.setEnabled(True)
    
        self.output_window.append(f"({queue_position}) {base_name} complete!")

    def downloadps3psnzip(self, selected_iso, queue_position):
        """Download and process PS3 PSN packages."""
        url = self.config_manager.get_url('psn', 'url')
        if not url:
            self.output_window.append(f"ERROR: Missing URL configuration for PS3 PSN downloads")
            return
        
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)
        
        # Create processor if it doesn't exist
        if not hasattr(self, 'processor'):
            self.processor = ProcessorFactory.create_processor('psn', self.settings_manager, self.output_window, self.progress_bar)
        
        # Skip if not a zip file
        if not file_path.lower().endswith('.zip'):
            print(f"File {file_path} is not a .zip file. Skipping unzip.")
            return
        
        # Unzip the file
        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")
        extracted_files = self.processor.unzip_file(file_path, self.settings_manager.processing_dir)
        
        # Delete the zip file
        os.remove(file_path)
        
        # Process each extracted file
        for file in extracted_files:
            if file.endswith('.pkg'):
                new_file_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}{os.path.splitext(file)[1]}")
                os.rename(file, new_file_path)
                
                # Split PKG if needed
                if self.split_pkg_checkbox.isChecked():
                    self.processor.split_pkg(new_file_path)
        
        # Move files to output directories
        import glob
        for file in glob.glob(os.path.join(self.settings_manager.processing_dir, '*.rap')):
            dst = os.path.join(self.settings_manager.psn_rap_dir, os.path.basename(file))
            if os.path.exists(dst):
                print(f"File {dst} already exists. Overwriting.")
            shutil.move(file, dst)
        
        for file in glob.glob(os.path.join(self.settings_manager.processing_dir, '*.pkg*')):
            dst = os.path.join(self.settings_manager.psn_pkg_dir, os.path.basename(file))
            if os.path.exists(dst):
                print(f"File {dst} already exists. Overwriting.")
            shutil.move(file, dst)
        
        self.output_window.append(f"({queue_position}) {base_name} ready!")

    def downloadps2isozip(self, selected_iso, queue_position):
        """Download and process PS2 ISO files."""
        url = self.config_manager.get_url('ps2', 'url')
        if not url:
            self.output_window.append(f"ERROR: Missing URL configuration for PS2 ISO downloads")
            return
        
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)
        
        # Create processor if it doesn't exist
        if not hasattr(self, 'processor'):
            self.processor = ProcessorFactory.create_processor('ps2', self.settings_manager, self.output_window, self.progress_bar)
        
        # Unzip the file
        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")
        extracted_files = self.processor.unzip_file(file_path, self.settings_manager.processing_dir)
        
        # Delete the zip file
        os.remove(file_path)
        
        # Process each extracted file
        for file in extracted_files:
            if file.endswith('.iso'):
                # Split ISO if needed
                if self.split_checkbox.isChecked() and os.path.getsize(file) >= 4294967295:
                    self.output_window.append(f"({queue_position}) Splitting ISO for {base_name}...")
                    split_success = self.processor.split_iso(file)
                    
                    # Delete unsplit ISO if not keeping it
                    if split_success and not self.keep_unsplit_dec_checkbox.isChecked():
                        os.remove(file)
                    
                    # Move split files
                    import glob
                    for split_file in glob.glob(file.rsplit('.', 1)[0] + '*.iso.*'):
                        shutil.move(split_file, self.settings_manager.ps2iso_dir)
                else:
                    # Move the ISO directly
                    shutil.move(file, self.settings_manager.ps2iso_dir)
            
            # Handle .bin and .cue files
            elif file.endswith('.bin') or file.endswith('.cue'):
                shutil.move(file, self.settings_manager.ps2iso_dir)
        
        self.output_window.append(f"({queue_position}) {base_name} complete!")

    def downloadpsxzip(self, selected_iso, queue_position):
        """Download and process PSX ISO files."""
        url = self.config_manager.get_url('psx', 'url')
        if not url:
            self.output_window.append(f"ERROR: Missing URL configuration for PSX ISO downloads")
            return
        
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)
        
        # Create processor if it doesn't exist
        if not hasattr(self, 'processor'):
            self.processor = ProcessorFactory.create_processor('psx', self.settings_manager, self.output_window, self.progress_bar)
        
        # Unzip the file
        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")
        self.processor.unzip_file(file_path, self.settings_manager.processing_dir)
        
        # Delete the zip file
        os.remove(file_path)
        
        # Move all files to the PSX directory
        import glob
        for file in glob.glob(os.path.join(self.settings_manager.processing_dir, base_name + '*')):
            shutil.move(file, self.settings_manager.psxiso_dir)
        
        self.output_window.append(f"({queue_position}) {base_name} complete!")

    def downloadpspisozip(self, selected_iso, queue_position):
        """Download and process PSP ISO files."""
        url = self.config_manager.get_url('psp', 'url')
        if not url:
            self.output_window.append(f"ERROR: Missing URL configuration for PSP ISO downloads")
            return
        
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)
        
        # Create processor if it doesn't exist
        if not hasattr(self, 'processor'):
            self.processor = ProcessorFactory.create_processor('psp', self.settings_manager, self.output_window, self.progress_bar)
        
        # Unzip the file
        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")
        self.processor.unzip_file(file_path, self.settings_manager.processing_dir)
        
        # Delete the zip file
        os.remove(file_path)
        
        # Split ISO if needed
        iso_path = os.path.join(self.settings_manager.processing_dir, f"{base_name}.iso")
        if self.split_checkbox.isChecked() and os.path.exists(iso_path) and os.path.getsize(iso_path) >= 4294967295:
            self.output_window.append(f"({queue_position}) Splitting ISO for {base_name}...")
            split_success = self.processor.split_iso(iso_path)
            
            # Delete unsplit ISO if not keeping it
            if split_success and not self.keep_unsplit_dec_checkbox.isChecked():
                os.remove(iso_path)
        
        # Move all files to the PSP directory
        import glob
        for file in glob.glob(os.path.join(self.settings_manager.processing_dir, base_name + '*')):
            shutil.move(file, self.settings_manager.pspiso_dir)
        
        self.output_window.append(f"({queue_position}) {base_name} complete!")

    def get_platform_from_queue_item(self, item_text):
        """Extract platform from a formatted queue item."""
        # Handle HTML-formatted items
        if '<' in item_text and '>' in item_text:
            # Strip HTML tags first
            plain_text = re.sub(r'<[^>]+>', '', item_text)
            item_text = plain_text
            
        # Match pattern (PLATFORM) at the beginning of the text
        match = re.search(r'^\(([^)]+)\)', item_text)
        if match:
            return match.group(1).lower()
        return None
    
    def get_filename_from_queue_item(self, item_text):
        """Extract filename from a formatted queue item."""
        # Handle HTML-formatted items
        if '<' in item_text and '>' in item_text:
            # Strip HTML tags first
            plain_text = re.sub(r'<[^>]+>', '', item_text)
            item_text = plain_text
            
        # Remove platform prefix pattern (PLATFORM) from the text
        text_without_platform = re.sub(r'^\([^)]+\)\s*', '', item_text)
        
        # Remove (DOWNLOADING) suffix if present
        return re.sub(r'\s*\(DOWNLOADING\)\s*$', '', text_without_platform)
    
    def download_item(self, platform_id, item_text, queue_position):
        """Download and process an item based on its platform."""
        # Extract actual filename if this is a formatted queue item
        if '<b>' in item_text:
            item_text = self.get_filename_from_queue_item(item_text)
        
        # Use existing specialized methods for known platforms
        if platform_id == 'ps3':
            self.downloadps3isozip(item_text, queue_position)
        elif platform_id == 'psn':
            self.downloadps3psnzip(item_text, queue_position)
        elif platform_id == 'ps2':
            self.downloadps2isozip(item_text, queue_position)
        elif platform_id == 'psx':
            self.downloadpsxzip(item_text, queue_position)
        elif platform_id == 'psp':
            self.downloadpspisozip(item_text, queue_position)
        else:
            # Generic download handler for new platforms
            self.download_generic(platform_id, item_text, queue_position)

    def download_generic(self, platform_id, selected_iso, queue_position):
        """Generic download handler for any platform."""
        url = self.config_manager.get_url(platform_id, 'url')
        if not url:
            self.output_window.append(f"ERROR: Missing URL configuration for {platform_id}")
            return
        
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)
        
        # Check if paused after download
        if self.is_paused:
            return
        
        # Create processor if needed
        if not hasattr(self, 'processor'):
            self.processor = ProcessorFactory.create_processor(platform_id, self.settings_manager, self.output_window, self.progress_bar)

        # Unzip with pause support
        extracted_files = self.unzip_file_with_pause_support(file_path, self.settings_manager.processing_dir, queue_position, base_name)
        
        # Check if paused after unzip
        if self.is_paused:
            return
            
        # Delete the zip file if it exists
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                self.output_window.append(f"({queue_position}) Warning: Could not delete zip file: {e}")
        
        try:
            # Disable pause during critical operations
            self.start_pause_button.setEnabled(False)
            
            # Process extracted files
            for file in extracted_files:
                if file.endswith(('.iso', '.bin', '.cue')):
                    # Split large ISO files if needed
                    if file.endswith('.iso') and self.split_checkbox.isChecked() and os.path.getsize(file) >= 4294967295:
                        # Update queue status to show SPLITTING
                        self.update_queue_status(self.current_item, "SPLITTING", QColor(0, 170, 0))  # Green color
                        
                        self.output_window.append(f"({queue_position}) Splitting ISO for {base_name}...")
                        split_success = self.processor.split_iso(file)
                        
                        # Delete original if splitting succeeded and not keeping unsplit
                        if split_success and not self.keep_unsplit_dec_checkbox.isChecked():
                            os.remove(file)
        
            # Get the appropriate output directory
            output_dir = getattr(self.settings_manager, f"{platform_id}_dir", self.settings_manager.processing_dir)
            
            # Move all processed files
            self.processor.move_processed_files(base_name, self.settings_manager.processing_dir, output_dir)
            
        except Exception as e:
            self.output_window.append(f"ERROR: Processing failed for {base_name}: {str(e)}")
        finally:
            # Re-enable pause button
            self.start_pause_button.setEnabled(True)
    
        self.output_window.append(f"({queue_position}) {base_name} complete!")
    
    def add_formatted_item_to_queue(self, item_text):
        """Add an item to the queue list with no special formatting by default."""
        list_item = QListWidgetItem()
        
        # Store original text as user data
        list_item.setData(Qt.UserRole, item_text)
        
        # Get platform and remaining text
        platform_match = re.search(r'^\(([^)]+)\)', item_text)
        if platform_match:
            # Extract platform part and the rest
            platform = platform_match.group(0)  # (PS3), (PSN), etc.
            remaining_text = item_text[len(platform):]
            
            # Set the full text without formatting
            clean_text = item_text
            
            # Check for downloading status - no special formatting initially
            if " (DOWNLOADING)" in remaining_text:
                remaining_text = remaining_text.replace(" (DOWNLOADING)", "")
                clean_text = platform + remaining_text
                
            # Set the display text (without HTML)
            list_item.setText(clean_text)
        else:
            # No platform prefix found, just use text as is
            list_item.setText(item_text)

        self.queue_list.addItem(list_item)
        return list_item

    def format_file_size(self, size_bytes):
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"
    
    def update_queue_status(self, item_original_name, status, color=None):
        """Update the queue item text to show the current operation status."""
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            if item.data(Qt.UserRole) == item_original_name:
                # Extract original text without any status
                text = item.data(Qt.UserRole)
                clean_text = re.sub(r' \([A-Z]+\)$', '', text)
                
                # Add the new status
                new_text = f"{clean_text} ({status})"
                item.setText(new_text)
                
                # Apply bold font
                font = QFont()
                font.setBold(True)
                item.setFont(font)
                
                # Apply color if specified
                if color:
                    item.setForeground(QBrush(color))
                break
