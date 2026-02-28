import os
import re

from core.utils import format_file_size
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
        self.is_shutting_down = False
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
        """Load the download queue and size information."""
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
            
            # Get file size from the stored JSON data
            file_size = self._get_file_size_from_cache(current_platform, item_text)
            
            # Create item data with size
            item_data = {
                'name': formatted_text,
                'size': file_size
            }
            
            if self.queue_manager.add_to_queue(item_data, queue_list_widget, platforms):
                added_count += 1
        
        if added_count > 0:
            self.save_queue(queue_list_widget)
        
        return added_count
        
    def _get_file_size_from_cache(self, platform_id, filename):
        """Get file size from cached JSON data."""
        try:
            import json
            import os
            
            json_file = os.path.join("config", f"{platform_id}_filelist.json")
            if os.path.exists(json_file):
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    
                    # Handle new format with file sizes
                    if data and isinstance(data[0], dict):
                        # Find the file in the data
                        for file_info in data:
                            if file_info.get('name') == filename:
                                return file_info.get('size', '')
                    # Handle old format - no sizes available
                    elif data and isinstance(data[0], str):
                        # Convert to new format with size fetching
                        return self._fetch_file_size_for_item(f"({platform_id.upper()}) {filename}")
        except Exception as e:
            print(f"Error getting file size from cache: {e}")
        
        return ""
    
    def _fetch_file_size_for_item(self, item_text):
        """Fetch file size for a queue item (fallback method)."""
        return self.queue_manager._fetch_file_size_for_item(item_text)
    
    def remove_from_queue(self, selected_items, queue_list_widget):
        """Remove selected items from the download queue."""
        items_to_remove = []
        current_items_handled = []
        
        for item in selected_items:
            # Get the original name from the item's data
            original_name = item.data(0, Qt.UserRole) if item.data(0, Qt.UserRole) else item.text(0)
            filename = self.queue_manager.get_filename_from_queue_item(original_name)
            
            # Check if this is a download in progress or paused
            is_current_download = (self.current_item == original_name)
            
            # Also check if there might be incomplete files in processing directory
            has_incomplete_file = False
            if not is_current_download:
                processing_dir = self.settings_manager.processing_dir
                if os.path.exists(processing_dir) and filename:
                    base_name = os.path.splitext(filename)[0]
                    for file in os.listdir(processing_dir):
                        if file.startswith(base_name) and file.endswith('.zip'):
                            file_path = os.path.join(processing_dir, file)
                            if os.path.exists(file_path):
                                has_incomplete_file = True
                                break
            
            if is_current_download:
                # Handle removal of current download/processing item with confirmation
                print(f"Handling removal of current item: {filename}")
                if self._handle_current_download_removal(item, original_name):
                    items_to_remove.append(item)
                    current_items_handled.append(filename)
                else:
                    print(f"User cancelled removal of: {filename}")
            elif has_incomplete_file:
                # Handle removal of item with incomplete download file
                print(f"Found incomplete file for: {filename}")
                # Temporarily set current_item for the removal handler
                old_current_item = self.current_item
                old_current_file_path = self.current_file_path
                
                self.current_item = original_name
                # Find the incomplete file path
                for file in os.listdir(processing_dir):
                    if file.startswith(base_name) and file.endswith('.zip'):
                        self.current_file_path = os.path.join(processing_dir, file)
                        break
                
                if self._handle_current_download_removal(item, original_name):
                    items_to_remove.append(item)
                    current_items_handled.append(filename)
                
                # Restore original state
                self.current_item = old_current_item
                self.current_file_path = old_current_file_path
            else:
                # Regular item without complications
                items_to_remove.append(item)
        
        # Remove all marked items
        removed_count = self.queue_manager.remove_from_queue(items_to_remove, queue_list_widget)
        
        if removed_count > 0:
            self.save_queue(queue_list_widget)
            
            # Provide feedback about what was removed
            regular_count = removed_count - len(current_items_handled)
            if regular_count > 0:
                print(f"Removed {regular_count} regular item(s) from queue")
        
        return removed_count
    
    def start_processing(self, queue_list_widget, settings):
        """Start processing the download queue."""
        print(f"Starting processing. Current item: {self.current_item}, is_paused: {self.is_paused}")
        
        # Don't start processing if shutting down
        if self.is_shutting_down:
            print("Cannot start processing - application is shutting down")
            return
        
        # Check if widget still exists
        try:
            if not queue_list_widget or not hasattr(queue_list_widget, 'topLevelItemCount'):
                print("Queue widget is invalid, aborting processing")
                return
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                print("Queue widget has been deleted, aborting processing")
                return
            else:
                raise
        
        self.is_paused = False
        
        # Check if resuming
        is_resuming_session = bool(self.current_item)
        
        if not is_resuming_session:
            # Fresh start
            self.processed_items = 0
            try:
                self.total_items = queue_list_widget.topLevelItemCount()
            except RuntimeError as e:
                if "wrapped C/C++ object" in str(e):
                    print("Queue widget deleted during processing start")
                    return
                else:
                    raise
            
            # Reset overwrite choices for new download session
            self.download_manager.reset_overwrite_choices()
            self.processing_manager.reset_overwrite_choices()
        else:
            print(f"Resuming session for item: {self.current_item}")
        
        # Process queue until empty
        try:
            skip_counter = 0
            max_skips = queue_list_widget.topLevelItemCount()  # Prevent infinite loops
            
            while queue_list_widget.topLevelItemCount() > 0 and not self.is_paused:
                # Get the first item in the queue
                current_queue_item = queue_list_widget.topLevelItem(0)
                item_original_name = current_queue_item.data(0, Qt.UserRole) if current_queue_item.data(0, Qt.UserRole) else current_queue_item.text(0)
                
                # For resuming session, skip items that don't match current item
                if is_resuming_session and self.current_item != item_original_name:
                    print(f"Skipping item {item_original_name}, not current item {self.current_item}")
                    skip_counter += 1
                    
                    # If we've skipped all items, the target item no longer exists
                    if skip_counter >= max_skips:
                        print(f"Target item {self.current_item} not found in queue after checking all items")
                        print("Clearing resume state and starting fresh processing")
                        self._reset_processing_state()
                        is_resuming_session = False
                        skip_counter = 0
                        continue
                    
                    # Remove the skipped item to avoid infinite loop
                    queue_list_widget.takeTopLevelItem(0)
                    self.save_queue(queue_list_widget)
                    continue
                
                # Reset skip counter when we find a processable item
                skip_counter = 0
                
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
                    queue_list_widget.takeTopLevelItem(0)
                    # Save queue immediately after removing completed item
                    self.save_queue(queue_list_widget)
                
                is_resuming_session = False
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                print("Queue widget deleted during processing, stopping gracefully")
                return
            else:
                raise
        
        # Reset state if completed
        if not self.is_paused:
            self._reset_processing_state()
    
    def resume_processing(self, queue_list_widget, settings):
        """Resume a previously paused processing operation."""
        # Don't resume if shutting down
        if self.is_shutting_down:
            print("Cannot resume processing - application is shutting down")
            return
        
        self.is_paused = False
        self.output_window.append(f"({self.current_position}) Resuming processing...\n")
        
        # Check if we have an active download thread that can be resumed
        has_active_download_thread = (
            self.download_manager.download_thread is not None and
            self.download_manager.download_thread.isRunning()
        )
        
        # Resume appropriate manager based on current operation
        if self.current_operation == 'download':
            print(f"Resuming download operation for {self.current_item}")
            self.status_updated.emit("DOWNLOADING")
            if self.current_queue_item:
                self._update_queue_item_status(self.current_queue_item, "DOWNLOADING", QColor(0, 128, 255))
            
            # Only try to resume if there's an active download thread
            if has_active_download_thread:
                print("Found active download thread, resuming it")
                self.download_manager.resume_download()
            else:
                print("No active download thread found, starting fresh processing")
                # Clear the current operation state and restart processing
                self.current_operation = None
                self.start_processing(queue_list_widget, settings)
        elif self.current_operation == 'processing':
            print(f"Resuming processing operation for {self.current_item}")
            # Will be updated by processing manager when it resumes specific operation
            self.processing_manager.resume_processing()
            # Don't call start_processing - let the existing processing continue
        else:
            print(f"No specific operation to resume, current_operation: {self.current_operation}")
            print("Starting fresh processing since no operation was in progress")
            # Only restart if no operation was in progress
            self.start_processing(queue_list_widget, settings)
    def pause_processing(self):
        """Pause the current processing operation."""
        self.is_paused = True
        self.status_updated.emit("PAUSED")
        
        # Update current queue item to show paused status
        if self.current_queue_item:
            self._update_queue_item_status(self.current_queue_item, "PAUSED", QColor(255, 215, 0), "(PAUSED)")
        
        self.download_manager.stop_download()
        self.processing_manager.stop_processing()
    
    def stop_processing(self, force_stop=False):
        """Stop the current processing operation."""
        if force_stop:
            # During shutdown, don't set paused state - just stop everything
            self.is_shutting_down = True
            self.download_manager.stop_download()
            self.processing_manager.stop_processing()
            self._reset_processing_state()
        else:
            # Normal pause operation - use pause_processing instead
            self.pause_processing()
    
    def check_for_paused_download(self, queue_list_widget):
        """
        Check if there is a paused download to resume.
        Prioritizes checking for physical partial files in the processing directory.
        Falls back to StateManager if no physical files indicate a paused state.
        """
        # Use the existing load_queue() method which loads from storage and returns the items
        loaded_queue_items_from_file = self.queue_manager.load_queue()

        # First, check for physical files indicating a resumable state
        processing_dir = self.settings_manager.processing_dir
        if os.path.exists(processing_dir):
            for idx, item_data_from_storage in enumerate(loaded_queue_items_from_file):
                item_name_from_storage = item_data_from_storage.get('name') if isinstance(item_data_from_storage, dict) else item_data_from_storage
                if not item_name_from_storage:
                    continue

                filename_in_queue = self.queue_manager.get_filename_from_queue_item(item_name_from_storage)
                base_name_in_queue = os.path.splitext(filename_in_queue)[0]

                for f_in_processing_dir in os.listdir(processing_dir):
                    # Check for .zip, .part, or .downloading suffixes
                    if f_in_processing_dir.startswith(base_name_in_queue) and \
                       (f_in_processing_dir.endswith('.zip') or \
                        f_in_processing_dir.endswith('.part') or \
                        f_in_processing_dir.endswith('.downloading')):
                        
                        print(f"Found physical partial file: {f_in_processing_dir} for queue item: {item_name_from_storage}")
                        
                        # A resumable file exists. Rebuild queue with this item as paused.
                        queue_list_widget.clear()
                        
                        # Add the identified paused item first
                        paused_item_widget = self.queue_manager.add_formatted_item_to_queue(item_data_from_storage, queue_list_widget)
                        self._update_queue_item_status(paused_item_widget, "PAUSED", QColor(255, 215, 0), "(PAUSED)")

                        # Add remaining items from the original loaded queue
                        for other_item_data in loaded_queue_items_from_file:
                            other_item_name = other_item_data.get('name') if isinstance(other_item_data, dict) else other_item_data
                            if other_item_name != item_name_from_storage:
                                self.queue_manager.add_formatted_item_to_queue(other_item_data, queue_list_widget)
                        
                        # Set AppController state for this paused item
                        self.current_item = item_name_from_storage
                        self.current_operation = 'download' # Assume it was a download
                        self.current_file_path = os.path.join(processing_dir, f_in_processing_dir)
                        self.current_queue_item = paused_item_widget
                        self.is_paused = True
                        # Try to determine position if possible, otherwise default
                        try:
                            self.current_position = f"{loaded_queue_items_from_file.index(item_data_from_storage) + 1}/{len(loaded_queue_items_from_file)}"
                            self.processed_items = loaded_queue_items_from_file.index(item_data_from_storage)
                            self.total_items = len(loaded_queue_items_from_file)
                        except ValueError:
                            self.current_position = f"1/{len(loaded_queue_items_from_file)}"
                            self.processed_items = 0
                            self.total_items = len(loaded_queue_items_from_file)


                        # Clear any old StateManager state as we are using physical file presence
                        StateManager.clear_pause_state()
                        self.save_queue(queue_list_widget) # Save the newly constructed queue
                        return True # Signal to UI to show "Resume"

        # Fallback: If no physical files found, check StateManager
        pause_state = StateManager.load_pause_state()
        if not pause_state:
            # No physical file and no saved state, so just load the queue normally if it wasn't already
            if queue_list_widget.topLevelItemCount() == 0: # Check if queue is empty
                 for item_data_s in loaded_queue_items_from_file:
                    self.queue_manager.add_formatted_item_to_queue(item_data_s, queue_list_widget)
            return False
            
        # Clear the current queue if we are restoring from StateManager
        queue_list_widget.clear()
        
        current_item_data = pause_state['current_item']
        paused_item = self.queue_manager.add_formatted_item_to_queue(current_item_data, queue_list_widget)
        self._update_queue_item_status(paused_item, "PAUSED", QColor(255, 215, 0), "(PAUSED)")
        
        if 'remaining_queue' in pause_state and isinstance(pause_state['remaining_queue'], list):
            for item_data in pause_state['remaining_queue']:
                item_text = item_data['name'] if isinstance(item_data, dict) else item_data
                current_text = current_item_data['name'] if isinstance(current_item_data, dict) else current_item_data
                if item_text != current_text:
                    self.queue_manager.add_formatted_item_to_queue(item_data, queue_list_widget)
        
        if isinstance(current_item_data, dict):
            self.current_item = current_item_data['name']
        else:
            self.current_item = current_item_data
        self.current_operation = pause_state['operation']
        self.current_position = pause_state['queue_position']
        self.current_file_path = pause_state['file_path']
        self.processed_items = pause_state['processed_items']
        self.total_items = pause_state['total_items']
        self.current_queue_item = paused_item
        self.is_paused = True
        
        self.save_queue(queue_list_widget)
        return True
    
    def save_pause_state(self, queue_list_widget, force_save=False):
        """Save the current pause state."""
        # Save if currently paused, or if forced (for shutdown when user had paused)
        if self.is_paused or force_save:
            # Get remaining queue items
            remaining_items = []
            for i in range(queue_list_widget.topLevelItemCount()):
                item = queue_list_widget.topLevelItem(i)
                item_data = {
                    'name': item.data(0, Qt.UserRole) if item.data(0, Qt.UserRole) else item.text(0),
                    'size': item.text(1)
                }
                remaining_items.append(item_data)
            
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
            self.status_updated.emit("DOWNLOADING")
            self._update_queue_item_status(queue_item, "DOWNLOADING", QColor(0, 128, 255))
            file_path = self.download_manager.download_item_by_platform(platform_id, filename, queue_position, queue_item)
            
            if self.is_paused:
                return
            
            # Skip processing if download failed (returns None)
            if file_path is None:
                self.output_window.append(f"({queue_position}) Download failed for {filename}, skipping processing")
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
        """Handle removal of currently downloading or paused item."""
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtCore import Qt
        
        try:
            # Determine if this is a paused item vs active download
            filename = self.queue_manager.get_filename_from_queue_item(original_name)
            
            # Get incomplete download file path and size info
            incomplete_file_path = self.current_file_path
            if not incomplete_file_path:
                # Try to construct the path from the processing directory
                incomplete_file_path = os.path.join(self.settings_manager.processing_dir, filename)
            
            file_exists = os.path.exists(incomplete_file_path)
            if file_exists:
                file_size = os.path.getsize(incomplete_file_path)
                size_str = self._format_file_size(file_size)
            else:
                # Check if there might be any related files in processing directory
                processing_files = []
                if os.path.exists(self.settings_manager.processing_dir):
                    base_name = os.path.splitext(filename)[0]
                    for file in os.listdir(self.settings_manager.processing_dir):
                        if file.startswith(base_name) and file.endswith('.zip'):
                            file_path = os.path.join(self.settings_manager.processing_dir, file)
                            if os.path.exists(file_path):
                                processing_files.append(file_path)
                
                if processing_files:
                    incomplete_file_path = processing_files[0]  # Use the first match
                    file_size = os.path.getsize(incomplete_file_path)
                    size_str = self._format_file_size(file_size)
                    file_exists = True
                else:
                    size_str = "unknown size (file not found)"
                    file_exists = False
            
            # Determine status based on current state
            if self.is_paused:
                status = "paused"
                dialog_title = "Remove Paused Download"
                status_msg = f"'{filename}' is currently paused"
            else:
                status = "in progress"
                dialog_title = "Remove Active Download"
                status_msg = f"'{filename}' is currently downloading"
            
            # Enhanced confirmation dialog
            msg_box = QMessageBox(self.parent())
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle(dialog_title)
            
            if file_exists:
                if file_exists:
                    msg_box.setText(f"{status_msg} and has an incomplete download file ({size_str}).")
                    msg_box.setInformativeText(
                        "Removing this item will stop the current operation and delete the incomplete download file.\n\n"
                        "Are you sure you want to continue?"
                    )
                    
                    delete_btn = msg_box.addButton("Delete File && Remove", QMessageBox.YesRole)
                    cancel_btn = msg_box.addButton(QMessageBox.Cancel)
                else:
                    msg_box.setText(f"{status_msg}.")
                    msg_box.setInformativeText(
                        "Removing this item will stop the current operation.\n\n"
                        "Are you sure you want to remove it from the queue?"
                    )
                    
                    remove_btn = msg_box.addButton("Remove from Queue", QMessageBox.YesRole)
                    cancel_btn = msg_box.addButton(QMessageBox.Cancel)
            msg_box.exec_()
            
            if msg_box.clickedButton() == cancel_btn:
                return False
            
            # Handle file deletion if requested and file exists
            if file_exists:
                clicked = msg_box.clickedButton()
                if clicked.text() == "Delete File && Remove":
                    try:
                        os.remove(incomplete_file_path)
                        self.output_window.append(f"({self.current_position or 'N/A'}) Deleted incomplete download: {incomplete_file_path}\n")
                        print(f"Successfully deleted incomplete download file: {incomplete_file_path}")
                    except Exception as e:
                        error_msg = f"Error deleting incomplete file: {str(e)}"
                        self.output_window.append(error_msg)
                        print(error_msg)
                        # Show error but still allow removal
                        QMessageBox.warning(
                            self.parent(),
                            "File Deletion Error",
                            f"Could not delete the incomplete download file:\n{str(e)}\n\nThe item will still be removed from the queue."
                        )
            
            # Stop current operations if this was the active item
            if self.current_item == original_name:
                # Clear pause state if paused
                if self.is_paused:
                    StateManager.clear_pause_state()
                    self.is_paused = False
                
                # Stop any active processing
                self.stop_processing()
                self._reset_processing_state()
                
                # Clear the current item to prevent resume confusion
                self.current_item = None
                self.current_operation = None
                self.current_file_path = None
                
            
            return True
            
        except Exception as e:
            error_msg = f"Error handling download removal: {str(e)}"
            self.output_window.append(error_msg)
            print(error_msg)
            # Still allow removal even if there was an error
            return True
    
    def _update_queue_item_status(self, item, status, color, suffix=None, size=None):
        """Update queue item with status and formatting."""
        from PyQt5.QtGui import QFont
        
        # Update the text in first column
        if suffix:
            text = f"{item.data(0, Qt.UserRole)} {suffix}"
        else:
            original_text = item.data(0, Qt.UserRole)
            clean_text = re.sub(r' \([A-Z]+\)$', '', original_text)
            text = f"{clean_text} ({status})"
        
        # Always preserve the original file size - don't update it with download progress
        # The size column should only show the final file size, not current download progress
        current_size = item.text(1)  # Keep existing size
        
        # Update first column only
        item.setText(0, text)
        # Don't update the size column (item.setText(1, current_size) removed)
        
        # Apply bold font and color to both columns
        font = QFont()
        font.setBold(True)
        item.setFont(0, font)
        item.setFont(1, font)
        item.setForeground(0, QBrush(color))
        item.setForeground(1, QBrush(color))
        
        # Store current state for pause/resume
        item.setData(0, Qt.UserRole + 1, {'status': status, 'size': current_size})
    
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
        
        # Only emit operation_complete signal if not shutting down
        if not self.is_shutting_down:
            self.operation_complete.emit()
        else:
            pass  # Skip operation_complete signal during shutdown
    
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
        return format_file_size(size_bytes)