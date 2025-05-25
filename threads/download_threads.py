import os
import time
import random
import asyncio
import aiohttp
import requests
import json
import urllib.parse
from urllib.parse import unquote
from bs4 import BeautifulSoup
from PyQt5.QtCore import QThread, pyqtSignal, QEventLoop


class GetSoftwareListThread(QThread):
    signal = pyqtSignal('PyQt_PyObject')

    def __init__(self, url, json_file):
        QThread.__init__(self)
        self.url = url
        self.json_file = json_file

    def run(self):
        iso_list = []
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, 'r') as file:
                    iso_list = json.load(file)
            except Exception as e:
                print(f"Error loading {self.json_file}: {str(e)}")
        
        # Only fetch new list if empty or file doesn't exist
        if not iso_list:
            try:
                response = requests.get(self.url)
                soup = BeautifulSoup(response.text, 'html.parser')
                iso_list = [unquote(link.get('href')) for link in soup.find_all('a') if link.get('href').endswith('.zip')]
                
                # Save the file
                os.makedirs(os.path.dirname(self.json_file) or '.', exist_ok=True)
                with open(self.json_file, 'w') as file:
                    json.dump(iso_list, file)
            except Exception as e:
                print(f"Error fetching software list from {self.url}: {str(e)}")
                iso_list = ["Error loading list. Please check your connection."]

        self.signal.emit(iso_list)


class DownloadThread(QThread):
    progress_signal = pyqtSignal(int)
    speed_signal = pyqtSignal(str)
    eta_signal = pyqtSignal(str)
    download_complete_signal = pyqtSignal()
    download_paused_signal = pyqtSignal()

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

    async def download(self):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }

        for i in range(self.retries):
            try:
                if os.path.exists(self.filename):
                    self.existing_file_size = os.path.getsize(self.filename)
                    headers['Range'] = f'bytes={self.existing_file_size}-'

                async with aiohttp.ClientSession() as session:
                    async with session.get(self.url, headers=headers) as response:
                        if response.status not in (200, 206):
                            raise aiohttp.ClientPayloadError()

                        if 'content-range' in response.headers:
                            total_size = int(response.headers['content-range'].split('/')[-1])
                        else:
                            total_size = int(response.headers.get('content-length'))

                        with open(self.filename, 'ab') as file:
                            self.start_time = time.time()
                            while True:
                                # Check if we should stop
                                if not self.running:
                                    print("Download thread stopped")
                                    return
                                
                                # Check if we should pause
                                if self.paused:
                                    self.download_paused_signal.emit()
                                    await self.pause_event.wait()
                                    # Don't print "Download resumed" to avoid redundant messages
                                    # Reset start time to calculate correct speed
                                    self.start_time = time.time()
                                    self.current_session_downloaded = 0
                                
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                file.write(chunk)
                                self.existing_file_size += len(chunk)
                                self.current_session_downloaded += len(chunk)
                                self.progress_signal.emit(int((self.existing_file_size / total_size) * 100))

                                # Calculate speed and ETA
                                elapsed_time = time.time() - self.start_time
                                if elapsed_time > 0:
                                    speed = self.current_session_downloaded / elapsed_time
                                else:
                                    speed = 0
                                remaining_bytes = total_size - self.existing_file_size
                                eta = remaining_bytes / speed if speed > 0 else 0

                                # Convert speed to appropriate units
                                if speed > 1024**2:
                                    speed_str = f"{speed / (1024**2):.2f} MB/s"
                                else:
                                    speed_str = f"{speed / 1024:.2f} KB/s"

                                # Convert ETA to appropriate units
                                if eta >= 60:
                                    minutes, seconds = divmod(int(eta), 60)
                                    eta_str = f"{minutes} minutes {seconds} seconds remaining"
                                else:
                                    eta_str = f"{eta:.2f} seconds remaining"

                                # Emit the speed and ETA signals
                                self.speed_signal.emit(speed_str)
                                self.eta_signal.emit(eta_str)

                # If the download was successful, break the loop
                break
            except aiohttp.ClientPayloadError:
                print(f"Download interrupted. Retrying ({i+1}/{self.retries})...")
                await asyncio.sleep(2 ** i + random.random())  # Exponential backoff
                if i == self.retries - 1:  # If this was the last retry
                    raise  # Re-raise the exception
            except asyncio.TimeoutError:
                print(f"Download interrupted. Retrying ({i+1}/{self.retries})...")
                await asyncio.sleep(2 ** i + random.random())  # Exponential backoff
                if i == self.retries - 1:  # If this was the last retry
                    raise  # Re-raise the exception

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
