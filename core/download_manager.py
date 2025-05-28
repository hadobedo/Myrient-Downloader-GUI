import os
import requests
import urllib.parse
from PyQt5.QtCore import QObject, pyqtSignal, QEventLoop

from threads.download_threads import DownloadThread


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
        
    @staticmethod
    def check_file_exists(url, local_path):
        """Check if local file exists and matches the remote file size."""
        if os.path.exists(local_path):
            local_file_size = os.path.getsize(local_path)
            
            # Get the size of the remote file
            response = requests.head(url)
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
    def build_download_url(base_url, filename):
        """Build a download URL by encoding the filename."""
        encoded_filename = urllib.parse.quote(filename)
        # Ensure base_url does not end with a slash, as we add one.
        return f"{base_url.rstrip('/')}/{encoded_filename}"

    @staticmethod
    def try_alternative_domains(original_platform_url, filename_for_testing):
        """
        Tries to find a working download domain for the given platform URL and filename.
        Returns a base URL (without trailing slash) for DownloadManager.build_download_url.
        """
        parsed_original = urllib.parse.urlparse(original_platform_url)
        original_scheme = parsed_original.scheme
        original_host = parsed_original.hostname
        
        # path_from_original is already URL-encoded if original_platform_url was.
        # e.g., /files/No-Intro/Nintendo%20-%20Game%20Boy%20Color/
        path_from_original = parsed_original.path
        
        # base_path_for_candidates will be like /files/No-Intro/Nintendo%20-%20Game%20Boy%20Color
        base_path_for_candidates = path_from_original.rstrip('/')

        # This is the base URL structure derived from the original_platform_url.
        # e.g., "https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Game%20Boy%20Color"
        default_candidate_base = f"{original_scheme}://{original_host}{base_path_for_candidates}"

        alternative_hosts = []
        for i in range(10):
            alternative_hosts.append(f"download{i}.mtcontent.rs")
        for i in range(10):
            alternative_hosts.append(f"cache{i}.mtcontent.rs")

        # 1. Test the original URL's structure first.
        #    This handles cases like PS3 using dlX.myrient.erista.me which might be direct.
        if original_host:
            test_url_original = DownloadManager.build_download_url(default_candidate_base, filename_for_testing)
            try:
                response = requests.head(test_url_original, timeout=2, allow_redirects=True)
                if response.status_code == 200:
                    return default_candidate_base
            except requests.exceptions.RequestException:
                pass # Continue to mtcontent.rs alternatives

        # 2. Try alternative mtcontent.rs domains.
        for alt_host in alternative_hosts:
            # candidate_dl_base will be like "https://downloadX.mtcontent.rs/files/No-Intro/Nintendo%20-%20Game%20Boy%20Color"
            candidate_dl_base = f"https://{alt_host}{base_path_for_candidates}"
            test_url_alt = DownloadManager.build_download_url(candidate_dl_base, filename_for_testing)
            try:
                response = requests.head(test_url_alt, timeout=1.5, allow_redirects=True)
                if response.status_code == 200:
                    return candidate_dl_base # Return the base part, e.g., https://downloadX.mtcontent.rs/path
            except requests.exceptions.RequestException:
                continue
        
        # 3. Fallback to the original URL structure if no alternatives worked.
        return default_candidate_base

    @staticmethod
    def get_base_name(filename):
        """Get the base name of a file (without extension)."""
        return os.path.splitext(filename)[0]
        
    def download_item_by_platform(self, platform_id, item_text, queue_position):
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
        # Download the file
        return self.download_file(item_text, queue_position, url)
    
    def download_file(self, selected_iso_filename, queue_position, base_download_url_for_platform):
        """
        Helper function to download a file.
        `selected_iso_filename` is the name of the .zip file (e.g., "Game Name (Region).zip").
        `base_download_url_for_platform` is the base URL for the platform (e.g., "http://example.com/ps3/").
        Returns the path to the downloaded .zip file, or path to existing final file if skipping.
        """
        self.current_operation = 'download'
        
        effective_base_url = DownloadManager.try_alternative_domains(base_download_url_for_platform, selected_iso_filename)
        download_url = DownloadManager.build_download_url(effective_base_url, selected_iso_filename)
        
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

        if platform_id == 'ps3':
            # PS3 can result in an ISO or an extracted folder. Check both.
            final_iso_path = os.path.join(final_output_dir, potential_final_filename_iso)
            final_extracted_folder_path = os.path.join(final_output_dir, potential_final_dirname_extracted_ps3)
            if os.path.exists(final_iso_path):
                self.output_window.append(f"({queue_position}) Final output file {final_iso_path} already exists. Skipping.")
                return final_iso_path
            if os.path.exists(final_extracted_folder_path) and os.path.isdir(final_extracted_folder_path):
                self.output_window.append(f"({queue_position}) Final output folder {final_extracted_folder_path} already exists. Skipping.")
                return final_extracted_folder_path
        elif platform_id == 'psn':
            # PSN games are primarily PKGs. RAPs are separate.
            final_pkg_path = os.path.join(final_output_dir, potential_final_filename_pkg)
            if os.path.exists(final_pkg_path):
                self.output_window.append(f"({queue_position}) Final output file {final_pkg_path} already exists. Skipping.")
                return final_pkg_path
        else:
            # Generic handler for other platforms using the new directory management
            final_iso_path = os.path.join(final_output_dir, potential_final_filename_iso)
            if os.path.exists(final_iso_path):
                 self.output_window.append(f"({queue_position}) Final output file {final_iso_path} already exists. Skipping.")
                 return final_iso_path
            # Add checks for other common extensions if necessary, e.g., .bin for PSX/PS2
            if platform_id in ['psx', 'ps2']:
                potential_final_filename_bin = base_name_no_ext + '.bin'
                final_bin_path = os.path.join(final_output_dir, potential_final_filename_bin)
                if os.path.exists(final_bin_path):
                    self.output_window.append(f"({queue_position}) Final output file {final_bin_path} already exists. Skipping.")
                    return final_bin_path

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
        
        self.download_thread = DownloadThread(download_url, zip_file_path) # Downloads to processing_dir
        self.download_thread.progress_signal.connect(self.progress_updated.emit)
        self.download_thread.speed_signal.connect(self.speed_updated.emit)
        self.download_thread.eta_signal.connect(self.eta_updated.emit)
        self.download_thread.size_signal.connect(self.size_updated.emit)
        self.download_thread.download_paused_signal.connect(self.download_paused.emit)
        
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
        """Pause the current download."""
        self.is_paused = True
        if self.download_thread and self.current_operation == 'download':
            self.download_thread.pause()
    
    def resume_download(self):
        """Resume a previously paused download."""
        self.is_paused = False
        if self.download_thread and self.current_operation == 'download':
            self.download_thread.resume()
    
    def stop_download(self):
        """Stop the current download."""
        if self.download_thread:
            self.download_thread.stop()
    
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