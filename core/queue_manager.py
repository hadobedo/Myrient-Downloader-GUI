import os
import pickle
import re
from PyQt5.QtCore import Qt, QObject, pyqtSignal
from PyQt5.QtWidgets import QListWidgetItem
from PyQt5.QtGui import QFont, QBrush, QColor


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
        # First check if the new location exists
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'rb') as file:
                    self.queue_items = pickle.load(file)
            except Exception as e:
                print(f"Error loading {self.queue_file}: {e}. Starting with an empty queue.")
                self.queue_items = []
        else:
            # Check for old file in root directory
            old_queue_file = "queue.txt"
            if os.path.exists(old_queue_file):
                try:
                    # Load from old location
                    with open(old_queue_file, 'rb') as file:
                        self.queue_items = pickle.load(file)
                    
                    # Ensure config directory exists
                    os.makedirs(self.config_dir, exist_ok=True)
                    
                    # Save to new location
                    with open(self.queue_file, 'wb') as file:
                        pickle.dump(self.queue_items, file)
                    
                    # Remove old file after successful migration
                    os.remove(old_queue_file)
                    print(f"Migrated queue from root to {self.queue_file}")
                except Exception as e:
                    print(f"Error migrating queue: {str(e)}")
                    self.queue_items = []
            else:
                self.queue_items = []
        
        return self.queue_items
    
    def save_queue(self, queue_list_widget):
        """Save the current queue to file."""
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Save original names (Qt.UserRole data)
        queue_items = []
        for i in range(queue_list_widget.count()):
            item = queue_list_widget.item(i)
            # Get original name from UserRole if it exists, otherwise use displayed text
            if item.data(Qt.UserRole):
                queue_items.append(item.data(Qt.UserRole))
            else:
                queue_items.append(item.text())
        
        with open(self.queue_file, 'wb') as file:
            pickle.dump(queue_items, file)
        
        self.queue_items = queue_items
        self.queue_updated.emit()
    
    def add_to_queue(self, item_text, queue_list_widget, platforms):
        """Add selected items to the download queue."""
        # Check if item is already in queue by comparing original names
        already_in_queue = False
        for i in range(queue_list_widget.count()):
            queue_item = queue_list_widget.item(i)
            # Compare with original name stored in UserRole
            if queue_item.data(Qt.UserRole) == item_text:
                already_in_queue = True
                break
        
        if not already_in_queue:
            self.add_formatted_item_to_queue(item_text, queue_list_widget)
            return True
        return False
    
    def add_formatted_item_to_queue(self, item_text, queue_list_widget):
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

        queue_list_widget.addItem(list_item)
        return list_item
    
    def remove_from_queue(self, selected_items, queue_list_widget):
        """Remove selected items from the download queue."""
        items_to_remove = []
        
        for item in selected_items:
            items_to_remove.append(item)
        
        # Remove all marked items
        for item in items_to_remove:
            queue_list_widget.takeItem(queue_list_widget.row(item))
        
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
    
    def update_queue_status(self, queue_list_widget, item_original_name, status, color=None):
        """Update the queue item text to show the current operation status."""
        for i in range(queue_list_widget.count()):
            item = queue_list_widget.item(i)
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