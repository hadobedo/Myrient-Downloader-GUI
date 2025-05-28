import os
import signal
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
from core.settings import SettingsManager, SettingsDialog, BinaryValidationDialog
from core.config_manager import ConfigManager
from threads.download_threads import GetSoftwareListThread


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
        
        # Initialize AppController
        from core.app_controller import AppController
        self.app_controller = AppController(
            self.settings_manager,
            self.config_manager,
            self.output_window,
            self
        )
        
        # Get platforms from configuration
        self.platforms = self.config_manager.get_platforms()
        
        # Load software lists
        self.init_software_lists()
        
        # Initialize the UI
        self.initUI()
        
        # Load the queue and check for paused downloads
        self._setup_queue()
        
        # Add signal handler for SIGINT
        signal.signal(signal.SIGINT, self.closeEvent)
        
        # Connect AppController signals
        self._connect_app_controller_signals()
    
    def _setup_queue(self):
        """Setup the queue and check for paused downloads."""
        # Load the queue using AppController
        queue_items = self.app_controller.load_queue()
        
        # Add items to the queue list using AppController's queue manager
        for item_text in queue_items:
            self.app_controller.queue_manager.add_formatted_item_to_queue(item_text, self.queue_list)
        
        # If queue is empty, clear any stale pause state
        if self.queue_list.count() == 0:
            from core.state_manager import StateManager
            StateManager.clear_pause_state()
        
        # Check if we need to resume a paused download
        if self.app_controller.check_for_paused_download(self.queue_list):
            self.start_pause_button.setText('Resume')

    def _connect_app_controller_signals(self):
        """Connect AppController signals to GUI updates."""
        self.app_controller.progress_updated.connect(self.progress_bar.setValue)
        self.app_controller.speed_updated.connect(self.download_speed_label.setText)
        self.app_controller.eta_updated.connect(self.download_eta_label.setText)
        self.app_controller.size_updated.connect(self.download_size_label.setText)
        self.app_controller.queue_updated.connect(self._on_queue_updated)
        self.app_controller.operation_complete.connect(self._on_operation_complete)
        self.app_controller.operation_paused.connect(self._on_operation_paused)
        self.app_controller.error_occurred.connect(self._on_error)

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
        
        # Set a minimum height for the queue list and make it resize properly
        self.queue_list.setMinimumHeight(150)
        # Enable horizontal scrollbar when needed for long lines
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Set the resize mode to fit contents
        self.queue_list.setResizeMode(QListWidget.Adjust)
        
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
        self.progress_bar.setFormat("%p%")  # Show percentage centered
        self.progress_bar.setAlignment(Qt.AlignCenter)  # Center the text
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
        self.resize(1200, 900)
        
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
        
        # Add universal content organization option
        row += 1
        self.organize_content_checkbox = QCheckBox('Group downloaded files per game', self)
        self.organize_content_checkbox.setChecked(self.settings_manager.organize_content_to_folders)
        general_grid.addWidget(self.organize_content_checkbox, row, 0, 1, 2)  # Span 2 columns
        
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
        self.extract_ps3_checkbox = QCheckBox('Extract ISO using extractps3iso', self)
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
        self.organize_content_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('organize_content_to_folders', state))
        
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
                    dialog = BinaryValidationDialog("extractps3iso", self)
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
            added_count = self.app_controller.add_to_queue(
                selected_items, current_platform, self.platforms, self.queue_list
            )
            
            # Removed "Added x items to queue" output to clean up logs
    
    def remove_from_queue(self):
        """Remove selected items from the download queue."""
        selected_items = self.queue_list.selectedItems()
        if not selected_items:
            return
        
        removed_count = self.app_controller.remove_from_queue(selected_items, self.queue_list)
        
        # Update button state
        self.update_remove_from_queue_button()
    
    def open_settings(self):
        """Open the settings dialog."""
        dlg = SettingsDialog(self.settings_manager, self.config_manager, self)
        if dlg.exec_() == QDialog.Accepted:
            QMessageBox.information(self, "Settings", "Settings saved.")
            # Optionally, update directories on disk if changed
            self.settings_manager.create_directories()
    
    

    def closeEvent(self, event):
        """Handle the close event."""
        try:
            # Save pause state and queue using AppController
            self.app_controller.save_pause_state(self.queue_list)
            
            # Stop all threads
            self._stop_all_threads()
            
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
        # Stop AppController operations
        self.app_controller.stop_processing()
        
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
        self._disable_controls_during_processing()
        
        # Change button to Pause
        self.start_pause_button.setText('Pause')
        
        # Get current settings
        settings = self._get_current_settings()
        
        # Start processing using AppController
        self.app_controller.start_processing(self.queue_list, settings)
    
    def pause_download(self):
        """Pause the current download or extraction process."""
        self.app_controller.pause_processing()
        
        # Change the button text to 'Resume'
        self.start_pause_button.setText('Resume')
        
        # Enable settings and remove from queue buttons when paused
        self._enable_controls_during_pause()
    
    def resume_download(self):
        """Resume a previously paused download."""
        self.start_pause_button.setText('Pause')
        
        # Get current settings
        settings = self._get_current_settings()
        
        # Disable controls during processing
        self._disable_controls_during_processing()
        
        # Resume processing using AppController
        self.app_controller.resume_processing(self.queue_list, settings)
    
    def _disable_controls_during_processing(self):
        """Disable GUI controls during processing."""
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
        self.keep_decrypted_iso_checkbox.setEnabled(False)
        self.organize_content_checkbox.setEnabled(False)

    def _enable_controls_during_pause(self):
        """Enable specific controls during pause."""
        self.settings_button.setEnabled(True)
        self.remove_from_queue_button.setEnabled(True)
        self.queue_list.setEnabled(True)
        
        # Allow selection in the queue list
        self.queue_list.setSelectionMode(QAbstractItemView.MultiSelection)
        
        # Update the remove from queue button state based on selection
        self.update_remove_from_queue_button()

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
        self.keep_decrypted_iso_checkbox.setEnabled(True)
        self.organize_content_checkbox.setEnabled(True)
        self.start_pause_button.setEnabled(True)
        self.start_pause_button.setText('Start')

    def _get_current_settings(self):
        """Get current settings from the GUI."""
        return {
            'decrypt_iso': self.decrypt_checkbox.isChecked(),
            'split_large_files': self.split_checkbox.isChecked(),
            'keep_dkey_file': self.keep_dkey_checkbox.isChecked(),
            'keep_encrypted_iso': self.keep_enc_checkbox.isChecked(),
            'keep_unsplit_file': self.keep_unsplit_dec_checkbox.isChecked(),
            'split_pkg': self.split_pkg_checkbox.isChecked(),
            'extract_ps3_iso': self.extract_ps3_checkbox.isChecked(),
            'keep_decrypted_iso_after_extraction': self.keep_decrypted_iso_checkbox.isChecked(),
            'organize_content_to_folders': self.organize_content_checkbox.isChecked()
        }

    def _on_queue_updated(self):
        """Handle queue update signal from AppController."""
        # Update button states
        self.update_add_to_queue_button()
        self.update_remove_from_queue_button()

    def _on_operation_complete(self):
        """Handle operation complete signal from AppController."""
        # Re-enable all buttons
        self._enable_all_buttons()
        
        # Clear download status labels
        self.download_speed_label.setText("")
        self.download_eta_label.setText("")
        self.download_size_label.setText("")
        
        # Save the queue state (should be empty now) to clear the queue file
        self.app_controller.save_queue(self.queue_list)

    def _on_operation_paused(self, item_name):
        """Handle operation paused signal from AppController."""
        self.start_pause_button.setText('Resume')
        self._enable_controls_during_pause()

    def _on_error(self, error_message):
        """Handle error signal from AppController."""
        self.output_window.append(f"ERROR: {error_message}")


