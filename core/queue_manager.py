import os
import pickle
import re
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QSize
from PyQt5.QtWidgets import QTreeWidgetItem, QListWidgetItem
from PyQt5.QtGui import QFont, QBrush, QColor

from core.utils import format_file_size


class QueueManager(QObject):
    """Manages download queue operations separate from GUI."""
    
    queue_updated = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.queue_items = []
        self.config_dir = "config"
        self.queue_file = os.path.join(self.config_dir, "queue.txt")
    
    def load_queue(self):
        """Load the download queue from file."""
        try:
            # Check if new format file exists
            if os.path.exists(self.queue_file):
                with open(self.queue_file, 'rb') as file:
                    data = pickle.load(file)
                    # Check if data is in new format (list of dicts)
                    if data and isinstance(data[0], dict):
                        self.queue_items = data
                    else:
                        # Convert old format to new
                        self.queue_items = [{'name': name, 'size': ''} for name in data]
            else:
                # Check for old file in root directory
                old_queue_file = "queue.txt"
                if os.path.exists(old_queue_file):
                    try:
                        # Load from old location
                        with open(old_queue_file, 'rb') as file:
                            old_data = pickle.load(file)
                            self.queue_items = [{'name': name, 'size': ''} for name in old_data]
                        
                        # Migrate to new location
                        os.makedirs(self.config_dir, exist_ok=True)
                        with open(self.queue_file, 'wb') as file:
                            pickle.dump(self.queue_items, file)
                        
                        # Remove old file after successful migration
                        os.remove(old_queue_file)
                        print(f"Migrated queue to new format in {self.queue_file}")
                    except Exception as e:
                        print(f"Error migrating queue: {str(e)}")
                        self.queue_items = []
                else:
                    self.queue_items = []
        except Exception as e:
            print(f"Error loading {self.queue_file}: {e}. Starting with an empty queue.")
            self.queue_items = []
        
        return self.queue_items
    
    def save_queue(self, queue_list_widget):
        """Save the current queue to file."""
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Save both original names and file sizes
        queue_items = []
        for i in range(queue_list_widget.topLevelItemCount()):
            item = queue_list_widget.topLevelItem(i)
            item_data = {
                'name': item.data(0, Qt.UserRole) if item.data(0, Qt.UserRole) else item.text(0),
                'size': item.text(1)
            }
            queue_items.append(item_data)
        
        with open(self.queue_file, 'wb') as file:
            pickle.dump(queue_items, file)
        
        self.queue_items = queue_items
        self.queue_updated.emit()
    
    def add_to_queue(self, item_data, queue_list_widget, platforms):
        """Add selected items to the download queue."""
        # Handle both dict and string formats
        if isinstance(item_data, dict):
            item_text = item_data['name']
        else:
            item_text = item_data
            
        # Check if item is already in queue by comparing original names
        already_in_queue = False
        for i in range(queue_list_widget.topLevelItemCount()):
            queue_item = queue_list_widget.topLevelItem(i)
            # Compare with original name stored in UserRole
            if queue_item.data(0, Qt.UserRole) == item_text:
                already_in_queue = True
                break
        
        if not already_in_queue:
            self.add_formatted_item_to_queue(item_data, queue_list_widget)
            return True
        return False
    
    def add_formatted_item_to_queue(self, queue_data, queue_tree_widget):
        """Add an item to the queue list with file size column."""
        # Try to import QueueTreeWidgetItem, fallback to standard QTreeWidgetItem
        try:
            from gui.main_window import QueueTreeWidgetItem
            # Get the main window instance from the queue tree widget
            main_window = None
            parent = queue_tree_widget.parent()
            while parent:
                if hasattr(parent, 'move_queue_item_up_inline'):
                    main_window = parent
                    break
                parent = parent.parent()
            
            if main_window:
                tree_item = QueueTreeWidgetItem(['', '', ''], main_window)
            else:
                tree_item = QTreeWidgetItem()
        except ImportError:
            tree_item = QTreeWidgetItem()
        
        # Support both new format (dict) and old format (string)
        if isinstance(queue_data, dict):
            item_text = queue_data['name']
            size = queue_data.get('size', '')
        else:
            item_text = queue_data
            size = ''
        
        # Store original text as user data
        tree_item.setData(0, Qt.UserRole, item_text)
        
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

            # Set display text in first column
            tree_item.setText(0, clean_text)
            
            # Set size in second column - try to fetch if empty
            if not size:
                size = self._fetch_file_size_for_item(item_text)
            tree_item.setText(1, size)
            tree_item.setTextAlignment(1, Qt.AlignRight)  # Right-align size
        else:
            # No platform prefix found, just use text as is
            tree_item.setText(0, item_text)
            tree_item.setText(1, size)
            tree_item.setTextAlignment(1, Qt.AlignRight)

        queue_tree_widget.addTopLevelItem(tree_item)
        
        # Create inline buttons if this is a QueueTreeWidgetItem
        if hasattr(tree_item, 'create_buttons'):
            tree_item.create_buttons(queue_tree_widget)
        
        # Ensure columns are properly sized after adding item
        if queue_tree_widget.topLevelItemCount() == 1:  # Only resize on first item
            header = queue_tree_widget.header()
            # Don't try to calculate based on viewport width as it may not be accurate yet
            # Let the header resize modes handle the sizing instead
            if queue_tree_widget.columnCount() == 3:  # 3-column layout with actions
                # Size column and actions column should use their fixed widths
                # Name column will stretch to fill remaining space
                pass  # Let the resize modes handle it
        
        return tree_item
    
    def remove_from_queue(self, selected_items, queue_tree_widget):
        """Remove selected items from the download queue."""
        items_to_remove = []
        
        for item in selected_items:
            items_to_remove.append(item)
        
        # Remove all marked items
        for item in items_to_remove:
            index = queue_tree_widget.indexOfTopLevelItem(item)
            queue_tree_widget.takeTopLevelItem(index)
        
        return len(items_to_remove)
    
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
    
    def update_queue_status(self, queue_tree_widget, item_original_name, status, color=None, size=None):
        """Update the queue item text to show the current operation status (preserve original file size)."""
        for i in range(queue_tree_widget.topLevelItemCount()):
            item = queue_tree_widget.topLevelItem(i)
            if item.data(0, Qt.UserRole) == item_original_name:
                # Extract original text without any status
                text = item.data(0, Qt.UserRole)
                clean_text = re.sub(r' \([A-Z]+\)$', '', text)
                
                # Add the new status
                new_text = f"{clean_text} ({status})"
                item.setText(0, new_text)
                
                # Don't update size column - preserve original file size
                # Size column should only show the final file size, not download progress
                
                # Apply bold font
                font = QFont()
                font.setBold(True)
                item.setFont(0, font)
                item.setFont(1, font)
                
                # Apply color if specified
                if color:
                    item.setForeground(0, QBrush(color))
                    item.setForeground(1, QBrush(color))
                break
    
    def _fetch_file_size_for_item(self, item_text):
        """Fetch file size for a queue item."""
        try:
            # Extract platform and filename
            platform_id = self.get_platform_from_queue_item(item_text)
            filename = self.get_filename_from_queue_item(item_text)
            
            if not platform_id or not filename:
                return ""
            
            # Import here to avoid circular imports
            from core.config_manager import ConfigManager
            from core.download_manager import DownloadManager
            
            config_manager = ConfigManager()
            url = config_manager.get_url(platform_id, 'url')
            if not url:
                return ""
            
            download_url = DownloadManager.build_download_url(url, filename)
            
            # Get remote file size
            size_bytes = DownloadManager.get_remote_file_size(download_url)
            if size_bytes:
                return self._format_file_size(size_bytes)
                
        except Exception as e:
            print(f"Error fetching file size for {item_text}: {str(e)}")
        
        return ""
    
    def update_queue_item_sizes_async(self, queue_tree_widget):
        """Update queue item sizes asynchronously for better performance."""
        from PyQt5.QtCore import QThread, pyqtSignal
        
        class SizeUpdateThread(QThread):
            size_updated = pyqtSignal(int, str)  # row, size
            
            def __init__(self, queue_manager, queue_items):
                super().__init__()
                self.queue_manager = queue_manager
                self.queue_items = queue_items
            
            def run(self):
                for i, item_text in enumerate(self.queue_items):
                    if isinstance(item_text, dict):
                        name = item_text['name']
                        if not item_text.get('size'):
                            size = self.queue_manager._fetch_file_size_for_item(name)
                            if size:
                                self.size_updated.emit(i, size)
                    else:
                        size = self.queue_manager._fetch_file_size_for_item(item_text)
                        if size:
                            self.size_updated.emit(i, size)
        
        # Get current queue items
        queue_items = []
        for i in range(queue_tree_widget.topLevelItemCount()):
            item = queue_tree_widget.topLevelItem(i)
            original_name = item.data(0, Qt.UserRole)
            current_size = item.text(1)
            queue_items.append({'name': original_name, 'size': current_size})
        
        # Start background thread to update sizes
        if queue_items:
            self.size_thread = SizeUpdateThread(self, queue_items)
            self.size_thread.size_updated.connect(
                lambda row, size: self._update_item_size(queue_tree_widget, row, size)
            )
            self.size_thread.start()
    
    def _update_item_size(self, queue_tree_widget, row, size):
        """Update a specific queue item's size."""
        if row < queue_tree_widget.topLevelItemCount():
            item = queue_tree_widget.topLevelItem(row)
            if not item.text(1):  # Only update if size is empty
                item.setText(1, size)
    
    def _format_file_size(self, size_bytes):
        """Format file size for display."""
        return format_file_size(size_bytes)