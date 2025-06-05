import os
import re
from typing import List
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtGui import QColor, QBrush

from core.queue_manager import QueueManager
from core.download_manager import DownloadManager
from core.processing_manager import ProcessingManager
from core.state_manager import StateManager


class AppController(QObject):
    """Main application controller that coordinates all operations."""
    
    # Signals for GUI updates
    progress_updated = pyqtSignal(int)
    speed_updated = pyqtSignal(str)
    eta_updated = pyqtSignal(str)
    size_updated = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    queue_updated = pyqtSignal()
    operation_complete = pyqtSignal()
    operation_paused = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, settings_manager, config_manager, output_window, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.config_manager = config_manager
        self.output_window = output_window
        
        # Initialize managers
        self.queue_manager = QueueManager()
        self.download_manager = DownloadManager(settings_manager, config_manager, output_window, self)
        self.processing_manager = ProcessingManager(settings_manager, config_manager, output_window, self)
        
        # Application state
        self.is_paused = False
        self.current_operation = None
        self.current_item = None
        self.current_position = None
        self.current_file_path = None
        self.current_queue_item = None
        self.processed_items = 0
        self.total_items = 0
        
        # Connect manager signals
        self._connect_signals()
    
    def _connect_signals(self):
        """Connect signals from managers to controller."""
        # Queue manager signals
        self.queue_manager.queue_updated.connect(self.queue_updated.emit)
        
        # Download manager signals
        self.download_manager.progress_updated.connect(self.progress_updated.emit)
        self.download_manager.speed_updated.connect(self.speed_updated.emit)
        self.download_manager.eta_updated.connect(self.eta_updated.emit)
        self.download_manager.size_updated.connect(self.size_updated.emit)
        self.download_manager.download_paused.connect(self._on_download_paused)
        self.download_manager.error_occurred.connect(self.error_occurred.emit)
        
        # Processing manager signals
        self.processing_manager.progress_updated.connect(self.progress_updated.emit)
        self.processing_manager.status_updated.connect(self._on_status_updated)
        self.processing_manager.processing_paused.connect(self._on_processing_paused)
        self.processing_manager.error_occurred.connect(self.error_occurred.emit)
    
    def load_queue(self):
        """Load the download queue."""
        return self.queue_manager.load_queue()
    
    def save_queue(self, queue_list_widget):
        """Save the download queue."""
        self.queue_manager.save_queue(queue_list_widget)
    
    def add_to_queue(self, selected_items, current_platform, platforms, queue_list_widget):
        """Add selected items to the download queue."""
        added_count = 0
        platform_name = current_platform.upper()
        
        for item in selected_items:
            item_text = item.text()
            formatted_text = f"({platform_name}) {item_text}"
            
            if self.queue_manager.add_to_queue(formatted_text, queue_list_widget, platforms):
                added_count += 1
        
        if added_count > 0:
            self.save_queue(queue_list_widget)
        
        return added_count
    
    def remove_from_queue(self, selected_items, queue_list_widget):
        """Remove selected items from the download queue."""
        items_to_remove = []
        
        for item in selected_items:
            # Get the original name from the item's data
            original_name = item.data(Qt.UserRole) if item.data(Qt.UserRole) else item.text()
            
            # Check if this is a download in progress or paused
            is_current_download = (self.current_item == original_name and 
                                  self.current_file_path and 
                                  os.path.exists(self.current_file_path))
            
            if is_current_download:
                # Handle removal of current download with confirmation
                if self._handle_current_download_removal(item, original_name):
                    items_to_remove.append(item)
            else:
                items_to_remove.append(item)
        
        # Remove all marked items
        removed_count = self.queue_manager.remove_from_queue(items_to_remove, queue_list_widget)
        
        if removed_count > 0:
            self.save_queue(queue_list_widget)
        
        return removed_count
    
    def start_processing(self, queue_list_widget, settings):
        """Start processing the download queue."""
        self.is_paused = False
        
        # Check if resuming
        is_resuming_session = bool(self.current_item)
        
        if not is_resuming_session:
            # Fresh start
            self.processed_items = 0
            self.total_items = queue_list_widget.count()
            
            # Reset overwrite choices for new download session
            self.download_manager.reset_overwrite_choices()
            self.processing_manager.reset_overwrite_choices()
        
        # Process queue until empty
        while queue_list_widget.count() > 0 and not self.is_paused:
            # Get the first item in the queue
            current_queue_item = queue_list_widget.item(0)
            item_original_name = current_queue_item.data(Qt.UserRole) if current_queue_item.data(Qt.UserRole) else current_queue_item.text()
            
            if not is_resuming_session or self.current_item != item_original_name:
                self.processed_items += 1
            
            # Update current item
            self.current_item = item_original_name
            self.current_position = f"{self.processed_items}/{self.total_items}"
            self.current_queue_item = current_queue_item
            
            # Update queue item appearance
            self._update_queue_item_status(current_queue_item, "DOWNLOADING", QColor(0, 128, 255))
            
            # Process item based on its type
            platform_id = self.queue_manager.get_platform_from_queue_item(item_original_name)
            if platform_id:
                filename = self.queue_manager.get_filename_from_queue_item(item_original_name)
                self._process_item(platform_id, filename, self.current_position, settings, current_queue_item)
            else:
                self.error_occurred.emit(f"Could not determine platform for {item_original_name}")
            
            # Remove item from queue if not paused
            if not self.is_paused:
                queue_list_widget.takeItem(0)
                # Save queue immediately after removing completed item
                self.save_queue(queue_list_widget)
            
            is_resuming_session = False
        
        # Reset state if completed
        if not self.is_paused:
            self._reset_processing_state()
    
    def pause_processing(self):
        """Pause the current processing operation."""
        self.is_paused = True
        self.current_operation = 'paused'
        
        # Pause appropriate manager
        self.download_manager.pause_download()
        self.processing_manager.pause_processing()
        
        self.operation_paused.emit()
    
    def resume_processing(self, queue_list_widget, settings):
        """Resume a previously paused processing operation."""
        self.is_paused = False
        self.output_window.append(f"({self.current_position}) Resuming processing...\n")
        
        # Resume appropriate manager
        self.download_manager.resume_download()
        self.processing_manager.resume_processing()
        
        # Continue processing from where we left off
        self.start_processing(queue_list_widget, settings)
    
    def stop_processing(self):
        """Stop the current processing operation."""
        self.is_paused = True
        self.download_manager.stop_download()
        self.processing_manager.stop_processing()
    
    def check_for_paused_download(self, queue_list_widget):
        """Check if there is a paused download to resume."""
        pause_state = StateManager.load_pause_state()
        if not pause_state:
            return False
            
        # Clear the current queue
        queue_list_widget.clear()
        
        # Add the current paused item first with (PAUSED) status
        current_item_text = pause_state['current_item']
        paused_item = self.queue_manager.add_formatted_item_to_queue(current_item_text, queue_list_widget)
        
        # Update the item to show it's paused
        self._update_queue_item_status(paused_item, "PAUSED", QColor(255, 215, 0), "(PAUSED)")
        
        # Add remaining items from saved queue
        if 'remaining_queue' in pause_state and isinstance(pause_state['remaining_queue'], list):
            for item_text in pause_state['remaining_queue']:
                if item_text != current_item_text:
                    self.queue_manager.add_formatted_item_to_queue(item_text, queue_list_widget)
        
        # Restore state
        self.current_item = pause_state['current_item']
        self.current_operation = pause_state['operation']
        self.current_position = pause_state['queue_position']
        self.current_file_path = pause_state['file_path']
        self.processed_items = pause_state['processed_items']
        self.total_items = pause_state['total_items']
        self.is_paused = True
        
        # Save the queue to ensure it's current
        self.save_queue(queue_list_widget)
        
        return True
    
    def save_pause_state(self, queue_list_widget):
        """Save the current pause state."""
        if self.is_paused:
            # Get remaining queue items
            remaining_items = []
            for i in range(queue_list_widget.count()):
                item = queue_list_widget.item(i)
                if item.data(Qt.UserRole):
                    remaining_items.append(item.data(Qt.UserRole))
                else:
                    remaining_items.append(item.text())
            
            StateManager.save_pause_state(
                self.current_item,
                self.current_position,
                self.current_operation,
                self.current_file_path,
                self.processed_items,
                self.total_items,
                remaining_items
            )
        else:
            StateManager.clear_pause_state()
    
    def _process_item(self, platform_id, filename, queue_position, settings, queue_item):
        """Process a single item."""
        try:
            # Download the file
            self.current_operation = 'download'
            file_path = self.download_manager.download_item_by_platform(platform_id, filename, queue_position)
            
            if self.is_paused:
                return
            
            # Process the downloaded file
            self.current_operation = 'processing'
            self._process_downloaded_file(platform_id, file_path, filename, queue_position, settings, queue_item)
            
        except Exception as e:
            self.error_occurred.emit(f"Error processing {filename}: {str(e)}")
    
    def _process_downloaded_file(self, platform_id, file_path, filename, queue_position, settings, queue_item):
        """Process a downloaded file based on platform."""
        if not os.path.exists(file_path):
            self.output_window.append(f"({queue_position}) File no longer exists: {file_path}")
            return
        
        base_name = os.path.splitext(filename)[0]
        
        # Unzip the file (status will be updated by processing manager)
        extracted_files = self.processing_manager.unzip_file_with_pause_support(
            file_path, self.settings_manager.processing_dir, queue_position, base_name
        )
        
        if self.is_paused:
            return
        
        # Delete the zip file if it exists
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                self.output_window.append(f"({queue_position}) Warning: Could not delete zip file: {e}")
        
        # Process based on platform with queue item for status updates
        if platform_id == 'ps3':
            self._update_queue_item_status(queue_item, "PROCESSING", QColor(128, 0, 128))
            self.processing_manager.process_ps3_files(extracted_files, base_name, queue_position, settings, queue_item)
        elif platform_id == 'psn':
            self._update_queue_item_status(queue_item, "PROCESSING", QColor(128, 0, 128))
            self.processing_manager.process_psn_files(extracted_files, base_name, queue_position, settings, queue_item)
        elif platform_id == 'ps2':
            self._update_queue_item_status(queue_item, "PROCESSING", QColor(128, 0, 128))
            self.processing_manager.process_ps2_files(extracted_files, base_name, queue_position, settings, queue_item)
        elif platform_id == 'psx':
            self._update_queue_item_status(queue_item, "PROCESSING", QColor(128, 0, 128))
            self.processing_manager.process_psx_files(extracted_files, base_name, queue_position, settings, queue_item)
        elif platform_id == 'psp':
            self._update_queue_item_status(queue_item, "PROCESSING", QColor(128, 0, 128))
            self.processing_manager.process_psp_files(extracted_files, base_name, queue_position, settings, queue_item)
        else:
            # All other platforms (including Xbox 360 variants) use generic processing
            self._update_queue_item_status(queue_item, "PROCESSING", QColor(128, 0, 128))
            self.processing_manager.process_generic_files(extracted_files, base_name, queue_position, platform_id, settings, queue_item)
        
        # Mark as completed
        self._update_queue_item_status(queue_item, "COMPLETED", QColor(0, 128, 0))
    
    def _handle_current_download_removal(self, item, original_name):
        """Handle removal of currently downloading item."""
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtCore import Qt
        
        try:
            if os.path.exists(self.current_file_path):
                file_size = os.path.getsize(self.current_file_path)
                size_str = self._format_file_size(file_size)
            else:
                size_str = "unknown size (file not found)"
            
            status = "paused" if self.is_paused else "in progress"
            filename = self.queue_manager.get_filename_from_queue_item(original_name)
            
            # Show confirmation dialog
            msg_box = QMessageBox(self.parent())
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("Confirm Removal")
            msg_box.setText(f"'{filename}' has a {status} download ({size_str}).")
            msg_box.setInformativeText("Do you want to delete the incomplete download file?")
            
            delete_btn = msg_box.addButton("Delete File", QMessageBox.YesRole)
            keep_btn = msg_box.addButton("Keep File", QMessageBox.NoRole)
            cancel_btn = msg_box.addButton(QMessageBox.Cancel)
            
            msg_box.exec_()
            
            if msg_box.clickedButton() == cancel_btn:
                return False
            
            if msg_box.clickedButton() == delete_btn:
                if os.path.exists(self.current_file_path):
                    try:
                        os.remove(self.current_file_path)
                        self.output_window.append(f"({self.current_position}) Deleted incomplete download: {self.current_file_path}\n")
                    except Exception as e:
                        self.output_window.append(f"Error deleting file: {str(e)}\n")
            else:
                self.output_window.append(f"Kept incomplete download: {self.current_file_path}")
            
            # Reset current state if this was the current operation
            if self.current_item == original_name:
                if self.is_paused:
                    StateManager.clear_pause_state()
                    self.is_paused = False
                
                self.stop_processing()
                self._reset_processing_state()
            
            return True
            
        except Exception as e:
            self.output_window.append(f"Error handling download removal: {str(e)}\n")
            return True
    
    def _update_queue_item_status(self, item, status, color, suffix=None):
        """Update queue item with status and formatting."""
        from PyQt5.QtGui import QFont
        
        if suffix:
            text = f"{item.data(Qt.UserRole)} {suffix}"
        else:
            original_text = item.data(Qt.UserRole)
            clean_text = re.sub(r' \([A-Z]+\)$', '', original_text)
            text = f"{clean_text} ({status})"
        
        item.setText(text)
        
        # Apply bold font and color
        font = QFont()
        font.setBold(True)
        item.setFont(font)
        item.setForeground(QBrush(color))
    
    def _on_download_paused(self):
        """Handle download paused signal."""
        self.output_window.append(f"\n({self.current_position}) Download paused")
        self.operation_paused.emit()
    
    def _on_status_updated(self, status):
        """Handle status update from processing manager."""
        self.status_updated.emit(status)
        
        # Update queue item with specific status colors
        if self.current_queue_item:
            if status == "UNZIPPING":
                self._update_queue_item_status(self.current_queue_item, "UNZIPPING", QColor(255, 165, 0))
            elif status == "DECRYPTING":
                self._update_queue_item_status(self.current_queue_item, "DECRYPTING", QColor(255, 69, 0))
            elif status == "EXTRACTING":
                self._update_queue_item_status(self.current_queue_item, "EXTRACTING", QColor(50, 205, 50))
            elif status == "SPLITTING":
                self._update_queue_item_status(self.current_queue_item, "SPLITTING", QColor(255, 140, 0))
    
    def _on_processing_paused(self):
        """Handle processing paused signal."""
        self.output_window.append(f"({self.current_position}) Processing paused!")
        self.operation_paused.emit()
    
    def _reset_processing_state(self):
        """Reset processing state."""
        self.processed_items = 0
        self.total_items = 0
        self.current_item = None
        self.current_position = None
        self.current_file_path = None
        self.current_queue_item = None
        self.current_operation = None
        self.is_paused = False
        
        # Clear manager states
        self.download_manager.clear_current_operation()
        self.processing_manager.clear_current_operation()
        
        # Clear pause state when processing completes normally
        from core.state_manager import StateManager
        StateManager.clear_pause_state()
        
        self.operation_complete.emit()
    
    def filter_by_regions(self, items: List[str], selected_regions: List[str]) -> List[str]:
        """Filter items by multiple regions."""
        def get_regions(item: str) -> List[str]:
            # Extract all region and language information from filename
            regions = []
            # Match all parenthetical content
            matches = re.finditer(r'\((.*?)\)', item)
            
            for match in matches:
                content = match.group(1)
                # Split by commas and spaces to get individual parts
                parts = re.split(r'[,\s]+', content)
                
                # Check each part for region or language code
                for part in parts:
                    # Common region names
                    if part in ["USA", "Europe", "Japan", "Australia", "Canada", "Korea",
                              "Spain", "Germany", "France", "Italy"]:
                        regions.append(part)
                    # Language codes that might indicate region
                    elif part == "En":
                        if "USA" not in regions and "Europe" not in regions:
                            regions.append("USA")
                    elif part == "Fr":
                        if "France" not in regions:
                            regions.append("France")
                    elif part == "De":
                        if "Germany" not in regions:
                            regions.append("Germany")
                    elif part == "Es":
                        if "Spain" not in regions:
                            regions.append("Spain")
                    elif part == "It":
                        if "Italy" not in regions:
                            regions.append("Italy")
            
            return regions

        filtered_items = []
        for item in items:
            item_regions = get_regions(item)
            # If any of the selected regions match this item's regions, include it
            if any(region in item_regions for region in selected_regions):
                filtered_items.append(item)
                
        return filtered_items

    def _format_file_size(self, size_bytes):
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"