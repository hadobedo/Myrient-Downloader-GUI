import os
import requests
import urllib.parse
from PyQt5.QtCore import QObject, pyqtSignal, QEventLoop

from threads.download_threads import DownloadThread
from gui.overwrite_dialog import OverwriteManager
from core.utils import format_file_size

# Shared headers for all Myrient HTTP requests to avoid triggering abuse detection.
# Myrient throttles bare python-requests User-Agent to 10 KB/s.
MYRIENT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Referer': 'https://myrient.erista.me/',
}


class DownloadManager(QObject):
    """Manages all download operations separate from GUI."""
    
    # Signals for GUI updates
    progress_updated = pyqtSignal(int)
    speed_updated = pyqtSignal(str)
    eta_updated = pyqtSignal(str)
    size_updated = pyqtSignal(str)
    download_complete = pyqtSignal()
    download_paused = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, settings_manager, config_manager, output_window, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.config_manager = config_manager
        self.output_window = output_window
        self.download_thread = None
        self.current_operation = None
        self.current_file_path = None
        self.is_paused = False
        self.overwrite_manager = OverwriteManager()
        
    @staticmethod
    def check_file_exists(url, local_path):
        """Check if local file exists and matches the remote file size."""
        if os.path.exists(local_path):
            local_file_size = os.path.getsize(local_path)
            
            # Get the size of the remote file
            response = requests.head(url, headers=MYRIENT_HEADERS, timeout=10, allow_redirects=True)
            if 'content-length' in response.headers:
                remote_file_size = int(response.headers['content-length'])
                
                # If the local file is smaller, attempt to resume the download
                if local_file_size < remote_file_size:
                    print(f"Local file is smaller than the remote file. Attempting to resume download...")
                    return False
                # If the local file is the same size as the remote file, skip the download
                elif local_file_size == remote_file_size:
                    # File already downloaded completely, skip
                    return True
            else:
                print("Could not get the size of the remote file.")
                return False
        return False

    @staticmethod
    def get_remote_file_size(url):
        """Get the size of a remote file without downloading it."""
        try:
            # Try HEAD request first (faster)
            response = requests.head(url, timeout=5, headers=MYRIENT_HEADERS, allow_redirects=True)
            if response.status_code == 200 and 'content-length' in response.headers:
                return int(response.headers['content-length'])
            
            # If HEAD fails, try GET with range to get just the headers
            headers_with_range = {**MYRIENT_HEADERS, 'Range': 'bytes=0-0'}
            response = requests.get(url, timeout=5, headers=headers_with_range, allow_redirects=True)
            if response.status_code in [200, 206, 416] and 'content-range' in response.headers:
                # Parse content-range header: "bytes 0-0/12345"
                content_range = response.headers['content-range']
                if '/' in content_range:
                    total_size = content_range.split('/')[-1]
                    if total_size.isdigit():
                        return int(total_size)
            elif response.status_code in [200, 206] and 'content-length' in response.headers:
                return int(response.headers['content-length'])
                
        except Exception as e:
            # Silently fail - too many files to print all errors
            pass
        return None

    @staticmethod
    def build_download_url(base_url, filename):
        """Build a download URL by encoding the filename."""
        # Only encode if not already encoded
        if '%' not in filename:
            encoded_filename = urllib.parse.quote(filename)
        else:
            encoded_filename = filename
        # Ensure base_url does not end with a slash, as we add one.
        return f"{base_url.rstrip('/')}/{encoded_filename}"

    @staticmethod
    def get_base_name(filename):
        """Get the base name of a file (without extension)."""
        return os.path.splitext(filename)[0]
        
    def download_item_by_platform(self, platform_id, item_text, queue_position, queue_item):
        """Download an item based on its platform and return the downloaded file path."""
        # Extract actual filename if this is a formatted queue item
        if '<b>' in item_text:
            item_text = self._get_filename_from_queue_item(item_text)
        
        # Get URL for platform
        url = self.config_manager.get_url(platform_id, 'url')
        if not url:
            self.error_occurred.emit(f"ERROR: Missing URL configuration for {platform_id}")
            return None
        
        # Download the file
        # Download the file with queue item for size updates
        self.current_queue_item = queue_item  # Store current queue item
        return self.download_file(item_text, queue_position, url, queue_item)
    
    def download_file(self, selected_iso_filename, queue_position, base_download_url_for_platform, queue_item=None):
        """
        Helper function to download a file.
        `selected_iso_filename` is the name of the .zip file (e.g., "Game Name (Region).zip").
        `base_download_url_for_platform` is the base URL for the platform (e.g., "http://example.com/ps3/").
        Returns the path to the downloaded .zip file, or path to existing final file if skipping.
        """
        self.current_operation = 'download'
        
        download_url = DownloadManager.build_download_url(base_download_url_for_platform, selected_iso_filename)
        
        base_name_no_ext = DownloadManager.get_base_name(selected_iso_filename) # e.g., "Game Name (Region)"

        # Determine platform_id from the base_download_url_for_platform
        # We need to extract the platform from the URL to know which output directory to check
        platform_id = None
        for pid, config in self.config_manager.get_platforms().items():
            if config['url'] in base_download_url_for_platform:
                platform_id = pid
                break
        
        if not platform_id:
            # Fallback: try to determine from URL patterns
            url_lower = base_download_url_for_platform.lower()
            if '/ps3/' in url_lower or 'ps3' in url_lower:
                platform_id = 'ps3'
            elif '/psn/' in url_lower or 'psn' in url_lower:
                platform_id = 'psn'
            elif '/ps2/' in url_lower:
                platform_id = 'ps2'
            elif '/psx/' in url_lower:
                platform_id = 'psx'
            elif '/psp/' in url_lower:
                platform_id = 'psp'
            elif 'xbox%20360' in url_lower or 'xbox 360' in url_lower or 'xbox360' in url_lower:
                # Return the specific Xbox 360 platform variant if we can determine it
                if 'digital' in url_lower:
                    platform_id = 'xbox360digital'
                elif 'title%20update' in url_lower or 'title update' in url_lower:
                    platform_id = 'xbox360tu'
                else:
                    platform_id = 'xbox360'

        # Use the new directory management system to get the output directory
        final_output_dir = self.settings_manager.get_platform_directory(platform_id)
        
        # Define potential final filenames
        potential_final_filename_iso = base_name_no_ext + '.iso'
        potential_final_filename_pkg = base_name_no_ext + '.pkg'
        potential_final_dirname_extracted_ps3 = base_name_no_ext

        # Check for existing files and handle conflicts
        existing_files = []
        
        if platform_id == 'ps3':
            # PS3 can result in an ISO or an extracted folder. Check both.
            final_iso_path = os.path.join(final_output_dir, potential_final_filename_iso)
            final_extracted_folder_path = os.path.join(final_output_dir, potential_final_dirname_extracted_ps3)
            
            if os.path.exists(final_iso_path):
                existing_files.append({
                    'path': final_iso_path,
                    'existing_size': os.path.getsize(final_iso_path),
                    'new_size': 0  # Unknown until download
                })
            if os.path.exists(final_extracted_folder_path) and os.path.isdir(final_extracted_folder_path):
                existing_files.append({
                    'path': final_extracted_folder_path,
                    'existing_size': self._get_directory_size(final_extracted_folder_path),
                    'new_size': 0  # Unknown until processing
                })
                
        elif platform_id == 'psn':
            # PSN games are primarily PKGs. RAPs are separate.
            final_pkg_path = os.path.join(final_output_dir, potential_final_filename_pkg)
            if os.path.exists(final_pkg_path):
                existing_files.append({
                    'path': final_pkg_path,
                    'existing_size': os.path.getsize(final_pkg_path),
                    'new_size': 0  # Unknown until download
                })
        else:
            # Generic handler for other platforms using the new directory management
            final_iso_path = os.path.join(final_output_dir, potential_final_filename_iso)
            if os.path.exists(final_iso_path):
                existing_files.append({
                    'path': final_iso_path,
                    'existing_size': os.path.getsize(final_iso_path),
                    'new_size': 0  # Unknown until download
                })
            
            # Add checks for other common extensions if necessary, e.g., .bin for PSX/PS2
            if platform_id in ['psx', 'ps2']:
                potential_final_filename_bin = base_name_no_ext + '.bin'
                final_bin_path = os.path.join(final_output_dir, potential_final_filename_bin)
                if os.path.exists(final_bin_path):
                    existing_files.append({
                        'path': final_bin_path,
                        'existing_size': os.path.getsize(final_bin_path),
                        'new_size': 0  # Unknown until download
                    })
        
        # Handle conflicts if any exist
        if existing_files:
            from gui.overwrite_dialog import OverwriteDialog
            choice, apply_to_all = self.overwrite_manager.handle_conflict(
                existing_files, "downloading", self.parent()
            )
            
            if choice == OverwriteDialog.CANCEL:
                self.output_window.append(f"({queue_position}) Download cancelled due to existing files.")
                return None
            elif choice == OverwriteDialog.SKIP:
                self.output_window.append(f"({queue_position}) Skipping download - files already exist.")
                # Return the first existing file as the "downloaded" result
                return existing_files[0]['path']
            # If OVERWRITE or RENAME, continue with download (files will be handled during processing)

        # If no existing final file was found, proceed to download the .zip into processing_dir
        zip_file_path = os.path.join(self.settings_manager.processing_dir, selected_iso_filename)

        # If the .zip file exists in processing_dir, compare its size to that of the remote URL
        if DownloadManager.check_file_exists(download_url, zip_file_path): # check_file_exists compares local and remote size
            self.output_window.append(f"({queue_position}) {selected_iso_filename} already exists in processing directory and matches remote size. Skipping download step.")
            return zip_file_path # Return path to existing zip for processing

        # Show download start and URL messages if not resuming
        if not hasattr(self, 'is_resuming') or not self.is_resuming: # 'is_resuming' seems to be a class member, ensure it's handled
            self.output_window.append(f"({queue_position}) Download started for {base_name_no_ext}")
            self.output_window.append(f"URL: {download_url}\n")
            
        self.progress_updated.emit(0)
        self.size_updated.emit("")
        
        # Get remote file size for initial display
        try:
            response = requests.head(download_url, headers=MYRIENT_HEADERS, timeout=10, allow_redirects=True)
            if 'content-length' in response.headers:
                remote_size = int(response.headers['content-length'])
                if queue_item:
                    queue_item.setText(1, self._format_file_size(remote_size))
        except Exception:
            pass  # Ignore errors in size prefetch
            
        self.download_thread = DownloadThread(download_url, zip_file_path) # Downloads to processing_dir
        self.download_thread.progress_signal.connect(self.progress_updated.emit)
        self.download_thread.speed_signal.connect(self.speed_updated.emit)
        self.download_thread.eta_signal.connect(self.eta_updated.emit)
        self.download_thread.size_signal.connect(self._handle_size_update)
        self.download_thread.download_paused_signal.connect(self.download_paused.emit)

        # Track whether the download succeeded
        self._download_success = True
        self.download_thread.download_error_signal.connect(self._handle_download_error)
        
        # Store file path for pause/resume
        self.current_file_path = zip_file_path
        
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

        # Return None on failure to prevent processing of incomplete files
        if not self._download_success:
            return None
            
        return zip_file_path
    
    def _handle_download_error(self, error_message):
        """Handle download error: mark failure and propagate to caller."""
        self._download_success = False
        self.error_occurred.emit(f"Download failed: {error_message}")
    
    def pause_download(self):
        """Pause the current download."""
        print("Download manager pausing...")
        self.is_paused = True
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.pause()
            print("Download thread pause requested")
        else:
            print("No active download thread to pause")
    
    def resume_download(self):
        """Resume a previously paused download."""
        print("Download manager resuming...")
        self.is_paused = False
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.resume()
            print("Download thread resume requested")
        else:
            print("No active download thread to resume")
            # This is expected when resuming from a detected partial file
            # The app controller should handle restarting the download process
    
    def stop_download(self):
        """Stop the current download."""
        if self.download_thread:
            self.download_thread.stop()
            if self.download_thread.isRunning():
                self.download_thread.wait(5000)  # Wait up to 5 seconds
            self.download_thread = None
            self.current_queue_item = None  # Clear queue item reference
        else:
            pass  # No download thread to stop
        # Don't set is_paused here - let the app controller handle state
    
    def _get_filename_from_queue_item(self, item_text):
        """Extract filename from a formatted queue item."""
        import re
        # Handle HTML-formatted items
        if '<' in item_text and '>' in item_text:
            # Strip HTML tags first
            plain_text = re.sub(r'<[^>]+>', '', item_text)
            item_text = plain_text
            
        # Remove platform prefix pattern (PLATFORM) from the text
        text_without_platform = re.sub(r'^\([^)]+\)\s*', '', item_text)
        
        # Remove (DOWNLOADING) suffix if present
        return re.sub(r'\s*\(DOWNLOADING\)\s*$', '', text_without_platform)
    
    def clear_current_operation(self):
        """Clear current operation state."""
        self.current_operation = None
        self.current_file_path = None
        self.current_queue_item = None  # Clear queue item reference
        self.is_paused = False
        
        # Clean up download thread if it exists
        if self.download_thread:
            if self.download_thread.isRunning():
                self.download_thread.stop()
                self.download_thread.wait(3000)  # Wait up to 3 seconds
            self.download_thread = None
    
    def reset_overwrite_choices(self):
        """Reset overwrite manager choices for new download session."""
        self.overwrite_manager.reset()
    
    def _get_directory_size(self, directory_path):
        """Calculate the total size of a directory and its contents."""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(directory_path):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(file_path)
                    except (OSError, IOError):
                        pass  # Skip files that can't be accessed
        except (OSError, IOError):
            pass  # Skip directories that can't be accessed
        return total_size
        
    def _handle_size_update(self, size_str):
        """Handle size updates from download thread and update queue item."""
        # Update the general size signal
        self.size_updated.emit(size_str)
        
        # Update queue item if available
        if hasattr(self, 'current_queue_item') and self.current_queue_item:
            # Extract current size from format "X.XX MB/Y.YY MB"
            current_size = size_str.split('/')[0].strip()
            self.current_queue_item.setText(1, current_size)

    def _format_file_size(self, size_bytes):
        """Format file size for display."""
        return format_file_size(size_bytes)