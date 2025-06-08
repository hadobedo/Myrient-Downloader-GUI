import os
import signal
import re
import sys
import json
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QTreeWidget, QTreeWidgetItem, QLabel, QCheckBox,
    QFileDialog, QDialog, QGroupBox, QProgressBar, QTabWidget, QAbstractItemView,
    QMessageBox, QListWidget, QListWidgetItem, QFormLayout, QDialogButtonBox, QGridLayout,
    QSplitter, QFrame, QSizePolicy, QComboBox
)
from PyQt5.QtCore import Qt, QSettings, QThread, pyqtSignal, QEventLoop, QTimer # Removed QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QBrush, QColor

from gui.output_window import OutputWindow
from core.settings import SettingsManager, SettingsDialog, BinaryValidationDialog
from core.config_manager import ConfigManager
from threads.download_threads import GetSoftwareListThread


class QueueTreeWidgetItem(QTreeWidgetItem):
    """Custom tree widget item with inline move buttons."""
    
    def __init__(self, columns, parent_widget=None):
        super().__init__(columns)
        self.parent_widget = parent_widget
        self.up_button = None
        self.down_button = None
        self.buttons_created = False
    
    def create_buttons(self, tree_widget):
        """Create inline move buttons for this item."""
        if self.buttons_created:
            return
            
        # Create mini buttons with styling
        self.up_button = QPushButton("↑")
        self.up_button.setMaximumSize(20, 20)
        self.up_button.setMinimumSize(20, 20)
        self.up_button.clicked.connect(lambda: self.parent_widget.move_queue_item_up_inline(self))
        
        self.down_button = QPushButton("↓")
        self.down_button.setMaximumSize(20, 20)
        self.down_button.setMinimumSize(20, 20)
        self.down_button.clicked.connect(lambda: self.parent_widget.move_queue_item_down_inline(self))
        
        # Apply button styling for enabled/disabled states
        button_style = """
            QPushButton {
                border: 1px solid #555;
                border-radius: 3px;
                background-color: #666;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover:enabled {
                background-color: #777;
                border-color: #888;
            }
            QPushButton:pressed:enabled {
                background-color: #555;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #666;
                border-color: #444;
            }
        """
        
        self.up_button.setStyleSheet(button_style)
        self.down_button.setStyleSheet(button_style)
        
        # Create container widget for buttons
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(2, 2, 2, 2)
        button_layout.setSpacing(1)
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)
        
        # Set the widget in the third column
        tree_widget.setItemWidget(self, 2, button_widget)
        self.buttons_created = True
        
        # Update button states
        self.update_button_states(tree_widget)
    
    def update_button_states(self, tree_widget):
        """Update button enabled state based on position."""
        if not self.buttons_created:
            return
            
        # Check if buttons still exist (they may have been deleted during item moves)
        try:
            if not self.up_button or not self.down_button:
                return
                
            current_index = tree_widget.indexOfTopLevelItem(self)
            total_items = tree_widget.topLevelItemCount()
            
            # Up button: disabled if at the top (index 0)
            self.up_button.setEnabled(current_index > 0)
            
            # Down button: disabled if at the bottom (last index)
            self.down_button.setEnabled(current_index < total_items - 1)
            
        except RuntimeError:
            # Buttons have been deleted - mark as needing recreation
            self.buttons_created = False
            self.up_button = None
            self.down_button = None


class SortableTreeWidgetItem(QTreeWidgetItem):
    """Custom QTreeWidgetItem that sorts file sizes numerically."""
    
    def __lt__(self, other):
        """Custom sorting logic for file sizes."""
        column = self.treeWidget().sortColumn()
        
        if column == 1:  # Size column - sort numerically
            size1 = self._size_to_bytes(self.text(1))
            size2 = self._size_to_bytes(other.text(1))
            return size1 < size2
        else:  # Name column or others - sort alphabetically
            return self.text(column).lower() < other.text(column).lower()
    
    def _size_to_bytes(self, size_text):
        """Convert size string to bytes for numerical sorting."""
        if not size_text or size_text.strip() == '':
            return 0
        
        try:
            # Remove extra whitespace and convert to uppercase
            size_text = size_text.strip().upper()
            
            # Handle edge cases
            if size_text in ['', '-', 'N/A', 'UNKNOWN']:
                return 0
            
            # Extract number and unit using regex
            import re
            match = re.match(r'([0-9,]+\.?[0-9]*)\s*([A-Z]*)', size_text)
            if not match:
                return 0
            
            number_str = match.group(1).replace(',', '')
            unit = match.group(2)
            
            try:
                number = float(number_str)
            except ValueError:
                return 0
            
            # Convert to bytes based on unit
            multipliers = {
                'B': 1,
                'KB': 1000,
                'MB': 1000 ** 2,
                'GB': 1000 ** 3,
                'TB': 1000 ** 4,
                'KIB': 1024,
                'MIB': 1024 ** 2,
                'GIB': 1024 ** 3,
                'TIB': 1024 ** 4
            }
            
            multiplier = multipliers.get(unit, 1)
            return int(number * multiplier)
            
        except Exception:
            return 0


class GUIDownloader(QWidget):
    """The main GUI window for the Myrient Downloader application."""
    
    def __init__(self):
        try:
            super().__init__()
            self.setAttribute(Qt.WA_DeleteOnClose)  # Ensure cleanup on close
            
            # Initialize output window first
            self.output_window = OutputWindow(self)
            if not self.output_window:
                raise RuntimeError("Failed to create output window")
            self.output_window.set_as_stdout()
            
            # Initialize core components
            self.config_manager = ConfigManager()
            if not self.config_manager:
                raise RuntimeError("Failed to initialize ConfigManager")
            
            # Initialize managers
            self.settings_manager = SettingsManager(config_manager=self.config_manager)
            if not self.settings_manager:
                raise RuntimeError("Failed to initialize SettingsManager")
            
            # Initialize the rest of the application
            self._init_application()
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            QMessageBox.critical(
                None,
                "Initialization Error",
                f"Failed to initialize application:\n\n{str(e)}\n\nSee logs for details."
            )
            print(f"Initialization error:\n{error_details}")
            raise  # Re-raise to let main() handle cleanup
    
    def _init_application(self):
        """Initialize the rest of the application after basic setup."""
        
        # Pass config_manager to SettingsManager
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
        
        # Set up signal handler
        def signal_handler(signum, frame):
            try:
                if hasattr(self, 'output_window'):
                    self.output_window.restore_stdout()
                self.close()
            except Exception:
                sys.exit(1)
        
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, signal_handler)
        
        # Initialize UI and components
        self.init_software_lists()
        self.initUI()
        self._setup_queue()
        self._connect_app_controller_signals()
    
    def _setup_queue(self):
        """Setup the queue and check for paused downloads."""
        self.was_paused_on_startup = False # Initialize flag

        # AppController now handles checking for paused state (physical or saved)
        # and populates the queue_list widget accordingly if a paused state is found.
        if self.app_controller.check_for_paused_download(self.queue_list):
            self.start_pause_button.setText('Resume')
            self.was_paused_on_startup = True
            self.status_header.setText("Paused")
            self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #ffd700;")
            print("Resumable download found and queue populated by AppController.")
        else:
            # No resumable state found by AppController, load queue normally.
            # AppController's check_for_paused_download might have already loaded it if no pause state was found.
            # We ensure it's loaded here if the queue is still empty.
            if self.queue_list.topLevelItemCount() == 0:
                print("No resumable download found by AppController. Loading queue from storage.")
                queue_data = self.app_controller.queue_manager.load_queue()
                for item_data in queue_data:
                    if isinstance(item_data, dict):
                        self.app_controller.queue_manager.add_formatted_item_to_queue(item_data, self.queue_list)
                    else:
                        item_dict = {'name': item_data, 'size': ''}
                        self.app_controller.queue_manager.add_formatted_item_to_queue(item_dict, self.queue_list)
            else:
                print("Queue already populated by AppController (no pause state, but queue loaded).")


        # Column widths are handled by resize modes set during UI initialization


        # If queue is empty after all checks, clear any stale pause state from StateManager
        if self.queue_list.topLevelItemCount() == 0:
            from core.state_manager import StateManager
            StateManager.clear_pause_state()

        # Update queue item sizes asynchronously if any are missing
        try:
            if self.queue_list.topLevelItemCount() > 0:
                self.app_controller.queue_manager.update_queue_item_sizes_async(self.queue_list)
        except Exception as e:
            print(f"Error updating queue sizes: {e}")

    def _connect_app_controller_signals(self):
        """Connect AppController signals to GUI updates."""
        self.app_controller.progress_updated.connect(self.progress_bar.setValue)
        self.app_controller.speed_updated.connect(self.download_speed_label.setText)
        self.app_controller.eta_updated.connect(self.download_eta_label.setText)
        self.app_controller.size_updated.connect(self.download_size_label.setText)
        self.app_controller.queue_updated.connect(self._on_queue_updated)
        self.app_controller.operation_complete.connect(self._on_operation_complete)
        self.app_controller.operation_paused.connect(self._on_operation_paused)
        self.app_controller.status_updated.connect(self._on_status_updated)
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
        # Set fetch_sizes=True to enable the new optimized file size fetching
        fetch_file_sizes = True  # Uses optimized batch processing for fast startup
        
        for platform_id, data in self.platforms.items():
            json_filename = f"{platform_id}_filelist.json"
            thread = self.load_software_list(
                data['url'],
                json_filename,
                lambda items, pid=platform_id: self.set_platform_list(pid, items),
                fetch_sizes=fetch_file_sizes
            )
            self.platform_threads[platform_id] = thread
            thread.start()

    def load_software_list(self, url, json_filename, setter, fetch_sizes=True):
        """Create and return a thread to load a software list."""
        thread = GetSoftwareListThread(url, json_filename, fetch_sizes)
        thread.signal.connect(setter)
        return thread
    
    def _populate_platform_tree(self, tree_widget, items):
        """Populate a platform tree widget with file data (names and sizes)."""
        tree_widget.clear()
        
        # Handle loading state
        if isinstance(items, list) and len(items) == 1 and isinstance(items[0], str):
            if "Loading..." in items[0]:
                item = QTreeWidgetItem(['Loading... this will take a moment', ''])
                tree_widget.addTopLevelItem(item)
                return
            elif "Error loading" in items[0]:
                item = QTreeWidgetItem([items[0], ''])
                tree_widget.addTopLevelItem(item)
                return
        
        # Load file data - sizes will be loaded from JSON in set_platform_list_with_sizes
        for filename in items:
            if isinstance(filename, str):
                item = SortableTreeWidgetItem([filename, ''])  # Size will be populated later
                tree_widget.addTopLevelItem(item)
    
    def _get_cached_file_size(self, filename):
        """Get cached file size for a filename from the JSON data."""
        # This is a basic implementation - sizes will be loaded when platforms are loaded
        # For now, return empty string as sizes will be populated from the JSON data
        return ''
    
    def set_platform_list(self, platform_id, items):
        """Set the list of items for a specific platform."""
        self.platform_lists[platform_id] = items
        
        # Find the correct tab index for this platform and update it
        for i in range(self.result_list.count()):
            if self.result_list.tabText(i) == self.platforms[platform_id]['tab_name']:
                tree_widget = self.result_list.widget(i)
                self._populate_platform_tree_with_sizes(tree_widget, items, platform_id)
                break
    
    def _populate_platform_tree_with_sizes(self, tree_widget, items, platform_id):
        """Populate a platform tree widget with file data and sizes from JSON."""
        tree_widget.clear()
        
        # Handle loading state
        if isinstance(items, list) and len(items) == 1 and isinstance(items[0], str):
            if "Loading..." in items[0]:
                item = SortableTreeWidgetItem(['Loading... this will take a moment', ''])
                tree_widget.addTopLevelItem(item)
                return
            elif "Error loading" in items[0]:
                item = SortableTreeWidgetItem([items[0], ''])
                tree_widget.addTopLevelItem(item)
                return
        
        # Load sizes from JSON cache
        file_sizes = self._load_file_sizes_from_json(platform_id)
        
        # Populate tree with files and sizes
        for filename in items:
            if isinstance(filename, str):
                size = file_sizes.get(filename, '')
                item = SortableTreeWidgetItem([filename, size])
                tree_widget.addTopLevelItem(item)
    
    def _load_file_sizes_from_json(self, platform_id):
        """Load file sizes from JSON cache for a specific platform."""
        file_sizes = {}
        try:
            json_file = f"config/{platform_id}_filelist.json"
            if os.path.exists(json_file):
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list) and data:
                        if isinstance(data[0], dict):
                            # New format with sizes
                            for item in data:
                                name = item.get('name')
                                size = item.get('size', '')
                                if name:
                                    file_sizes[name] = size
        except Exception as e:
            print(f"Error loading file sizes for {platform_id}: {e}")
        return file_sizes

    def initUI(self):
        """Initialize the user interface."""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(3)  # Further reduce spacing between elements
        main_layout.setContentsMargins(8, 8, 8, 8)  # Reduce window margins

        # ============ TOP SECTION: Software List and Queue Side-by-Side ============
        top_splitter = QSplitter(Qt.Horizontal)
        
        # Left side: Software List
        software_widget = QWidget()
        software_layout = QVBoxLayout(software_widget)
        software_layout.setContentsMargins(5, 5, 5, 5)
        
        # Software header and search
        software_header = QLabel('Software')
        software_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        software_layout.addWidget(software_header)
        
        # Search and filter container
        search_filter_layout = QVBoxLayout()
        
        # Search bar and filters button in horizontal layout
        search_bar_layout = QHBoxLayout()
        
        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText('Search...')
        self.search_box.textChanged.connect(self.update_results)
        search_bar_layout.addWidget(self.search_box)
        
        # Filters button
        self.filters_button = QPushButton('Filters')
        self.filters_button.setCheckable(True)
        self.filters_button.clicked.connect(self.toggle_region_filter)
        search_bar_layout.addWidget(self.filters_button)
        
        search_filter_layout.addLayout(search_bar_layout)
        
        # Region filter group (initially hidden)
        region_group = QGroupBox("Filter by Region")
        region_group.setStyleSheet("QGroupBox { padding-top: 15px; margin-top: 5px; }")
        region_group.setVisible(False)
        self.region_filter_group = region_group  # Store reference for toggling
        region_layout = QGridLayout()
        
        # Create region checkboxes
        self.region_checkboxes = {}
        regions = [
            "USA", "Canada", "Europe", "Japan", "Australia",
            "Korea", "Spain", "Germany", "France", "Italy",
            "World",  # For multi-language/region releases
            "Other"  # For games that don't match other regions
        ]
        
        row = 0
        col = 0
        for region in regions:
            checkbox = QCheckBox(region)
            checkbox.stateChanged.connect(self.update_results)
            region_layout.addWidget(checkbox, row, col)
            self.region_checkboxes[region] = checkbox
            
            col += 1
            if col > 2:  # 3 checkboxes per row
                col = 0
                row += 1
        
        region_group.setLayout(region_layout)
        search_filter_layout.addWidget(region_group)
        
        software_layout.addLayout(search_filter_layout)
        
        # Create result list (software tabs)
        self.result_list = QTabWidget()
        
        # Create tabs based on the platforms configuration - using QTreeWidget for file sizes
        for platform_id, data in self.platforms.items():
            tree_widget = QTreeWidget()
            tree_widget.setColumnCount(2)
            tree_widget.setHeaderLabels(['Name', 'Size'])
            
            # Configure columns
            header = tree_widget.header()
            header.setSectionsMovable(False)
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, header.ResizeMode.Stretch)  # Name column stretches
            header.setSectionResizeMode(1, header.ResizeMode.Fixed)    # Size column fixed
            tree_widget.setColumnWidth(1, 100)  # Fixed width for size column
            
            # Enable sorting
            tree_widget.setSortingEnabled(True)
            tree_widget.sortByColumn(0, Qt.AscendingOrder)  # Default sort by name
            
            # Set sorting indicator to be visible
            tree_widget.header().setSortIndicatorShown(True)
            
            tree_widget.setAllColumnsShowFocus(True)
            tree_widget.setUniformRowHeights(True)
            tree_widget.setRootIsDecorated(False)  # No tree indicators
            
            # Add initial items
            self._populate_platform_tree(tree_widget, self.platform_lists[platform_id])
            
            tree_widget.itemSelectionChanged.connect(self.update_add_to_queue_button)
            tree_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.result_list.addTab(tree_widget, data['tab_name'])
        
        self.result_list.currentChanged.connect(self.update_add_to_queue_button)
        self.result_list.currentChanged.connect(self.update_checkboxes_for_platform)
        software_layout.addWidget(self.result_list)

        # Connect the itemSelectionChanged signals
        for i in range(self.result_list.count()):
            self.result_list.widget(i).itemSelectionChanged.connect(self.update_add_to_queue_button)
            self.result_list.widget(i).setSelectionMode(QAbstractItemView.ExtendedSelection)

        # Add to queue button
        self.add_to_queue_button = QPushButton('Add to Queue')
        self.add_to_queue_button.clicked.connect(self.add_to_queue)
        self.add_to_queue_button.setEnabled(False)
        software_layout.addWidget(self.add_to_queue_button)
        
        # Right side: Queue
        queue_widget = QWidget()
        queue_layout = QVBoxLayout(queue_widget)
        queue_layout.setContentsMargins(5, 5, 5, 5)
        
        # Queue header
        queue_header = QLabel('Download Queue')
        queue_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        queue_layout.addWidget(queue_header)
        
        # Queue list with columns
        self.queue_list = QTreeWidget()
        self.queue_list.setColumnCount(3)
        self.queue_list.setHeaderLabels(['Name', 'Size', 'Actions'])
        
        # Configure column properties to match file list styling
        header = self.queue_list.header()
        header.setSectionsMovable(False)  # Prevent column reordering
        header.setStretchLastSection(False)  # Don't stretch last column
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)  # Name column stretches
        header.setSectionResizeMode(1, header.ResizeMode.Fixed)    # Size column fixed width
        header.setSectionResizeMode(2, header.ResizeMode.Fixed)    # Actions column fixed width
        
        # Set column widths to match file list proportions
        self.queue_list.setColumnWidth(1, 100)   # Size column - same as file list
        self.queue_list.setColumnWidth(2, 60)    # Actions column for buttons
        
        # Disable sorting for queue to preserve manual ordering
        self.queue_list.setSortingEnabled(False)
        self.queue_list.header().setSortIndicatorShown(False)
        
        # Match file list appearance settings
        self.queue_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.queue_list.itemSelectionChanged.connect(self.update_remove_from_queue_button)
        self.queue_list.setAllColumnsShowFocus(True)
        self.queue_list.setUniformRowHeights(True)
        self.queue_list.setRootIsDecorated(False)  # No tree indicators like file list
        self.queue_list.setAlternatingRowColors(False)  # Match file list
        self.queue_list.setMinimumHeight(150)
        
        queue_layout.addWidget(self.queue_list)
        
        # Queue control buttons (only remove button now)
        queue_buttons_layout = QHBoxLayout()
        
        # Remove from queue button
        self.remove_from_queue_button = QPushButton('Remove from Queue')
        self.remove_from_queue_button.clicked.connect(self.remove_from_queue)
        self.remove_from_queue_button.setEnabled(False)
        queue_buttons_layout.addWidget(self.remove_from_queue_button)
        
        queue_layout.addLayout(queue_buttons_layout)
        
        # Add both widgets to the splitter
        top_splitter.addWidget(software_widget)
        top_splitter.addWidget(queue_widget)
        # top_splitter.setSizes([600, 600])  # Removed for auto-sizing
        
        main_layout.addWidget(top_splitter)

        # ============ MIDDLE SECTION: Settings Side-by-Side ============
        settings_splitter = QSplitter(Qt.Horizontal)
        
        # Create general and platform-specific options side by side
        general_options_widget, platform_options_widget = self.create_options_side_by_side()
        
        settings_splitter.addWidget(general_options_widget)
        settings_splitter.addWidget(platform_options_widget)
        
        # Make the settings_splitter handle non-movable by the user
        settings_splitter_handle = settings_splitter.handle(1)
        if settings_splitter_handle:
            settings_splitter_handle.setDisabled(True)
        # Set initial equal sizes for the settings_splitter
        settings_splitter.setSizes([350, 350]) # Adjust if necessary

        main_layout.addWidget(settings_splitter)

        # ============ CONTROL BUTTONS: Settings and Start Side-by-Side ============
        control_buttons_layout = QHBoxLayout()
        
        # Add stretch to center the buttons
        control_buttons_layout.addStretch()
        
        self.settings_button = QPushButton('Settings')
        self.settings_button.clicked.connect(self.open_settings)
        control_buttons_layout.addWidget(self.settings_button)
        
        self.start_pause_button = QPushButton('Start')
        self.start_pause_button.clicked.connect(self.start_or_pause_download)
        control_buttons_layout.addWidget(self.start_pause_button)
        
        # Add stretch to center the buttons
        control_buttons_layout.addStretch()
        
        main_layout.addLayout(control_buttons_layout)

        # ============ PROGRESS INDICATORS ============
        # Create the toggle button instance here, as it's used by toggle_output_window
        # and create_collapsible_output_section will no longer create it.
        self.output_toggle_button = QPushButton('Show Logs') # Initial text
        self.output_toggle_button.clicked.connect(self.toggle_output_window)
        # self.output_window is already created and will be managed by create_collapsible_output_section

        # Status header to show current operation
        self.status_header = QLabel('Ready')
        self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #666;")
        self.status_header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_header)
        
        progress_header = QLabel('Progress')
        progress_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        main_layout.addWidget(progress_header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.progress_bar)

        # Download status information
        download_status_layout = QHBoxLayout()
        
        # Left side for speed and ETA
        status_left = QVBoxLayout()
        download_info_header = QLabel('Download Speed & ETA')
        status_left.addWidget(download_info_header)
        
        self.download_speed_label = QLabel()
        status_left.addWidget(self.download_speed_label)
        
        self.download_eta_label = QLabel()
        status_left.addWidget(self.download_eta_label)
        
        download_status_layout.addLayout(status_left)
        download_status_layout.addStretch()
        
        # Right side for file size
        status_right = QVBoxLayout()
        filesize_header = QLabel('File Size')
        filesize_header.setAlignment(Qt.AlignRight)
        status_right.addWidget(filesize_header)
        
        self.download_size_label = QLabel()
        self.download_size_label.setAlignment(Qt.AlignRight)
        status_right.addWidget(self.download_size_label)
        
        # Empty label for alignment
        status_right.addWidget(QLabel())
        
        download_status_layout.addLayout(status_right)
        main_layout.addLayout(download_status_layout)

        # ============ BOTTOM SECTION: Collapsible Output Window (Window only) ============
        # This method will now just return the frame with the output_window
        self.output_frame = self.create_collapsible_output_section()
        main_layout.addWidget(self.output_frame) # Add the frame containing the text area

        # ============ LOGS TOGGLE BUTTON (at the very bottom, right-justified) ============
        logs_button_layout = QHBoxLayout()
        logs_button_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        logs_button_layout.addStretch()
        logs_button_layout.addWidget(self.output_toggle_button) # Add the pre-created button
        main_layout.addLayout(logs_button_layout)

        self.setLayout(main_layout)
        self.setWindowTitle('Myrient Downloader')
        
        # Set a reasonable width but let height be determined by content
        self.setMinimumWidth(1000)
        self.setMaximumWidth(1400)
        
        # Initialize checkbox visibility based on the current platform
        self.update_checkboxes_for_platform()
        
        # Let Qt calculate the optimal size based on content, then show
        self.adjustSize()
        
        # Ensure the window doesn't get too small
        current_size = self.size()
        if current_size.height() < 500:
            self.resize(current_size.width(), 500)
        
        # Initially hide the region filter
        region_group.setVisible(False)
        
        self.show()
        
        # Store region group reference for toggling visibility
        self.region_filter_group = region_group
    
    def create_collapsible_output_section(self):
        """Create a collapsible output window section."""
        # Create the main frame
        output_frame = QFrame()
        output_frame.setFrameStyle(QFrame.StyledPanel)
        output_layout = QVBoxLayout(output_frame)
        output_layout.setContentsMargins(5, 5, 5, 5)
        
        # Configure output window
        self.output_window.setMinimumHeight(200)
        self.output_window.setMaximumHeight(400)
        
        # Add to layout and set initial visibility
        output_layout.addWidget(self.output_window)
        self.output_window.setVisible(False)
        output_frame.setVisible(False)
        
        # Store frame for later access
        self.output_frame = output_frame
        
        return output_frame

    def toggle_output_window(self):
        """Toggle the visibility of the output window."""
        if self.output_frame.isVisible():
            self.output_frame.setVisible(False)
            self.output_toggle_button.setText('Show Logs')
            # Resize window to fit content without output section
            self.adjustSize()
        else:
            self.output_frame.setVisible(True)
            self.output_window.setVisible(True) # Ensure content is visible when frame is
            self.output_toggle_button.setText('Hide Logs')
            # Let the window expand to accommodate the output section
            self.adjustSize()
    
    # Removed animation helper methods _on_hide_animation_finished and _on_show_animation_finished

    def create_options_side_by_side(self):
        """Create general and platform-specific options side by side."""
        # General options widget
        general_widget = QWidget()
        general_layout = QVBoxLayout(general_widget)
        general_layout.setContentsMargins(5, 5, 5, 5)
        
        general_options_group = QGroupBox("General Options")
        general_options_group.setStyleSheet("QGroupBox { padding-top: 15px; margin-top: 5px; font-weight: bold; }")
        general_options_layout = QVBoxLayout()
        
        # Create general options grid
        general_grid = QGridLayout()
        general_grid.setHorizontalSpacing(20)
        general_grid.setVerticalSpacing(10)
        
        # Add general options
        row = 0
        self.split_checkbox = QCheckBox('Split for FAT32 (if > 4GB)')
        self.split_checkbox.setChecked(self.settings_manager.split_large_files)
        general_grid.addWidget(self.split_checkbox, row, 0)
        
        self.keep_unsplit_dec_checkbox = QCheckBox('Keep unsplit file')
        self.keep_unsplit_dec_checkbox.setChecked(self.settings_manager.keep_unsplit_file)
        general_grid.addWidget(self.keep_unsplit_dec_checkbox, row, 1)
        
        row += 1
        self.organize_content_checkbox = QCheckBox('Group downloaded files per game')
        self.organize_content_checkbox.setChecked(self.settings_manager.organize_content_to_folders)
        general_grid.addWidget(self.organize_content_checkbox, row, 0, 1, 2)
        
        general_options_layout.addLayout(general_grid)
        general_options_group.setLayout(general_options_layout)
        general_layout.addWidget(general_options_group)
        # Removed general_layout.addStretch() to allow groupbox to potentially fill more space
        
        # Platform-specific options widget
        platform_widget = QWidget()
        platform_layout = QVBoxLayout(platform_widget)
        platform_layout.setContentsMargins(5, 5, 5, 5)
        
        self.platform_options_group = QGroupBox("Platform-Specific Options")
        self.platform_options_group.setStyleSheet("QGroupBox { padding-top: 15px; margin-top: 5px; font-weight: bold; }")
        platform_options_layout = QVBoxLayout()
        
        # PS3 specific options
        self.ps3_options_widget = QWidget()
        ps3_layout = QVBoxLayout(self.ps3_options_widget)
        ps3_layout.setContentsMargins(0, 0, 0, 0)
        
        ps3_grid = QGridLayout()
        ps3_grid.setHorizontalSpacing(20)
        ps3_grid.setVerticalSpacing(10)
        
        # PS3 options
        row = 0
        self.decrypt_checkbox = QCheckBox('Decrypt using PS3Dec')
        self.decrypt_checkbox.setChecked(self.settings_manager.decrypt_iso)
        ps3_grid.addWidget(self.decrypt_checkbox, row, 0)
        
        self.keep_enc_checkbox = QCheckBox('Keep encrypted PS3 ISO')
        self.keep_enc_checkbox.setChecked(self.settings_manager.keep_encrypted_iso)
        ps3_grid.addWidget(self.keep_enc_checkbox, row, 1)
        
        row += 1
        self.extract_ps3_checkbox = QCheckBox('Extract ISO using extractps3iso')
        self.extract_ps3_checkbox.setChecked(self.settings_manager.extract_ps3_iso)
        ps3_grid.addWidget(self.extract_ps3_checkbox, row, 0, 1, 2)
        
        row += 1
        self.keep_decrypted_iso_checkbox = QCheckBox('Keep decrypted ISO after extraction')
        self.keep_decrypted_iso_checkbox.setChecked(self.settings_manager.keep_decrypted_iso_after_extraction)
        ps3_grid.addWidget(self.keep_decrypted_iso_checkbox, row, 0, 1, 2)
        
        row += 1
        ps3_grid.setRowMinimumHeight(row, 5)
        
        row += 1
        self.keep_dkey_checkbox = QCheckBox('Keep PS3 ISO dkey file')
        self.keep_dkey_checkbox.setChecked(self.settings_manager.keep_dkey_file)
        ps3_grid.addWidget(self.keep_dkey_checkbox, row, 0, 1, 2)
        
        ps3_layout.addLayout(ps3_grid)
        platform_options_layout.addWidget(self.ps3_options_widget)
        
        # PSN specific options
        self.psn_options_widget = QWidget()
        psn_layout = QGridLayout(self.psn_options_widget)
        psn_layout.setContentsMargins(0, 0, 0, 0)
        
        self.split_pkg_checkbox = QCheckBox('Split PKG')
        self.split_pkg_checkbox.setChecked(self.settings_manager.split_pkg)
        psn_layout.addWidget(self.split_pkg_checkbox, 0, 0)
        
        platform_options_layout.addWidget(self.psn_options_widget)
        platform_options_layout.addStretch()
        
        self.platform_options_group.setLayout(platform_options_layout)
        platform_layout.addWidget(self.platform_options_group)
        # Removed platform_layout.addStretch() to allow groupbox to potentially fill more space
        
        # Connect signals for all checkboxes
        self._connect_checkbox_signals()
        
        # Set initial visibility states
        self.update_all_checkbox_states()
        self.ps3_options_widget.setVisible(False)
        self.psn_options_widget.setVisible(False)
        
        return general_widget, platform_widget
    
    def _connect_checkbox_signals(self):
        """Connect signals for all checkboxes."""
        # General checkboxes
        self.split_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('split_large_files', state))
        self.keep_unsplit_dec_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('keep_unsplit_file', state))
        self.organize_content_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('organize_content_to_folders', state))
        
        # PS3 checkboxes
        self.decrypt_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('decrypt_iso', state))
        self.extract_ps3_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('extract_ps3_iso', state))
        self.keep_enc_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('keep_encrypted_iso', state))
        self.keep_dkey_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('keep_dkey_file', state))
        self.keep_decrypted_iso_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('keep_decrypted_iso_after_extraction', state))
        
        # PSN checkbox
        self.split_pkg_checkbox.stateChanged.connect(lambda state: self.handle_checkbox_change('split_pkg', state))

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
        """Filter the software list based on search text and selected regions."""
        search_term = self.search_box.text().lower().split()
        selected_regions = [region for region, checkbox in self.region_checkboxes.items()
                          if checkbox.isChecked()]
        
        # Get the current platform based on the active tab
        current_tab = self.result_list.currentIndex()
        platform_ids = list(self.platforms.keys())
        if 0 <= current_tab < len(platform_ids):
            current_platform = platform_ids[current_tab]
            list_to_search = self.platform_lists[current_platform]
            
            # Apply search filter
            filtered_list = [item for item in list_to_search if all(word in item.lower() for word in search_term)]
            
            def has_exact_region(item, region):
                """Check if item has exact region match in parentheses."""
                return f"({region})" in item or f"({region.lower()})" in item.lower()
            
            def is_world_release(item):
                """Check if item is a World release."""
                return "(world)" in item.lower() or has_exact_region(item, "World")
            
            # Apply region filter if any regions are selected
            if selected_regions:
                if "World" in selected_regions:
                    # Handle World releases
                    world_matches = [item for item in filtered_list if is_world_release(item)]
                    other_regions = [r for r in selected_regions if r not in ["World", "Other"]]
                    
                    if other_regions or "Other" in selected_regions:
                        # Get items matching other selected regions exactly
                        region_matches = []
                        if other_regions:
                            for item in filtered_list:
                                if any(has_exact_region(item, region) for region in other_regions):
                                    region_matches.append(item)
                        
                        if "Other" in selected_regions:
                            # Add items that don't match any region exactly and aren't world releases
                            no_region_matches = [
                                item for item in filtered_list
                                if not is_world_release(item) and not any(
                                    has_exact_region(item, region)
                                    for region in self.region_checkboxes.keys()
                                    if region not in ["World", "Other"]
                                )
                            ]
                            filtered_list = list(set(world_matches + region_matches + no_region_matches))
                        else:
                            filtered_list = list(set(world_matches + region_matches))
                    else:
                        # Only World releases
                        filtered_list = world_matches
                
                elif "Other" in selected_regions:
                    # Handle Other (excluding World releases)
                    standard_regions = [r for r in selected_regions if r != "Other"]
                    if standard_regions:
                        # Get items matching standard regions exactly
                        standard_matches = []
                        for item in filtered_list:
                            if any(has_exact_region(item, region) for region in standard_regions):
                                standard_matches.append(item)
                        
                        # Get items not matching any region exactly and not world releases
                        no_region_matches = [
                            item for item in filtered_list
                            if not is_world_release(item) and not any(
                                has_exact_region(item, region)
                                for region in self.region_checkboxes.keys()
                                if region not in ["World", "Other"]
                            )
                        ]
                        filtered_list = list(set(standard_matches + no_region_matches))
                    else:
                        # Only "Other" is selected - show items not matching any region exactly and not world releases
                        filtered_list = [
                            item for item in filtered_list
                            if not is_world_release(item) and not any(
                                has_exact_region(item, region)
                                for region in self.region_checkboxes.keys()
                                if region not in ["World", "Other"]
                            )
                        ]
                else:
                    # Normal region filtering - match regions exactly
                    filtered_list = [
                        item for item in filtered_list
                        if any(has_exact_region(item, region) for region in selected_regions)
                    ]
            
            # Clear the current tree widget and add the filtered items
            current_tree_widget = self.result_list.currentWidget()
            self._populate_platform_tree_with_sizes(current_tree_widget, filtered_list, current_platform)
    
    def update_add_to_queue_button(self):
        """Enable or disable the add to queue button based on selection."""
        current_widget = self.result_list.currentWidget()
        if current_widget:
            self.add_to_queue_button.setEnabled(bool(current_widget.selectedItems()))
        else:
            self.add_to_queue_button.setEnabled(False)

    def update_remove_from_queue_button(self):
        """Enable or disable the remove from queue button based on selection."""
        selected = self.queue_list.selectedItems()
        self.remove_from_queue_button.setEnabled(bool(selected))
    
    def add_to_queue(self):
        """Add selected items to the download queue."""
        selected_items = self.result_list.currentWidget().selectedItems()
        current_tab = self.result_list.currentIndex()
        platform_ids = list(self.platforms.keys())
        
        if 0 <= current_tab < len(platform_ids):
            current_platform = platform_ids[current_tab]
            
            # Create adapter objects for tree widget items to work with app controller
            class TreeItemAdapter:
                def __init__(self, tree_item):
                    self.tree_item = tree_item
                def text(self):
                    return self.tree_item.text(0)  # Return first column text
            
            adapted_items = [TreeItemAdapter(item) for item in selected_items]
            added_count = self.app_controller.add_to_queue(
                adapted_items, current_platform, self.platforms, self.queue_list
            )
            
            # Update all button states after adding items
            self.update_all_queue_button_states()
    
    def remove_from_queue(self):
        """Remove selected items from the download queue."""
        selected_items = self.queue_list.selectedItems()
        if not selected_items:
            return
        
        # No need for conversion since AppController now handles QTreeWidgetItems directly
        removed_count = self.app_controller.remove_from_queue(selected_items, self.queue_list)
        
        # Update button states for all remaining items
        self.update_remove_from_queue_button()
        self.update_all_queue_button_states()
    
    def move_queue_item_up_inline(self, item):
        """Move the specified queue item up one position (called from inline buttons)."""
        if not item:
            return
            
        current_index = self.queue_list.indexOfTopLevelItem(item)
        
        if current_index > 0:
            # Take the item out and insert it one position up
            taken_item = self.queue_list.takeTopLevelItem(current_index)
            self.queue_list.insertTopLevelItem(current_index - 1, taken_item)
            
            # Reselect the moved item
            self.queue_list.setCurrentItem(taken_item)
            
            # Save the queue with new order
            self.app_controller.save_queue(self.queue_list)
            
            # Recreate buttons for all items and update their states
            self.recreate_all_queue_buttons()
    
    def move_queue_item_down_inline(self, item):
        """Move the specified queue item down one position (called from inline buttons)."""
        if not item:
            return
            
        current_index = self.queue_list.indexOfTopLevelItem(item)
        total_items = self.queue_list.topLevelItemCount()
        
        if current_index < total_items - 1:
            # Take the item out and insert it one position down
            taken_item = self.queue_list.takeTopLevelItem(current_index)
            self.queue_list.insertTopLevelItem(current_index + 1, taken_item)
            
            # Reselect the moved item
            self.queue_list.setCurrentItem(taken_item)
            
            # Save the queue with new order
            self.app_controller.save_queue(self.queue_list)
            
            # Recreate buttons for all items and update their states
            self.recreate_all_queue_buttons()

    def update_all_queue_button_states(self):
        """Update button states for all queue items."""
        for i in range(self.queue_list.topLevelItemCount()):
            item = self.queue_list.topLevelItem(i)
            if hasattr(item, 'update_button_states'):
                try:
                    item.update_button_states(self.queue_list)
                except RuntimeError:
                    # Button was deleted, skip this item
                    continue
    
    def recreate_all_queue_buttons(self):
        """Recreate buttons for all queue items after moves."""
        for i in range(self.queue_list.topLevelItemCount()):
            item = self.queue_list.topLevelItem(i)
            if hasattr(item, 'create_buttons'):
                # Always reset and recreate buttons after a move operation
                # because takeTopLevelItem/insertTopLevelItem destroys widgets
                item.buttons_created = False
                item.up_button = None
                item.down_button = None
                item.create_buttons(self.queue_list)
                # Ensure button states are updated after creation
                item.update_button_states(self.queue_list)

    def move_queue_item_up(self):
        """Move the selected queue item up one position (legacy method for compatibility)."""
        selected = self.queue_list.selectedItems()
        if len(selected) != 1:
            return
        self.move_queue_item_up_inline(selected[0])
    
    def move_queue_item_down(self):
        """Move the selected queue item down one position (legacy method for compatibility)."""
        selected = self.queue_list.selectedItems()
        if len(selected) != 1:
            return
        self.move_queue_item_down_inline(selected[0])
    
    def open_settings(self):
        """Open the settings dialog."""
        dlg = SettingsDialog(self.settings_manager, self.config_manager, self)
        if dlg.exec_() == QDialog.Accepted:
            QMessageBox.information(self, "Settings", "Settings saved.")
            # Optionally, update directories on disk if changed
            self.settings_manager.create_directories()
    

    def closeEvent(self, event):
        """Handle the close event."""
        print("Window closing, cleaning up...")
        
        try:
            # Restore stdout first to ensure we can see any errors
            if hasattr(self, 'output_window') and self.output_window:
                self.output_window.restore_stdout()
                
            # Stop any active downloads/processing first
            if hasattr(self, 'app_controller') and self.app_controller:
                # Check if user had manually paused before closing
                was_paused_before_shutdown = self.app_controller.is_paused
                
                self.app_controller.stop_processing(force_stop=True)
                
                # Save state based on what the user was doing before shutdown
                try:
                    if hasattr(self, 'queue_list') and self.queue_list:
                        if was_paused_before_shutdown:
                                                        # User had paused manually, so save pause state for resume
                                                        self.app_controller.save_pause_state(self.queue_list, force_save=True)
                        else:
                            # User was not paused, just save regular queue
                            print("Saving queue...")
                            self.app_controller.save_queue(self.queue_list)
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e):
                        print("Queue widget deleted, skipping save")
                    else:
                        raise
            
            # Stop all threads
            self._stop_all_threads()
            
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                print("UI widgets already deleted during shutdown")
            else:
                print(f"Runtime error during shutdown: {str(e)}")
        except Exception as e:
            print(f"Error during shutdown: {str(e)}")
        finally:
            print("Window cleanup complete")
            # Always accept the event and schedule quit with shorter delay
            event.accept()
            QTimer.singleShot(50, QApplication.instance().quit)
    
    def _stop_all_threads(self):
        """Stop all running threads gracefully."""
        # Stop AppController operations with force_stop flag
        self.app_controller.stop_processing(force_stop=True)
        
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
        
        try:
            if button_text == 'Start':
                self.start_download()
            elif button_text == 'Pause':
                self.pause_download()
            elif button_text == 'Resume':
                self.resume_download()
        except Exception as e:
            print(f"Error in start_or_pause_download: {e}")
            self._reset_ui_state()

    def start_download(self):
        """Start downloading the selected items."""
        print("Starting download...")
        
        # Check if queue is empty
        if self.queue_list.topLevelItemCount() == 0:
            print("Queue is empty, nothing to download")
            return
        
        # Reset any previous state
        self._reset_download_state()
        
        # Disable the GUI buttons except pause
        self._disable_controls_during_processing()
        
        # Change button to Pause
        self.start_pause_button.setText('Pause')
        
        # Get current settings
        settings = self._get_current_settings()
        
        # Start processing using AppController
        try:
            self.app_controller.start_processing(self.queue_list, settings)
        except Exception as e:
            print(f"Error starting processing: {e}")
            self._reset_ui_state()
    
    def pause_download(self):
        """Pause the current download or extraction process."""
        print("Pausing download...")
        
        # Check if already paused (button is not "Pause")
        if self.start_pause_button.text() != 'Pause':
            print("Download is not running, ignoring pause request")
            return
        
        try:
            # Pause processing first
            self.app_controller.pause_processing()
            
            # Update UI state
            self.start_pause_button.setText('Resume')
            self._enable_controls_during_pause()
            
            print("Download paused successfully")
        except Exception as e:
            print(f"Error pausing download: {e}")
            self._reset_ui_state()
    
    def resume_download(self):
        """Resume a previously paused download."""
        print("Resuming download...")
        
        # Check if already resumed (button is not "Resume")
        if self.start_pause_button.text() != 'Resume':
            print("Download is not paused, ignoring resume request")
            return
        
        try:
            # Check if queue is empty
            if self.queue_list.topLevelItemCount() == 0:
                print("Queue is empty, cannot resume")
                self._reset_ui_state()
                return
            
            # Update UI first
            self.start_pause_button.setText('Pause')
            self._disable_controls_during_processing()
            
            # Get current settings
            settings = self._get_current_settings()
            
            # Resume processing using AppController
            self.app_controller.resume_processing(self.queue_list, settings)
            
            print("Download resumed successfully")
        except Exception as e:
            print(f"Error resuming download: {e}")
            self._on_error(f"Resume failed: {str(e)}")
            self._reset_ui_state()
    
    def _disable_controls_during_processing(self):
        """Disable GUI controls during processing."""
        self.settings_button.setEnabled(False)
        self.add_to_queue_button.setEnabled(False)
        self.remove_from_queue_button.setEnabled(False)
        self.queue_list.setEnabled(False)  # Disable queue interaction including inline buttons
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
        self.queue_list.setEnabled(True)  # Re-enable queue interaction including inline buttons
        
        # Allow selection in the queue list
        # Keep using ExtendedSelection for QTreeWidget
        self.queue_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        
        # Update the remove from queue button state based on selection
        self.update_remove_from_queue_button()

    def _enable_all_buttons(self):
        """Re-enable all GUI buttons."""
        try:
            if hasattr(self, 'settings_button') and self.settings_button:
                self.settings_button.setEnabled(True)
            if hasattr(self, 'add_to_queue_button') and self.add_to_queue_button:
                self.add_to_queue_button.setEnabled(True)
            if hasattr(self, 'remove_from_queue_button') and self.remove_from_queue_button:
                self.remove_from_queue_button.setEnabled(True)
            if hasattr(self, 'queue_list') and self.queue_list:
                self.queue_list.setEnabled(True)  # Re-enable queue interaction including inline buttons
            if hasattr(self, 'decrypt_checkbox') and self.decrypt_checkbox:
                self.decrypt_checkbox.setEnabled(True)
            if hasattr(self, 'split_checkbox') and self.split_checkbox:
                self.split_checkbox.setEnabled(True)
            if hasattr(self, 'keep_dkey_checkbox') and self.keep_dkey_checkbox:
                self.keep_dkey_checkbox.setEnabled(True)
            if hasattr(self, 'keep_enc_checkbox') and self.keep_enc_checkbox:
                self.keep_enc_checkbox.setEnabled(True)
            if hasattr(self, 'keep_unsplit_dec_checkbox') and self.keep_unsplit_dec_checkbox:
                self.keep_unsplit_dec_checkbox.setEnabled(True)
            if hasattr(self, 'split_pkg_checkbox') and self.split_pkg_checkbox:
                self.split_pkg_checkbox.setEnabled(True)
            if hasattr(self, 'extract_ps3_checkbox') and self.extract_ps3_checkbox:
                self.extract_ps3_checkbox.setEnabled(True)
            if hasattr(self, 'keep_decrypted_iso_checkbox') and self.keep_decrypted_iso_checkbox:
                self.keep_decrypted_iso_checkbox.setEnabled(True)
            if hasattr(self, 'organize_content_checkbox') and self.organize_content_checkbox:
                self.organize_content_checkbox.setEnabled(True)
            if hasattr(self, 'start_pause_button') and self.start_pause_button:
                self.start_pause_button.setEnabled(True)
                # Only set to 'Start' if not paused on startup
                if not getattr(self, "was_paused_on_startup", False):
                    self.start_pause_button.setText('Start')
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                print("Some UI widgets have been deleted, skipping enable")
            else:
                raise
    
    def _reset_download_state(self):
        """Reset download state before starting new download."""
        # Don't reset state during shutdown to prevent unwanted operations
        if hasattr(self.app_controller, 'is_shutting_down') and self.app_controller.is_shutting_down:
            return
            
        # Clear any existing app controller state
        if hasattr(self.app_controller, 'is_paused'):
            self.app_controller.is_paused = False
        if hasattr(self.app_controller, 'current_operation'):
            self.app_controller.current_operation = None
        if hasattr(self.app_controller, 'current_item'):
            self.app_controller.current_item = None
        
        # Reset download manager state
        if hasattr(self.app_controller, 'download_manager'):
            self.app_controller.download_manager.is_paused = False
            self.app_controller.download_manager.current_operation = None
            if self.app_controller.download_manager.download_thread:
                # Stop any existing download thread
                self.app_controller.download_manager.download_thread.stop()
                self.app_controller.download_manager.download_thread = None
        
        # Reset processing manager state
        if hasattr(self.app_controller, 'processing_manager'):
            self.app_controller.processing_manager.is_paused = False
            self.app_controller.processing_manager.current_operation = None
        
        # Clear state manager
        from core.state_manager import StateManager
        StateManager.clear_pause_state()
    
    def _reset_ui_state(self):
        """Reset UI to a consistent state after errors."""
        print("Resetting UI state...")
        
        # Check if widgets still exist before accessing them
        try:
            if hasattr(self, 'start_pause_button') and self.start_pause_button:
                # Only set to 'Start' if not paused on startup
                if not getattr(self, "was_paused_on_startup", False):
                    self.start_pause_button.setText('Start')
                self.start_pause_button.setEnabled(True)
            
            # Re-enable all controls
            self._enable_all_buttons()
            
            # Clear progress indicators
            if hasattr(self, 'progress_bar') and self.progress_bar:
                self.progress_bar.setValue(0)
            if hasattr(self, 'download_speed_label') and self.download_speed_label:
                self.download_speed_label.clear()
            if hasattr(self, 'download_eta_label') and self.download_eta_label:
                self.download_eta_label.clear()
            if hasattr(self, 'download_size_label') and self.download_size_label:
                self.download_size_label.clear()
            
            # Reset download state
            self._reset_download_state()
            
            print("UI state reset complete")
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                print("UI widgets have been deleted, skipping UI reset")
            else:
                raise

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

    def toggle_region_filter(self):
        """Toggle visibility of the region filter group."""
        if hasattr(self, 'region_filter_group') and self.region_filter_group:
            is_visible = self.region_filter_group.isVisible()
            self.region_filter_group.setVisible(not is_visible)
            self.filters_button.setChecked(not is_visible)
            
    def _on_queue_updated(self):
        """Handle queue update signal from AppController."""
        try:
            self.update_add_to_queue_button()
            self.update_remove_from_queue_button()
        except Exception as e:
            print(f"Error updating queue buttons: {e}")
            
    def _on_operation_complete(self):
        """Handle operation complete signal from AppController."""
        # Don't handle operation complete during shutdown
        if hasattr(self.app_controller, 'is_shutting_down') and self.app_controller.is_shutting_down:
            return
        
        # Re-enable all buttons
        self._enable_all_buttons()
        
        # Clear status labels and reset status header
        self.status_header.setText("Ready")
        self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #666;")
        self.download_speed_label.clear()
        self.download_eta_label.clear()
        self.download_size_label.clear()
        self.progress_bar.setValue(0)
        
        # Clear the queue file since processing is complete
        self.app_controller.save_queue(self.queue_list)
        
        # Reset download state completely
        self._reset_download_state()
        
    
    def _on_operation_paused(self):
        """Handle operation paused signal from AppController."""
        print("Operation paused signal received")
        
        # Update status header to show paused state
        self.status_header.setText("Paused")
        self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #ffd700;")
        
        # Ensure button shows Resume
        self.start_pause_button.setText('Resume')
        
        # Enable controls during pause
        self._enable_controls_during_pause()
        
        print("Operation paused handling finished")

    def _on_status_updated(self, status):
        """Handle status update signal from AppController."""
        # Update the status header with current operation
        if status == "DOWNLOADING":
            self.status_header.setText("Downloading...")
            self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #0080ff;")
        elif status == "UNZIPPING":
            self.status_header.setText("Extracting archive...")
            self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #ff8c00;")
        elif status == "DECRYPTING":
            self.status_header.setText("Decrypting...")
            self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #ff4500;")
        elif status == "EXTRACTING":
            self.status_header.setText("Extracting ISO...")
            self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #32cd32;")
        elif status == "SPLITTING":
            self.status_header.setText("Splitting files...")
            self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #ff8c00;")
        elif status == "PAUSED":
            self.status_header.setText("Paused")
            self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #ffd700;")
        else:
            self.status_header.setText("Ready")
            self.status_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #666;")

    def _on_error(self, error_message):
        """Handle error signal from AppController."""
        # Show output window when there's an error
        if not self.output_window.isVisible():
            self.toggle_output_window()
        self.output_window.append(f"ERROR: {error_message}")
