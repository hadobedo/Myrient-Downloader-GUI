import os
import time
import random
import asyncio
import aiohttp
import requests
import json
import urllib.parse
import collections  # Add this import for deque
import re  # Add this import for regex operations
from urllib.parse import unquote
from bs4 import BeautifulSoup
from PyQt5.QtCore import QThread, pyqtSignal, QEventLoop


class GetSoftwareListThread(QThread):
    signal = pyqtSignal('PyQt_PyObject')

    def __init__(self, url, json_file, fetch_sizes=True):
        QThread.__init__(self)
        self.url = url
        # Ensure json file is in config directory
        self.json_file = os.path.join("config", json_file)
        self.fetch_sizes = fetch_sizes

    def run(self):
        file_data = []
        
        # Ensure config directory exists
        os.makedirs(os.path.dirname(self.json_file), exist_ok=True)
        
        # Check for file in new location
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, 'r') as file:
                    loaded_data = json.load(file)
                    
                    # Handle both old format (list of strings) and new format (list of dicts)
                    if loaded_data and isinstance(loaded_data[0], str):
                        # Convert old format to new format
                        print(f"Converting {self.json_file} to new format with file sizes...")
                        file_data = self._convert_old_format_to_new(loaded_data)
                        # Save converted data
                        with open(self.json_file, 'w') as file:
                            json.dump(file_data, file, indent=2)
                    else:
                        file_data = loaded_data
            except Exception as e:
                print(f"Error loading {self.json_file}: {str(e)}")
        else:
            # Check for old file in root directory
            old_file_path = os.path.basename(self.json_file)
            if os.path.exists(old_file_path):
                try:
                    with open(old_file_path, 'r') as file:
                        old_data = json.load(file)
                        # Convert old format and add sizes
                        file_data = self._convert_old_format_to_new(old_data)
                    
                    # Save to new location with new format
                    with open(self.json_file, 'w') as file:
                        json.dump(file_data, file, indent=2)
                    
                    # Remove old file after successful migration
                    os.remove(old_file_path)
                    print(f"Migrated file list from root to {self.json_file} with file sizes")
                except Exception as e:
                    print(f"Error migrating file list: {str(e)}")
        
        # Only fetch new list if empty or file doesn't exist
        # Only fetch new list if empty or file doesn't exist
        if not file_data:
            try:
                print(f"Fetching file list from {self.url}")
                response = requests.get(self.url)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                if self.fetch_sizes:
                    print("Parsing directory listing for filenames and sizes...")
                    file_data = self._parse_directory_listing_with_sizes(soup)
                else:
                    # Just extract filenames without sizes
                    file_links = [link for link in soup.find_all('a') if link.get('href') and link.get('href').endswith('.zip')]
                    file_data = []
                    for link in file_links:
                        filename = unquote(link.get('href'))
                        file_data.append({
                            'name': filename,
                            'size': ""
                        })
                
                print(f"Found {len(file_data)} files with sizes")
                
                # Save the file with new format
                with open(self.json_file, 'w') as file:
                    json.dump(file_data, file, indent=2)
                    
                print(f"Saved file list to {self.json_file}")
                
            except Exception as e:
                print(f"Error fetching software list from {self.url}: {str(e)}")
                file_data = [{"name": "Error loading list. Please check your connection.", "size": ""}]
        # Extract just the filenames for backward compatibility with GUI
        filenames = [item['name'] if isinstance(item, dict) else item for item in file_data]
        self.signal.emit(filenames)
        
    def _convert_old_format_to_new(self, old_list):
        """Convert old format (list of strings) to new format (list of dicts with sizes)."""
        print(f"Converting {len(old_list)} files to new format...")
        
        if self.fetch_sizes:
            # Re-fetch the directory listing to get sizes
            try:
                print("Re-fetching directory listing to get file sizes...")
                response = requests.get(self.url)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Parse the directory listing for sizes
                new_data_with_sizes = self._parse_directory_listing_with_sizes(soup)
                
                # Create a lookup map of filename to size
                size_map = {item['name']: item['size'] for item in new_data_with_sizes}
                
                # Convert old list using the size map
                new_data = []
                for filename in old_list:
                    if isinstance(filename, str) and filename.endswith('.zip'):
                        size = size_map.get(filename, "")
                        new_data.append({
                            'name': filename,
                            'size': size
                        })
                    else:
                        # Handle error messages or non-zip files
                        new_data.append({
                            'name': filename,
                            'size': ""
                        })
                        
                print(f"Successfully converted {len(new_data)} files with sizes from directory listing")
                return new_data
                
            except Exception as e:
                print(f"Failed to re-fetch directory listing: {e}")
                print("Falling back to conversion without sizes...")
        
        # Fallback: just convert format without sizes
        new_data = []
        for filename in old_list:
            if isinstance(filename, str) and filename.endswith('.zip'):
                new_data.append({
                    'name': filename,
                    'size': ""
                })
            else:
                # Handle error messages or non-zip files
                new_data.append({
                    'name': filename,
                    'size': ""
                })
        
        return new_data
        
    def _get_file_size(self, filename):
        """Get the size of a remote file."""
        try:
            # Import here to avoid circular imports
            from core.download_manager import DownloadManager
            import time
            
            # Try to get alternative domain first, then build download URL
            effective_base_url = DownloadManager.try_alternative_domains(self.url, filename)
            download_url = DownloadManager.build_download_url(effective_base_url, filename)
            
            # Add a small delay to avoid overwhelming the server
            time.sleep(0.1)
            
            # Get remote file size with multiple attempts
            for attempt in range(3):
                try:
                    size_bytes = DownloadManager.get_remote_file_size(download_url)
                    if size_bytes:
                        return self._format_file_size(size_bytes)
                except Exception as e:
                    if attempt < 2:  # Try up to 3 times
                        time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        print(f"Failed to get size for {filename} after {attempt + 1} attempts: {str(e)}")
                        break
                        
        except Exception as e:
            print(f"Error getting size for {filename}: {str(e)}")
        
        return ""
        
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
    
    def _parse_directory_listing_with_sizes(self, soup):
        """Parse directory listing HTML to extract filenames and sizes directly."""
        file_data = []
        
        try:
            # Look for table rows containing file information
            rows = soup.find_all('tr')
            
            for row in rows:
                # Find the link and size cells in this row
                link_cell = row.find('td', class_='link')
                size_cell = row.find('td', class_='size')
                
                if link_cell and size_cell:
                    # Extract filename from the link
                    link = link_cell.find('a')
                    if link and link.get('href') and link.get('href').endswith('.zip'):
                        filename = unquote(link.get('href'))
                        
                        # Extract size from size cell
                        size_text = size_cell.get_text(strip=True)
                        
                        # Convert size format (e.g., "54.4 KiB" -> "54.4 KB")
                        size_formatted = self._normalize_size_format(size_text)
                        
                        file_data.append({
                            'name': filename,
                            'size': size_formatted
                        })
            
            # If no files found with the above method, try fallback parsing
            if not file_data:
                print("No files found with table parsing, trying fallback method...")
                file_data = self._parse_directory_fallback(soup)
                
        except Exception as e:
            print(f"Error parsing directory listing: {e}")
            # Fallback to filename-only extraction
            file_links = soup.find_all('a', href=lambda x: x and x.endswith('.zip'))
            for link in file_links:
                filename = unquote(link.get('href'))
                file_data.append({
                    'name': filename,
                    'size': ""
                })
        
        return file_data
    
    def _parse_directory_fallback(self, soup):
        """Fallback parser for different directory listing formats."""
        file_data = []
        
        try:
            # Try to find any table rows
            rows = soup.find_all('tr')
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 2:  # Need at least filename and size
                    # Look for .zip files in any cell
                    for i, cell in enumerate(cells):
                        link = cell.find('a')
                        if link and link.get('href') and link.get('href').endswith('.zip'):
                            filename = unquote(link.get('href'))
                            
                            # Look for size in subsequent cells
                            size = ""
                            for j in range(i + 1, len(cells)):
                                cell_text = cells[j].get_text(strip=True)
                                if self._looks_like_file_size(cell_text):
                                    size = self._normalize_size_format(cell_text)
                                    break
                            
                            file_data.append({
                                'name': filename,
                                'size': size
                            })
                            break
                            
        except Exception as e:
            print(f"Fallback parsing failed: {e}")
        
        return file_data
    
    def _looks_like_file_size(self, text):
        """Check if text looks like a file size."""
        if not text or len(text) > 20:
            return False
        
        # Common size patterns
        size_patterns = [
            r'^\d+(\.\d+)?\s*(B|KB|MB|GB|KiB|MiB|GiB|TiB)$',  # Standard formats
            r'^\d+(\.\d+)?\s*[KMGT]i?B?$',                   # Abbreviated formats
            r'^\d{1,3}(,\d{3})+$',                           # Numbers with commas
            r'^\d+$'                                         # Plain numbers
        ]
        
        text_clean = text.strip().replace(',', '')
        
        for pattern in size_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _normalize_size_format(self, size_text):
        """Normalize size format to consistent display (convert KiB to KB, etc.)."""
        if not size_text:
            return ""
        
        size_text = size_text.strip()
        
        # Handle binary units (KiB, MiB, etc.) -> convert to decimal (KB, MB, etc.)
        binary_units = {
            'KiB': 1024,
            'MiB': 1024**2,
            'GiB': 1024**3,
            'TiB': 1024**4
        }
        
        # Extract number and unit
        match = re.match(r'(\d+(?:\.\d+)?)\s*([A-Za-z]+)?', size_text)
        if match:
            number = float(match.group(1))
            unit = match.group(2) if match.group(2) else 'B'
            
            # Convert binary to decimal units for consistency
            if unit in binary_units:
                bytes_val = number * binary_units[unit]
                return self._format_file_size(int(bytes_val))
            elif unit.upper() in ['B', 'KB', 'MB', 'GB', 'TB']:
                # Already in standard format, just normalize
                return f"{number:g} {unit.upper()}"
            else:
                # Try to guess - if it's a large number, probably bytes
                if number > 1000000:  # > 1MB in bytes
                    return self._format_file_size(int(number))
                else:
                    return f"{number:g} {unit}"
        
        return size_text

class DownloadThread(QThread):
    progress_signal = pyqtSignal(int)
    download_complete_signal = pyqtSignal()
    download_paused_signal = pyqtSignal()
    speed_signal = pyqtSignal(str)
    eta_signal = pyqtSignal(str)
    size_signal = pyqtSignal(str)  # Add size signal
    
    def __init__(self, url, filename, retries=50):
        QThread.__init__(self)
        self.url = url
        self.filename = filename
        self.retries = retries
        self.existing_file_size = 0
        self.start_time = None
        self.current_session_downloaded = 0
        self.running = True
        self.paused = False
        self.pause_event = asyncio.Event()
        self.pause_event.set()  # Not paused initially
        
        # For smooth speed calculation
        self.speed_window_size = 20  # Reduced window size to be more responsive
        self.download_chunks = collections.deque(maxlen=self.speed_window_size)
        self.last_update_time = 0
        self.last_chunk_time = 0
        self.last_emitted_speed = 0
        self.last_emitted_eta = 0
        
        # Dynamic chunking parameters
        self.initial_chunk_size = 262144  # Start with 256KB chunks
        self.min_chunk_size = 65536      # 64KB minimum
        self.max_chunk_size = 4194304    # 4MB maximum
        self.current_chunk_size = self.initial_chunk_size
        self.chunk_adjust_threshold = 5  # Number of chunks before adjustment
        self.chunk_counter = 0
        self.last_adjust_time = 0
        self.adjust_interval = 2.0       # Seconds between adjustments
        
        # Connection parameters
        self.tcp_nodelay = True          # Disable Nagle's algorithm for better responsiveness
        self.read_timeout = 30.0         # Read timeout in seconds

    async def download(self):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }

        for i in range(self.retries):
            try:
                if os.path.exists(self.filename):
                    self.existing_file_size = os.path.getsize(self.filename)
                    headers['Range'] = f'bytes={self.existing_file_size}-'

                # Configure client session with optimized parameters
                connector = aiohttp.TCPConnector(
                    force_close=False,          # Keep connections alive
                    ssl=False,                  # Disable SSL verification for speed
                    ttl_dns_cache=300,          # Cache DNS for 5 minutes
                    limit=0,                    # No connection limit
                    enable_cleanup_closed=True  # Clean up closed connections
                )
                
                timeout = aiohttp.ClientTimeout(
                    total=None,                 # No total timeout
                    connect=20.0,               # 20s connection timeout
                    sock_read=self.read_timeout # Configurable read timeout
                )
                
                async with aiohttp.ClientSession(
                    connector=connector, 
                    timeout=timeout,
                    headers=headers
                ) as session:
                    async with session.get(self.url) as response:
                        if response.status not in (200, 206):
                            raise aiohttp.ClientPayloadError()

                        # Get total file size
                        if 'content-range' in response.headers:
                            total_size = int(response.headers['content-range'].split('/')[-1])
                        else:
                            total_size = int(response.headers.get('content-length', 0)) + self.existing_file_size

                        with open(self.filename, 'ab') as file:
                            self.start_time = time.time()
                            self.last_update_time = time.time()
                            self.download_chunks.clear()  # Clear any old chunks
                            self.last_adjust_time = time.time()
                            self.chunk_counter = 0
                            
                            while True:
                                # Check if we should stop
                                if not self.running:
                                    print("Download thread stopped")
                                    return
                                
                                # Check if we should pause
                                if self.paused:
                                    self.download_paused_signal.emit()
                                    await self.pause_event.wait()
                                    # Reset timing information after pause
                                    self.start_time = time.time()
                                    self.last_update_time = time.time()
                                    self.download_chunks.clear()  # Clear old chunks after pause
                                    self.current_session_downloaded = 0
                                    self.last_adjust_time = time.time()
                                
                                # Read data with dynamic chunk size
                                chunk = await response.content.read(self.current_chunk_size)
                                if not chunk:
                                    break
                                    
                                # Write the chunk and update counters
                                file.write(chunk)
                                chunk_size = len(chunk)
                                self.existing_file_size += chunk_size
                                self.current_session_downloaded += chunk_size
                                
                                # Record this chunk for speed calculation
                                current_time = time.time()
                                self.download_chunks.append((current_time, chunk_size))
                                self.last_chunk_time = current_time
                                
                                # Update progress
                                progress = int((self.existing_file_size / total_size) * 100) if total_size > 0 else 0
                                self.progress_signal.emit(progress)

                                # Emit file size information
                                size_str = f"{self.format_size(self.existing_file_size)}/{self.format_size(total_size)}"
                                self.size_signal.emit(size_str)
                                
                                # Dynamically adjust chunk size based on download speed
                                self.chunk_counter += 1
                                if self.chunk_counter >= self.chunk_adjust_threshold and (current_time - self.last_adjust_time) >= self.adjust_interval:
                                    self.adjust_chunk_size()
                                    self.chunk_counter = 0
                                    self.last_adjust_time = current_time

                                # Calculate and emit speed and ETA more frequently (0.1s) for "live" feeling
                                if current_time - self.last_update_time >= 0.1:  # Update UI every 100ms
                                    speed = self.calculate_speed()
                                    remaining_bytes = total_size - self.existing_file_size
                                    eta = self.calculate_eta(speed, remaining_bytes)
                                    
                                    speed_str = self.format_speed(speed)
                                    eta_str = self.format_eta(eta)
                                    
                                    # Be more responsive for speed updates (reduce throttling)
                                    speed_changed_enough = abs(speed - self.last_emitted_speed) > self.last_emitted_speed * 0.02
                                    eta_changed_enough = abs(eta - self.last_emitted_eta) > 1.0
                                    
                                    # Always update speed, but throttle ETA updates
                                    self.speed_signal.emit(speed_str)
                                    if eta_changed_enough:
                                        self.eta_signal.emit(eta_str)
                                        self.last_emitted_eta = eta
                                    
                                    self.last_emitted_speed = speed
                                    self.last_update_time = current_time

                # If the download was successful, break the loop
                break
            except aiohttp.ClientPayloadError:
                print(f"Download interrupted. Retrying ({i+1}/{self.retries})...")
                await asyncio.sleep(2 ** i + random.random())  # Exponential backoff
                if i == self.retries - 1:  # If this was the last retry
                    raise  # Re-raise the exception
            except asyncio.TimeoutError:
                print(f"Download timed out. Retrying ({i+1}/{self.retries})...")
                # Reduce chunk size upon timeout to improve stability
                self.current_chunk_size = max(self.current_chunk_size // 2, self.min_chunk_size)
                await asyncio.sleep(2 ** i + random.random())  # Exponential backoff
                if i == self.retries - 1:  # If this was the last retry
                    raise  # Re-raise the exception
            except Exception as e:
                print(f"Download error: {str(e)}. Retrying ({i+1}/{self.retries})...")
                # Reduce chunk size on general errors too
                self.current_chunk_size = max(self.current_chunk_size // 2, self.min_chunk_size)
                await asyncio.sleep(2 ** i + random.random())  # Exponential backoff
                if i == self.retries - 1:
                    raise

    def adjust_chunk_size(self):
        """Dynamically adjust chunk size based on download speed"""
        if not self.download_chunks:
            return
        
        # Calculate recent download speed
        speed = self.calculate_speed()
        
        # Don't adjust if speed is too low (likely unstable connection)
        if speed < 50000:  # Less than 50 KB/s
            return
        
        # Calculate optimal chunk size - approximately the amount downloaded in 1 second
        optimal_chunk = min(max(int(speed), self.min_chunk_size), self.max_chunk_size)
        
        # Gradually adjust chunk size (don't change too drastically)
        if optimal_chunk > self.current_chunk_size:
            # Increase by 25% if optimal is higher
            self.current_chunk_size = min(int(self.current_chunk_size * 1.25), optimal_chunk)
        elif optimal_chunk < self.current_chunk_size * 0.75:
            # Decrease if optimal is significantly lower (25% lower)
            self.current_chunk_size = max(int(self.current_chunk_size * 0.75), optimal_chunk)
            
        # Ensure chunk size stays within bounds
        self.current_chunk_size = min(max(self.current_chunk_size, self.min_chunk_size), self.max_chunk_size)

    def calculate_speed(self):
        """Calculate current download speed in bytes per second using sliding window."""
        if not self.download_chunks:
            return 0
        
        # Get the oldest and newest chunk timestamps
        oldest_time = self.download_chunks[0][0]
        newest_time = self.last_chunk_time
        time_diff = newest_time - oldest_time
        
        # Calculate total downloaded in the window
        total_downloaded = sum(size for _, size in self.download_chunks)
        
        # Calculate speed, protecting against zero time_diff
        if time_diff > 0.001:  # At least 1 millisecond
            return total_downloaded / time_diff
        elif total_downloaded > 0:  # If we have downloads but time diff is tiny
            return total_downloaded  # Return bytes as bytes/s (avoids division by zero)
        else:
            return 0
    
    def calculate_eta(self, speed, remaining_bytes):
        """Calculate estimated time of arrival (ETA) in seconds."""
        if speed > 0:
            return remaining_bytes / speed
        return float('inf')  # infinity if speed is 0
    
    def format_speed(self, speed):
        """Format speed with appropriate units."""
        if speed < 0:
            speed = 0
            
        if speed == 0:
            return "0 B/s"
        elif speed < 1024:
            return f"{speed:.0f} B/s"
        elif speed < 1024**2:
            return f"{speed/1024:.1f} KB/s"
        elif speed < 1024**3:
            return f"{speed/(1024**2):.2f} MB/s"
        else:
            return f"{speed/(1024**3):.2f} GB/s"
    
    def format_eta(self, eta):
        """Format ETA in a human-readable format."""
        if eta == float('inf'):
            return "Calculating..."
            
        if eta < 0:
            eta = 0
            
        if eta < 1:
            return "Less than a second"
        elif eta < 60:
            return f"{eta:.0f} seconds remaining"
        elif eta < 3600:
            minutes, seconds = divmod(int(eta), 60)
            return f"{minutes} minutes {seconds} seconds remaining"
        else:
            hours, remainder = divmod(int(eta), 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours == 1:
                return f"1 hour {minutes} minutes remaining"
            else:
                return f"{hours} hours {minutes} minutes remaining"
    
    def format_file_size(self, size_bytes):
        """Format file size in a human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.2f} GB"
    
    def format_size(self, size_in_bytes):
        """Format file size with appropriate units."""
        if size_in_bytes < 1024:
            return f"{size_in_bytes} B"
        elif size_in_bytes < 1024 * 1024:
            return f"{size_in_bytes/1024:.1f} KB"
        elif size_in_bytes < 1024 * 1024 * 1024:
            return f"{size_in_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_in_bytes/(1024*1024*1024):.1f} GB"

    def run(self):
        asyncio.run(self.download())
        # Only emit completion if not paused
        if not self.paused:
            self.download_complete_signal.emit()

    def stop(self):
        self.running = False
        
    def pause(self):
        if not self.paused:
            self.paused = True
            self.pause_event.clear()
        
    def resume(self):
        if self.paused:
            self.paused = False
            self.pause_event.set()
