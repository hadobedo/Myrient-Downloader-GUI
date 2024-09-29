import os
import subprocess
import zipfile
import sys
import platform
import shutil
import signal
import glob
import multiprocessing
import urllib
import urllib.request
import urllib.parse
import json
import difflib
import time
import pickle
import random
import threading
import asyncio
from pathlib import Path
from urllib.parse import unquote
import requests
import aiohttp
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import QApplication, QGridLayout, QGroupBox, QWidget, QVBoxLayout, \
    QPushButton, QComboBox, QLineEdit, QListWidget, QLabel, QCheckBox, QTextEdit, \
    QFileDialog, QDialog, QHBoxLayout, QAbstractItemView, QProgressBar, \
    QTabWidget
from PyQt5.QtCore import QThread, pyqtSignal, QSettings, QEventLoop
from PyQt5.QtGui import QTextCursor

class GetSoftwareListThread(QThread):
    signal = pyqtSignal('PyQt_PyObject')

    def __init__(self, url, json_file):
        QThread.__init__(self)
        self.url = url
        self.json_file = json_file

    def run(self):
        iso_list = []
        if os.path.exists(self.json_file):
            with open(self.json_file, 'r') as file:
                iso_list = json.load(file)
        if not iso_list:
            response = requests.get(self.url)
            soup = BeautifulSoup(response.text, 'html.parser')
            iso_list = [unquote(link.get('href')) for link in soup.find_all('a') if link.get('href').endswith('.zip')]
            with open(self.json_file, 'w') as file:
                json.dump(iso_list, file)

        self.signal.emit(iso_list)

class SplitPkgThread(QThread):
    progress = pyqtSignal(str)
    status = pyqtSignal(bool)

    def __init__(self, file_path):
        QThread.__init__(self)
        self.file_path = file_path

    def run(self):
        file_size = os.path.getsize(self.file_path)
        if file_size < 4294967295:
            self.status.emit(False)
            return
        else:
            chunk_size = 4294967295
            num_parts = -(-file_size // chunk_size)
            with open(self.file_path, 'rb') as f:
                i = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    with open(f"{Path(self.file_path).stem}.pkg.666{str(i).zfill(2)}", 'wb') as chunk_file:
                        chunk_file.write(chunk)
                    print(f"Splitting {self.file_path}: part {i+1}/{num_parts} complete")
                    i += 1
            os.remove(self.file_path)
            self.status.emit(True)

class SplitIsoThread(QThread):
    progress = pyqtSignal(str)
    status = pyqtSignal(bool)

    def __init__(self, file_path):
        QThread.__init__(self)
        self.file_path = file_path

    def run(self):
        file_size = os.path.getsize(self.file_path)
        if file_size < 4294967295:
            self.status.emit(False)
            return
        else:
            chunk_size = 4294967295
            num_parts = -(-file_size // chunk_size)
            with open(self.file_path, 'rb') as f:
                i = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    with open(f"{os.path.splitext(self.file_path)[0]}.iso.{str(i)}", 'wb') as chunk_file:
                        chunk_file.write(chunk)
                    print(f"Splitting {self.file_path}: part {i+1}/{num_parts} complete")  
                    i += 1
            self.status.emit(True)


class OutputWindow(QTextEdit):
    def __init__(self, *args, **kwargs):
        super(OutputWindow, self).__init__(*args, **kwargs)
        # sys.stdout = self
        self.setReadOnly(True)

    def write(self, text):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.setTextCursor(cursor)
        QApplication.processEvents()

    def flush(self):
        pass

# Function to run a command and check its success
class CommandRunner(QThread):
    def __init__(self, command):
        super().__init__()
        self.command = command

    def run(self):
        process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, bufsize=1, universal_newlines=True)
        
        # If on Windows, send a newline character to ps3dec's standard input
        if platform.system() == 'Windows':
            process.stdin.write('\n')
            process.stdin.flush()
        
        def reader_thread(process):
            for line in iter(process.stdout.readline, ''):
                print(line.rstrip('\n')) 
                QApplication.processEvents()

        thread = threading.Thread(target=reader_thread, args=(process,))
        thread.start()
        process.wait()
        thread.join()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, self.command)

class UnzipRunner(QThread):
    progress_signal = pyqtSignal(int)

    def __init__(self, zip_path, output_path):
        super().__init__()
        self.zip_path = zip_path
        self.output_path = output_path
        self.extracted_files = []
        self.running = True  # Add a flag to indicate whether the runner is running

    def run(self):
        if not self.zip_path.lower().endswith('.zip'):
            print(f"File {self.zip_path} is not a .zip file. Skipping unzip.")
            return

        with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
            total_size = sum([info.file_size for info in zip_ref.infolist()])
            extracted_size = 0

            for info in zip_ref.infolist():
                with zip_ref.open(info, 'r') as file_in:
                    file_out_path = os.path.join(self.output_path, os.path.basename(info.filename)) 
                    with open(file_out_path, 'wb') as file_out:
                        while True:
                            chunk = file_in.read(8192)
                            if not chunk or not self.running:  # Stop reading if the runner is not running
                                break
                            file_out.write(chunk)
                            extracted_size += len(chunk)
                            self.progress_signal.emit(int((extracted_size / total_size) * 100))
                            QApplication.processEvents()
                    self.extracted_files.append(file_out_path)  # Store the path of the extracted file

    def stop(self):
        self.running = False  # Add a method to stop the runner

class DownloadThread(QThread):
    progress_signal = pyqtSignal(int)
    speed_signal = pyqtSignal(str)
    eta_signal = pyqtSignal(str)
    download_complete_signal = pyqtSignal()

    def __init__(self, url, filename, retries=50):  # Increase retries to 50
        QThread.__init__(self)
        self.url = url
        self.filename = filename
        self.retries = retries
        self.existing_file_size = 0
        self.start_time = None
        self.current_session_downloaded = 0
        self.running = True  # Add a flag to indicate whether the thread is running

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
                        if response.status not in (200, 206):  # 200 = OK, 206 = Partial Content
                            raise aiohttp.ClientPayloadError()

                        if 'content-range' in response.headers:
                            total_size = int(response.headers['content-range'].split('/')[-1])
                        else:
                            total_size = int(response.headers.get('content-length'))

                        with open(self.filename, 'ab') as file:
                            self.start_time = time.time()
                            while True:
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                file.write(chunk)
                                self.existing_file_size += len(chunk)
                                self.current_session_downloaded += len(chunk)  # Update the current_session_downloaded
                                self.progress_signal.emit(int((self.existing_file_size / total_size) * 100))  # Emit progress signal

                                # Calculate speed and ETA
                                elapsed_time = time.time() - self.start_time
                                if elapsed_time > 0:
                                    speed = self.current_session_downloaded / elapsed_time  # Calculate speed based on current session download
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
        self.download_complete_signal.emit()

    def stop(self):
        self.running = False  # Add a method to stop the thread

class GUIDownloader(QWidget):
    def __init__(self):
        super().__init__()

        # Load the user's settings
        self.settings = QSettings('./myrientDownloaderGUI.ini', QSettings.IniFormat)
        self.ps3dec_binary = self.settings.value('ps3dec_binary', '')
        self.psxiso_dir = self.settings.value('psxiso_dir', 'MyrientDownloads/PSXISO')
        self.ps2iso_dir = self.settings.value('ps2iso_dir', 'MyrientDownloads/PS2ISO')
        self.pspiso_dir = self.settings.value('pspiso_dir', 'MyrientDownloads/PSPISO')
        self.ps3iso_dir = self.settings.value('ps3iso_dir', 'MyrientDownloads/PS3ISO')
        self.psn_pkg_dir = self.settings.value('psn_pkg_dir', 'MyrientDownloads/packages')
        self.psn_rap_dir = self.settings.value('psn_rap_dir', 'MyrientDownloads/exdata')
        self.gciso_dir = self.settings.value('gciso_dir', 'MyrientDownloads/GCISO')
        self.processing_dir = 'processing'

        # Create directories if they do not exist
        os.makedirs(self.psxiso_dir, exist_ok=True)
        os.makedirs(self.ps2iso_dir, exist_ok=True)
        os.makedirs(self.pspiso_dir, exist_ok=True)
        os.makedirs(self.ps3iso_dir, exist_ok=True)
        os.makedirs(self.psn_pkg_dir, exist_ok=True)
        os.makedirs(self.psn_rap_dir, exist_ok=True)
        os.makedirs(self.gciso_dir, exist_ok=True)
        os.makedirs(self.processing_dir, exist_ok=True)

        # Check if the saved binary paths exist
        if not os.path.isfile(self.ps3dec_binary):
            self.ps3dec_binary = ''
            self.settings.setValue('ps3dec_binary', '')

        # Check if ps3dec is in the user's PATH
        ps3dec_in_path = shutil.which("ps3dec") or shutil.which("PS3Dec") or shutil.which("ps3dec.exe") or shutil.which("PS3Dec.exe")

        if ps3dec_in_path:
            self.ps3dec_binary = ps3dec_in_path
            self.settings.setValue('ps3dec_binary', self.ps3dec_binary)

        # Check if the saved settings are valid
        if not self.is_valid_binary(self.ps3dec_binary, 'ps3dec'):
            # If not, open the first startup prompt
            self.first_startup()

        self.psxiso_list, self.ps2iso_list, self.pspiso_list, self.ps3iso_list, self.psn_list, self.gciso_list = [['Loading... this will take a moment'] for _ in range(6)]

        self.psxiso_thread = self.load_software_list(self.psxiso_list, "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation/", 'psxlist.json', self.set_psxiso_list)
        self.ps2iso_thread = self.load_software_list(self.ps2iso_list, "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%202/", 'ps2isolist.json', self.set_ps2iso_list)
        self.pspiso_thread = self.load_software_list(self.pspiso_list, "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%20Portable/", 'psplist.json', self.set_pspiso_list)
        self.ps3iso_thread = self.load_software_list(self.ps3iso_list, "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%203/", 'ps3isolist.json', self.set_ps3iso_list)
        self.psn_thread = self.load_software_list(self.psn_list, "https://myrient.erista.me/files/No-Intro/Sony%20-%20PlayStation%203%20(PSN)%20(Content)", 'psnlist.json', self.set_psn_list)  
        self.gciso_thread = self.load_software_list(self.gciso_list, "https://myrient.erista.me/files/Redump/Nintendo%20-%20GameCube%20-%20NKit%20RVZ%20%5Bzstd-19-128k%5D/", 'gclist.json', self.set_gciso_list)
        self.psxiso_thread.start()
        self.ps2iso_thread.start()
        self.pspiso_thread.start()
        self.ps3iso_thread.start()
        self.psn_thread.start()
        self.gciso_thread.start()        

        # For displaying queue position in OutputWindow
        self.processed_items = 0 
        self.total_items = 0 

        # Load the queue from 'queue.txt'
        if os.path.exists('queue.txt'):
            with open('queue.txt', 'rb') as file:
                self.queue = pickle.load(file)
        else:
            self.queue = []

        self.initUI()

        # Add the entries from 'queue.txt' to the queue
        for item in self.queue:
            self.queue_list.addItem(item)

        # Add a signal handler for SIGINT to stop the download and save the queue
        signal.signal(signal.SIGINT, self.closeEvent)

    def closeEvent(self, event):
        # Stop the UnzipRunner and DownloadThread
        self.download_thread.stop()
        self.unzip_runner.stop()

        # Save the queue to 'queue.txt'
        with open('queue.txt', 'wb') as file:
            pickle.dump([self.queue_list.item(i).text() for i in range(self.queue_list.count())], file)

        event.accept()  # Accept the close event


    def initUI(self):
        vbox = QVBoxLayout()

        # Add a header for the Manufacturer list
        manufacturer_header = QLabel('Manufacturer')
        vbox.addWidget(manufacturer_header)

        #Combobox for Manufacturer
        self.manufacturer = QComboBox(self)
        self.manufacturer.addItems(['Sony', 'Nintendo'])
        vbox.addWidget(self.manufacturer)
        
        # Add a header for the software list
        iso_list_header = QLabel('Software')
        vbox.addWidget(iso_list_header)

        # Create a search box
        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText('Search...')
        self.search_box.textChanged.connect(self.update_results)
        vbox.addWidget(self.search_box)

        # Create a list for each Console
        self.result_list = QTabWidget(self)
        self.result_list.addTab(QListWidget(), "PSX ISOs")
        self.result_list.addTab(QListWidget(), "PS2 ISOs")
        self.result_list.addTab(QListWidget(), "PSP ISOs")
        self.result_list.addTab(QListWidget(), "PS3 ISOs")
        self.result_list.addTab(QListWidget(), "PSN PKGs")
        self.result_list.addTab(QListWidget(), "GC ISOs")
        self.result_list.widget(0).addItems(self.ps3iso_list)
        self.result_list.widget(1).addItems(self.psn_list)
        self.result_list.widget(2).addItems(self.ps2iso_list)
        self.result_list.widget(3).addItems(self.psxiso_list)
        self.result_list.widget(4).addItems(self.pspiso_list)
        self.result_list.widget(5).addItems(self.gciso_list)
        self.result_list.currentChanged.connect(self.update_add_to_queue_button)
        self.result_list.currentChanged.connect(self.update_results)
        vbox.addWidget(self.result_list)

        #Hide Nintendo Tabs by default
        self.result_list.setTabVisible(5, False)
        self.manufacturer.currentIndexChanged.connect(self.manufacturer_selection)

        # Connect the itemSelectionChanged signal to the update_add_to_queue_button method
        self.result_list.widget(0).itemSelectionChanged.connect(self.update_add_to_queue_button)
        self.result_list.widget(1).itemSelectionChanged.connect(self.update_add_to_queue_button)
        self.result_list.widget(2).itemSelectionChanged.connect(self.update_add_to_queue_button)
        self.result_list.widget(3).itemSelectionChanged.connect(self.update_add_to_queue_button)
        self.result_list.widget(4).itemSelectionChanged.connect(self.update_add_to_queue_button)
        self.result_list.widget(5).itemSelectionChanged.connect(self.update_add_to_queue_button)

        # Allow selecting multiple items
        self.result_list.widget(0).setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.result_list.widget(1).setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.result_list.widget(2).setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.result_list.widget(3).setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.result_list.widget(4).setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.result_list.widget(5).setSelectionMode(QAbstractItemView.ExtendedSelection)

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

        # Add the horizontal box layout to the vertical box layout
        vbox.addLayout(hbox)

        # Add a header for the Queue
        queue_header = QLabel('Queue')
        vbox.addWidget(queue_header)

        # Create queue list
        self.queue_list = QListWidget(self)
        self.queue_list.setSelectionMode(QAbstractItemView.MultiSelection)  
        self.queue_list.itemSelectionChanged.connect(self.update_remove_from_queue_button) 
        vbox.addWidget(self.queue_list)

        # Create a grid layout for the options
        grid = QGridLayout()

        # Add a header for the options
        iso_options_header = QLabel('ISO Settings')
        grid.addWidget(iso_options_header, 0, 0)

        pkg_options_header = QLabel('PKG Settings')
        grid.addWidget(pkg_options_header, 0, 1)

        # Create a checkbox for decrypting the file
        self.decrypt_checkbox = QCheckBox('Decrypt (if necessary)', self)
        self.decrypt_checkbox.setChecked(True)  # Enable checkbox by default
        grid.addWidget(self.decrypt_checkbox, 1, 0)

        # Create a checkbox for keeping or deleting the encrypted ISO file
        self.keep_enc_checkbox = QCheckBox('Keep encrypted ISO', self)
        self.keep_enc_checkbox.setChecked(False)
        grid.addWidget(self.keep_enc_checkbox, 2, 0)

        # Create a checkbox for splitting the file for FAT32 filesystems
        self.split_checkbox = QCheckBox('Split for FAT32 (if > 4GB)', self)
        self.split_checkbox.setChecked(True)  # Enable checkbox by default
        grid.addWidget(self.split_checkbox, 3, 0)

        # Create a checkbox for keeping or deleting the unsplit decrypted ISO file
        self.keep_unsplit_dec_checkbox = QCheckBox('Keep unsplit ISO', self)
        self.keep_unsplit_dec_checkbox.setChecked(False)
        grid.addWidget(self.keep_unsplit_dec_checkbox, 4, 0)

        # Create a checkbox for splitting the PKG file
        self.split_pkg_checkbox = QCheckBox('Split PKG', self)
        self.split_pkg_checkbox.setChecked(True) # Enable checkbox by default
        grid.addWidget(self.split_pkg_checkbox, 1, 1)

        # Create a checkbox for keeping or deleting the dkey file
        self.keep_dkey_checkbox = QCheckBox('Keep dkey file', self)
        self.keep_dkey_checkbox.setChecked(False)
        grid.addWidget(self.keep_dkey_checkbox, 5, 0)

        # Connect the stateChanged signal of the decrypt_checkbox to a slot that shows or hides the keep_enc_checkbox
        self.decrypt_checkbox.stateChanged.connect(self.keep_enc_checkbox.setVisible)

        # Connect the stateChanged signal of the split_checkbox to a slot that shows or hides the keep_unsplit_dec_checkbox
        self.split_checkbox.stateChanged.connect(self.keep_unsplit_dec_checkbox.setVisible)

        # Create a group box to contain the grid layout
        group_box = QGroupBox()
        group_box.setLayout(grid)
        vbox.addWidget(group_box)

        # Create a settings button
        self.settings_button = QPushButton('Settings', self)
        self.settings_button.clicked.connect(self.open_settings)
        vbox.addWidget(self.settings_button)

        # Create a button to start the process
        self.start_button = QPushButton('Start', self)
        self.start_button.clicked.connect(self.start_download)
        vbox.addWidget(self.start_button)

        # Add a header for the Output Window
        output_window_header = QLabel('Logs')
        vbox.addWidget(output_window_header)

        # Create an output window
        self.output_window = OutputWindow(self)
        vbox.addWidget(self.output_window)

        # Add a header for the progress bar
        queue_header = QLabel('Progress')
        vbox.addWidget(queue_header)

        # Create a progress bar and add it to the layout
        self.progress_bar = QProgressBar(self)
        vbox.addWidget(self.progress_bar)

        # Add a header for the speed, eta
        queue_header = QLabel('Download Speed & ETA')
        vbox.addWidget(queue_header)

        # Create labels for download speed and ETA
        self.download_speed_label = QLabel(self)
        vbox.addWidget(self.download_speed_label)
        self.download_eta_label = QLabel(self)
        vbox.addWidget(self.download_eta_label)

        self.setLayout(vbox)

        self.setWindowTitle('Myrient Downloader')
        self.resize(800, 600)
        self.show()

    def manufacturer_selection(self):
        '''
        0: Sony
        1: Nintendo
        '''
        manuIndexAssignment = [0,0,0,0,0,1]
        for i in range(len(manuIndexAssignment)):
            self.result_list.setTabVisible(i, self.manufacturer.currentIndex() == manuIndexAssignment[i])

    def load_software_list(self, software_list, url, json_filename, setter):
        thread = GetSoftwareListThread(url, json_filename)
        thread.signal.connect(setter)
        thread.start()
        return thread  # Return the thread

    def start_download(self):
        # Disable the GUI buttons
        self.settings_button.setEnabled(False)
        self.add_to_queue_button.setEnabled(False)
        self.remove_from_queue_button.setEnabled(False)
        self.decrypt_checkbox.setEnabled(False)
        self.split_checkbox.setEnabled(False)
        self.keep_dkey_checkbox.setEnabled(False)
        self.keep_enc_checkbox.setEnabled(False)
        self.keep_unsplit_dec_checkbox.setEnabled(False)
        self.split_pkg_checkbox.setEnabled(False)
        self.keep_dkey_checkbox.setEnabled(False)
        self.start_button.setEnabled(False)

        while self.queue_list.count() > 0:
            item_text = self.queue_list.item(0).text()

            # Get the total number of items in the queue
            if self.processed_items == 0:  # Only update total_items at the start of the download process
                self.total_items = self.queue_list.count()

            # Increment the processed_items counter
            self.processed_items += 1

            if item_text in self.psxiso_list:
                file_paths = self.downloadpsxzip(item_text, f"{self.processed_items}/{self.total_items}")
            elif item_text in self.ps2iso_list:
                file_paths = self.downloadps2isozip(item_text, f"{self.processed_items}/{self.total_items}")
            elif item_text in self.pspiso_list:
                file_paths = self.downloadpspisozip(item_text, f"{self.processed_items}/{self.total_items}")
            elif item_text in self.ps3iso_list:
                file_paths = self.downloadps3isozip(item_text, f"{self.processed_items}/{self.total_items}")
            elif item_text in self.psn_list:
                file_paths = self.downloadps3psnzip(item_text, f"{self.processed_items}/{self.total_items}")
            else:
                file_paths = self.downloadgczip(item_text, f"{self.processed_items}/{self.total_items}")

            # Remove the first item from the queue list
            self.queue_list.takeItem(0)

        self.processed_items = 0
        self.total_items = 0

        # Save the queue to 'queue.txt'
        with open('queue.txt', 'wb') as file:
            pickle.dump([self.queue_list.item(i).text() for i in range(self.queue_list.count())], file)

        # Re-enable the buttons
        self.settings_button.setEnabled(True)
        self.add_to_queue_button.setEnabled(True)
        self.remove_from_queue_button.setEnabled(True)
        self.decrypt_checkbox.setEnabled(True)
        self.split_checkbox.setEnabled(True)
        self.keep_dkey_checkbox.setEnabled(True)
        self.keep_enc_checkbox.setEnabled(True)
        self.keep_unsplit_dec_checkbox.setEnabled(True)
        self.split_pkg_checkbox.setEnabled(True)
        self.keep_dkey_checkbox.setEnabled(True)
        self.start_button.setEnabled(True)




    def downloadhelper(self, selected_iso, queue_position, url):
        # URL-encode the selected_iso
        selected_iso_encoded = urllib.parse.quote(selected_iso)
        
        # Load the user's settings
        settings = QSettings('./myrientDownloaderGUI.ini', QSettings.IniFormat)
        ps3dec_binary = settings.value('ps3dec_binary', '')

        # Compute base_name from selected_iso
        base_name = os.path.splitext(selected_iso)[0]

        # Define the file paths for .iso, .pkg, or .rvz files
        iso_file_path = os.path.join(self.processing_dir, base_name + '.iso')
        pkg_file_path = os.path.join(self.processing_dir, base_name + '.pkg')
        rvz_file_path = os.path.join(self.processing_dir, base_name + '.rvz')

        # Check if the .iso, .pkg, or .rvz file already exists
        paths = [iso_file_path,pkg_file_path,rvz_file_path]
        for path in paths:
            if os.path.exists(path):
                print(f"File {path} already exists. Skipping download.")
                return path
        # Define the path for the .zip file
        zip_file_path = os.path.join(self.processing_dir, base_name + '.zip')

        # If the .zip file exists, compare its size to that of the remote URL
        if os.path.exists(zip_file_path):
            local_file_size = os.path.getsize(zip_file_path)

            # Get the size of the remote file
            response = requests.head(f"{url}/{selected_iso_encoded}")
            if 'content-length' in response.headers:
                remote_file_size = int(response.headers['content-length'])
            else:
                print("Could not get the size of the remote file.")
                return zip_file_path

            # If the local file is smaller, attempt to resume the download
            if local_file_size < remote_file_size:
                print(f"Local file is smaller than the remote file. Attempting to resume download...")
            # If the local file is the same size as the remote file, skip the download
            elif local_file_size == remote_file_size:
                print(f"Local file is the same size as the remote file. Skipping download...")
                return zip_file_path

        # If the file does not exist, proceed with the download
        self.output_window.append(f"({queue_position}) Download started for {base_name}...")
        self.progress_bar.reset()  # Reset the progress bar to 0
        self.download_thread = DownloadThread(f"{url}/{selected_iso_encoded}", zip_file_path)
        self.download_thread.progress_signal.connect(self.progress_bar.setValue)
        self.download_thread.speed_signal.connect(self.download_speed_label.setText)
        self.download_thread.eta_signal.connect(self.download_eta_label.setText)

        # Create a QEventLoop
        loop = QEventLoop()
        self.download_thread.finished.connect(loop.quit)

        # Start the thread and the event loop
        self.download_thread.start()
        loop.exec_()

        return zip_file_path

    def downloadpsxzip(self, selected_iso, queue_position):
        url = "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation"
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)

        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")

        # Unzip the ISO and delete the ZIP file
        runner = UnzipRunner(file_path, self.processing_dir)
        runner.progress_signal.connect(self.progress_bar.setValue)
        runner.start()
        loop = QEventLoop()
        runner.finished.connect(loop.quit)
        loop.exec_()

        os.remove(file_path)

        # Move the finished file to the output directory
        for file in glob.glob(os.path.join(self.processing_dir, base_name + '*')):
            shutil.move(file, self.psxiso_dir)

        self.queue_list.takeItem(0)
        self.output_window.append(f"({queue_position}) {base_name} complete!")

        # If there are more items in the queue, start the next download
        if self.queue_list.count() > 0:
            self.start_download()

    def downloadps2isozip(self, selected_iso, queue_position):
        url = "https://myrient.erista.me/files/Redump/Sony - PlayStation 2"
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)

        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")

        # Unzip the ISO and delete the ZIP file
        runner = UnzipRunner(file_path, self.processing_dir)
        runner.progress_signal.connect(self.progress_bar.setValue)
        runner.start()
        loop = QEventLoop()
        runner.finished.connect(loop.quit)
        loop.exec_()

        os.remove(file_path)

        # Go through the extracted files
        for file in runner.extracted_files:
            if file.endswith('.iso'):
                if self.split_checkbox.isChecked() and os.path.getsize(file) >= 4294967295:
                    self.output_window.append(f"({queue_position}) Splitting ISO for {base_name}...")
                    split_iso_thread = SplitIsoThread(file)
                    split_iso_thread.progress.connect(print)
                    split_iso_thread.start()
                    split_iso_thread.wait()  # Wait for the thread to finish

                    # Delete the unsplit iso if the checkbox is unchecked
                    if not self.keep_unsplit_dec_checkbox.isChecked() and os.path.exists(file):
                        os.remove(file)

                    for split_file in glob.glob(file.rsplit('.', 1)[0] + '*.iso.*'):
                        shutil.move(split_file, self.ps2iso_dir)

                else:
                    # Move the iso to ps2iso_dir
                    shutil.move(file, self.ps2iso_dir)

            # If the file is a .bin or .cue file, move it directly to ps2iso_dir
            elif file.endswith('.bin') or file.endswith('.cue'):
                shutil.move(file, self.ps2iso_dir)

        self.queue_list.takeItem(0)
        self.output_window.append(f"({queue_position}) {base_name} complete!")

        with open('queue.txt', 'wb') as file:
            pickle.dump([self.queue_list.item(i).text() for i in range(self.queue_list.count())], file)

        # If there are more items in the queue, start the next download
        if self.queue_list.count() > 0:
            self.start_download()

    def downloadpspisozip(self, selected_iso, queue_position):
        url = "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%20Portable"
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)

        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")

        # Unzip the ISO and delete the ZIP file
        runner = UnzipRunner(file_path, self.processing_dir)
        runner.progress_signal.connect(self.progress_bar.setValue)
        runner.start()
        loop = QEventLoop()
        runner.finished.connect(loop.quit)
        loop.exec_()

        os.remove(file_path)

        # Split processed .iso file if splitting is enabled
        if self.split_checkbox.isChecked() and os.path.getsize(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso")) >= 4294967295:
            self.output_window.append(f"({queue_position}) Splitting ISO for {base_name}...")
            split_iso_thread = SplitIsoThread(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso"))
            split_iso_thread.progress.connect(print)
            split_iso_thread.start()
            split_iso_thread.wait()  # Wait for the thread to finish

            # Delete the unsplit iso if the checkbox is unchecked
            if not self.keep_unsplit_dec_checkbox.isChecked() and os.path.exists(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso")):
                os.remove(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso"))

        # Move the finished file to the output directory
        for file in glob.glob(os.path.join(self.processing_dir, base_name + '*')):
            shutil.move(file, self.pspiso_dir)

        self.queue_list.takeItem(0)
        self.output_window.append(f"({queue_position}) {base_name} complete!")

        with open('queue.txt', 'wb') as file:
            pickle.dump([self.queue_list.item(i).text() for i in range(self.queue_list.count())], file)

        # If there are more items in the queue, start the next download
        if self.queue_list.count() > 0:
            self.start_download()

    def downloadps3isozip(self, selected_iso, queue_position):
        url = "https://dl10.myrient.erista.me/files/Redump/Sony - PlayStation 3"
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)

        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")

        # Unzip the ISO and delete the ZIP file
        runner = UnzipRunner(file_path, self.processing_dir)
        runner.progress_signal.connect(self.progress_bar.setValue)
        runner.start()
        loop = QEventLoop()
        runner.finished.connect(loop.quit)
        loop.exec_()

        os.remove(file_path)

        # Check if the corresponding dkey file already exists
        if not os.path.isfile(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.dkey")):
            if self.decrypt_checkbox.isChecked() or self.keep_dkey_checkbox.isChecked():
                # Download the corresponding dkey file
                self.output_window.append(f"({queue_position}) Getting dkey for {base_name}...")
                self.progress_bar.reset()  # Reset the progress bar to 0
                self.download_thread = DownloadThread(f"https://dl10.myrient.erista.me/files/Redump/Sony - PlayStation 3 - Disc Keys TXT/{os.path.splitext(selected_iso)[0]}.zip", os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.zip"))
                self.download_thread.progress_signal.connect(self.progress_bar.setValue)

                # Create a QEventLoop
                loop = QEventLoop()
                self.download_thread.finished.connect(loop.quit)

                # Start the thread and the event loop
                self.download_thread.start()
                loop.exec_()
                    
                # Unzip the dkey file and delete the ZIP file
                with zipfile.ZipFile(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.zip"), 'r') as zip_ref:
                    zip_ref.extractall(self.processing_dir)
                os.remove(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.zip"))

        # Run the PS3Dec command if decryption is enabled
        if self.decrypt_checkbox.isChecked():
        # Read the first 32 characters of the .dkey file
            if os.path.isfile(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.dkey")):
                with open(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.dkey"), 'r') as file:
                    key = file.read(32)
            self.output_window.append(f"({queue_position}) Decrypting ISO for {base_name}...")
            if platform.system() == 'Windows':
                thread_count = multiprocessing.cpu_count() // 2
                command = [f"{self.ps3dec_binary}", "--iso", os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso"), "--dk", key, "--tc", str(thread_count)]
            else:
                command = [self.ps3dec_binary, 'd', 'key', key, os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso")]

            runner = CommandRunner(command)
            runner.start()
            runner.wait()  # Wait for the command to complete

            # Rename the original ISO file to .iso.enc
            os.rename(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso"), os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso.enc"))

            # Check the platform and rename the decrypted file accordingly
            if platform.system() == 'Windows':
                os.rename(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso_decrypted.iso"), os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso"))
            else:
                os.rename(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso.dec"), os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso"))

            # Delete the .iso.enc if the checkbox is unchecked
            if not self.keep_enc_checkbox.isChecked():
                os.remove(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso.enc"))

        # Split processed .iso file if splitting is enabled
        if self.split_checkbox.isChecked() and os.path.getsize(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso")) >= 4294967295:
            self.output_window.append(f"({queue_position}) Splitting ISO for {base_name}...")
            split_iso_thread = SplitIsoThread(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso"))
            split_iso_thread.progress.connect(print)
            split_iso_thread.start()
            split_iso_thread.wait()  # Wait for the thread to finish

            # Delete the unsplit iso if the checkbox is unchecked
            if not self.keep_unsplit_dec_checkbox.isChecked() and os.path.exists(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso")):
                os.remove(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.iso"))

        # Delete the .dkey file if the 'Keep dkey file' checkbox is unchecked
        if not self.keep_dkey_checkbox.isChecked() and os.path.isfile(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.dkey")):
            os.remove(os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}.dkey"))

        # Move the finished file to the output directory
        for file in glob.glob(os.path.join(self.processing_dir, base_name + '*')):
            shutil.move(file, self.ps3iso_dir)

        self.queue_list.takeItem(0)
        self.output_window.append(f"({queue_position}) {base_name} complete!")

        with open('queue.txt', 'wb') as file:
            pickle.dump([self.queue_list.item(i).text() for i in range(self.queue_list.count())], file)

        # If there are more items in the queue, start the next download
        if self.queue_list.count() > 0:
            self.start_download()

    def downloadps3psnzip(self, selected_iso, queue_position):
        url = "https://dl8.myrient.erista.me/files/No-Intro/Sony%20-%20PlayStation%203%20(PSN)%20(Content)"
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)

        if not file_path.lower().endswith('.zip'):
            print(f"File {file_path} is not a .zip file. Skipping unzip.")
            return

        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")

        # Unzip the ISO and delete the ZIP file
        runner = UnzipRunner(file_path, self.processing_dir)
        runner.progress_signal.connect(self.progress_bar.setValue)
        runner.start()
        loop = QEventLoop()
        runner.finished.connect(loop.quit)
        loop.exec_()
        os.remove(file_path)

        # Rename the extracted .pkg file to the original name of the zip file
        for file in runner.extracted_files: 
            if file.endswith('.pkg'):
                new_file_path = os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}{os.path.splitext(file)[1]}")
                os.rename(file, new_file_path)
                if self.split_pkg_checkbox.isChecked():   # If the 'split PKG' checkbox is checked, split the PKG file
                    split_pkg_thread = SplitPkgThread(new_file_path)
                    split_pkg_thread.progress.connect(print)
                    split_pkg_thread.start()
                    split_pkg_thread.wait()

        # Move the finished file to the output directory
        for file in glob.glob(os.path.join(self.processing_dir, '*.rap')):
            dst = os.path.join(self.psn_rap_dir, os.path.basename(file))
            if os.path.exists(dst):
                print(f"File {dst} already exists. Overwriting.")
            shutil.move(file, dst)

        for file in glob.glob(os.path.join(self.processing_dir, '*.pkg')) + glob.glob(os.path.join(self.processing_dir, '*.pkg.*')):
            dst = os.path.join(self.psn_pkg_dir, os.path.basename(file))
            if os.path.exists(dst):
                print(f"File {dst} already exists. Overwriting.")
            shutil.move(file, dst)


        self.queue_list.takeItem(0)
        self.output_window.append(f"({queue_position}) {base_name} ready!")

        with open('queue.txt', 'wb') as file:
            pickle.dump([self.queue_list.item(i).text() for i in range(self.queue_list.count())], file)

        # If there are more items in the queue, start the next download
        if self.queue_list.count() > 0:
            self.start_download()
          
    def downloadgczip(self, selected_iso, queue_position):
        url = "https://myrient.erista.me/files/Redump/Nintendo - GameCube - NKit RVZ [zstd-19-128k]"
        base_name = os.path.splitext(selected_iso)[0]
        file_path = self.downloadhelper(selected_iso, queue_position, url)

        if not file_path.lower().endswith('.zip'):
            print(f"File {file_path} is not a .zip file. Skipping unzip.")
            return

        self.output_window.append(f"({queue_position}) Unzipping {base_name}.zip...")

        # Unzip the ISO and delete the ZIP file
        runner = UnzipRunner(file_path, self.processing_dir)
        runner.progress_signal.connect(self.progress_bar.setValue)
        runner.start()
        loop = QEventLoop()
        runner.finished.connect(loop.quit)
        loop.exec_()
        os.remove(file_path)

        # Rename the extracted .rvz file to the original name of the zip file
        for file in runner.extracted_files: 
            if file.endswith('.rvz'):
                new_file_path = os.path.join(self.processing_dir, f"{os.path.splitext(selected_iso)[0]}{os.path.splitext(file)[1]}")
                os.rename(file, new_file_path)

        # Move the finished file to the output directory
        for file in glob.glob(os.path.join(self.processing_dir, '*.rvz')) + glob.glob(os.path.join(self.processing_dir, '*.rvz.*')):
            dst = os.path.join(self.gciso_dir, os.path.basename(file))
            if os.path.exists(dst):
                print(f"File {dst} already exists. Overwriting.")
            shutil.move(file, dst)


        self.queue_list.takeItem(0)
        self.output_window.append(f"({queue_position}) {base_name} ready!")

        with open('queue.txt', 'wb') as file:
            pickle.dump([self.queue_list.item(i).text() for i in range(self.queue_list.count())], file)

        # If there are more items in the queue, start the next download
        if self.queue_list.count() > 0:
            self.start_download()

    def add_to_queue(self):
        selected_items = self.result_list.currentWidget().selectedItems()
        for item in selected_items:
            item_text = item.text()
            if not any(item_text == self.queue_list.item(i).text() for i in range(self.queue_list.count())):
                self.queue_list.addItem(item_text)

        # Save the queue to 'queue.txt'
        with open('queue.txt', 'wb') as file:
            pickle.dump([self.queue_list.item(i).text() for i in range(self.queue_list.count())], file)

    def remove_from_queue(self):
        selected_items = self.queue_list.selectedItems()
        for item in selected_items:
            # Remove the item from the queue list
            self.queue_list.takeItem(self.queue_list.row(item))

        # Save the queue to 'queue.txt'
        with open('queue.txt', 'wb') as file:
            pickle.dump([self.queue_list.item(i).text() for i in range(self.queue_list.count())], file)


    def update_add_to_queue_button(self):
        self.add_to_queue_button.setEnabled(bool(self.result_list.currentWidget().selectedItems()))

    def update_remove_from_queue_button(self):
        self.remove_from_queue_button.setEnabled(bool(self.queue_list.selectedItems()))

    def stop_process(self):
        # TODO: Implement the logic to stop the current process
        pass

    def update_results(self):
        search_term = self.search_box.text().lower().split()

        if self.result_list.currentIndex() == 0:
            list_to_search = self.psxiso_list
        elif self.result_list.currentIndex() == 1:
            list_to_search = self.ps2iso_list
        elif self.result_list.currentIndex() == 2:
            list_to_search = self.pspiso_list
        elif self.result_list.currentIndex() == 3:
            list_to_search = self.ps3iso_list
        elif self.result_list.currentIndex() == 4:
            list_to_search = self.psn_list
        else:
            list_to_search = self.gciso_list

        filtered_list = [item for item in list_to_search if all(word in item.lower() for word in search_term)]

        # Clear the current list widget and add the filtered items
        current_list_widget = self.result_list.currentWidget()
        current_list_widget.clear()
        current_list_widget.addItems(filtered_list)

    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)

    def set_psxiso_list(self, psxiso_list):
        self.psxiso_list = psxiso_list
        self.result_list.widget(0).clear()
        self.result_list.widget(0).addItems(self.psxiso_list)

    def set_ps2iso_list(self, ps2iso_list):
        self.ps2iso_list = ps2iso_list
        self.result_list.widget(1).clear()
        self.result_list.widget(1).addItems(self.ps2iso_list)

    def set_pspiso_list(self, pspiso_list):
        self.pspiso_list = pspiso_list
        self.result_list.widget(2).clear()
        self.result_list.widget(2).addItems(self.pspiso_list)

    def set_ps3iso_list(self, ps3iso_list):
        self.ps3iso_list = ps3iso_list
        self.result_list.widget(3).clear()
        self.result_list.widget(3).addItems(self.ps3iso_list)

    def set_psn_list(self, psn_list):
        self.psn_list = psn_list
        self.result_list.widget(4).clear()
        self.result_list.widget(4).addItems(self.psn_list)
        
    def set_gciso_list(self, gciso_list):
        self.gciso_list = gciso_list
        self.result_list.widget(5).clear()
        self.result_list.widget(5).addItems(self.gciso_list)

    def append_to_output_window(self, text):
        self.output_window.append(text)

    def settings_welcome_dialog(self, title, close_button_text, add_iso_list_section=False, welcome_text=None):
        dialog = QDialog()
        dialog.setWindowTitle(title)
        vbox = QVBoxLayout(dialog)

        # Adds welcome text when provided
        if welcome_text is not None:
            welcome_label = QLabel(welcome_text)
            vbox.addWidget(welcome_label)

        def select_location(name, select_button, path_textbox, download_button=None):
            hbox = QHBoxLayout()
            hbox.addWidget(select_button)
            hbox.addWidget(path_textbox)
            if download_button is not None:
                hbox.addWidget(download_button)
            vbox.addLayout(hbox)

        # PS3Dec section
        ps3decSelectButton = QPushButton('Choose PS3Dec Binary')
        ps3decPathTextbox = QLineEdit(self.settings.value('ps3dec_binary', ''))
        ps3decSelectButton.clicked.connect(lambda: self.open_file_dialog(ps3decPathTextbox, 'ps3dec_binary'))
        ps3decDownloadButton = QPushButton('Download PS3Dec')
        if sys.platform == "win32":
            ps3decDownloadButton.clicked.connect(lambda: self.download_ps3dec(ps3decDownloadButton, ps3decPathTextbox))
        else:
            ps3decDownloadButton.setEnabled(False)
            ps3decDownloadButton.setToolTip('PS3Dec can only be retrieved on Windows')
        select_location("PS3Dec:", ps3decSelectButton, ps3decPathTextbox, ps3decDownloadButton)

        # PSXISO section
        psxisoSelectButton = QPushButton('Choose PSXISO Directory')
        psxisoPathTextbox = QLineEdit(self.settings.value('psxiso_dir', 'MyrientDownloads/PSXISO'))
        psxisoSelectButton.clicked.connect(lambda: self.open_directory_dialog(psxisoPathTextbox, 'psxiso_dir'))
        select_location("PSXISO Directory:", psxisoSelectButton, psxisoPathTextbox)

        # PS2ISO section
        ps2isoSelectButton = QPushButton('Choose PS2ISO Directory')
        ps2isoPathTextbox = QLineEdit(self.settings.value('ps2iso_dir', 'MyrientDownloads/PS2ISO'))
        ps2isoSelectButton.clicked.connect(lambda: self.open_directory_dialog(ps2isoPathTextbox, 'ps2iso_dir'))
        select_location("PS2ISO Directory:", ps2isoSelectButton, ps2isoPathTextbox)

        # PSPISO section
        pspisoSelectButton = QPushButton('Choose PSPISO Directory')
        pspisoPathTextbox = QLineEdit(self.settings.value('pspiso_dir', 'MyrientDownloads/PSPISO'))
        pspisoSelectButton.clicked.connect(lambda: self.open_directory_dialog(pspisoPathTextbox, 'pspiso_dir'))
        select_location("PSPISO Directory:", pspisoSelectButton, pspisoPathTextbox)

        # PS3ISO section
        ps3isoSelectButton = QPushButton('Choose PS3ISO Directory')
        ps3isoPathTextbox = QLineEdit(self.settings.value('ps3iso_dir', 'MyrientDownloads/PS3ISO'))
        ps3isoSelectButton.clicked.connect(lambda: self.open_directory_dialog(ps3isoPathTextbox, 'ps3iso_dir'))
        select_location("PS3ISO Directory:", ps3isoSelectButton, ps3isoPathTextbox)

        # PSN PKG section
        psn_pkg_SelectButton = QPushButton('Choose PSN PKG Directory')
        psn_pkg_PathTextbox = QLineEdit(self.settings.value('psn_pkg_dir', 'MyrientDownloads/packages'))
        psn_pkg_SelectButton.clicked.connect(lambda: self.open_directory_dialog(psn_pkg_PathTextbox, 'psn_pkg_dir'))
        select_location("PSN PKG Directory:", psn_pkg_SelectButton, psn_pkg_PathTextbox)

        # PSN RAP section
        psn_rap_SelectButton = QPushButton('Choose PSN RAP Directory')
        psn_rap_PathTextbox = QLineEdit(self.settings.value('psn_rap_dir', 'MyrientDownloads/exdata'))
        psn_rap_SelectButton.clicked.connect(lambda: self.open_directory_dialog(psn_rap_PathTextbox, 'psn_rap_dir'))
        select_location("PSN RAP Directory:", psn_rap_SelectButton, psn_rap_PathTextbox)
        
        # GCISO section
        gcisoSelectButton = QPushButton('Choose GCISO Directory')
        gcisoPathTextbox = QLineEdit(self.settings.value('gciso_dir', 'MyrientDownloads/GCISO'))
        gcisoSelectButton.clicked.connect(lambda: self.open_directory_dialog(gcisoPathTextbox, 'gciso_dir'))
        select_location("GCISO Directory:", gcisoSelectButton, gcisoPathTextbox)

        # ISO List section
        if add_iso_list_section:
            iso_list_button = QPushButton('Update software lists')
            iso_list_button.clicked.connect(self.update_iso_list)
            vbox.addWidget(iso_list_button)

        # Close button
        closeButton = QPushButton(close_button_text)
        closeButton.clicked.connect(dialog.close)
        vbox.addWidget(closeButton)

        dialog.exec_()

    def open_file_dialog(self, textbox, setting_key):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        fileName, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*);;Executable Files (*.exe)", options=options)
        if fileName:
            self.settings.setValue(setting_key, fileName)
            textbox.setText(fileName)  # Update the textbox with the new path

    def open_directory_dialog(self, textbox, setting_key):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        dirName = QFileDialog.getExistingDirectory(self, "Select Directory", options=options)
        if dirName:
            self.settings.setValue(setting_key, dirName)
            textbox.setText(dirName)  # Update the textbox with the new path

            # Update the directory path in the application
            if setting_key == 'psx_dir':
                self.psx_dir = dirName
            elif setting_key == 'ps2iso_dir':
                self.ps2iso_dir = dirName
            elif setting_key == 'psp_dir':
                self.psp_dir = dirName
            elif setting_key == 'ps3iso_dir':
                self.ps3iso_dir = dirName
            elif setting_key == 'psn_pkg_dir':
                self.psn_pkg_dir = dirName
            elif setting_key == 'psn_rap_dir':
                self.psn_rap_dir = dirName
            elif setting_key == 'gc_dir':
                self.gc_dir = dirName

    def open_settings(self):
        self.settings_welcome_dialog("Tools", "Close", add_iso_list_section=True)

    def first_startup(self):
        welcome_text = "Welcome! The script can attempt to grab PS3Dec automatically or you can set it manually"
        self.settings_welcome_dialog("Welcome!", "Continue", welcome_text=welcome_text)

    def update_iso_list(self):
        self.get_psxiso_list_thread.start()
        self.get_ps2iso_list_thread.start()
        self.get_pspiso_list_thread.start()
        self.get_ps3iso_list_thread.start()
        self.get_psn_list_thread.start()        
        self.get_gciso_list_thread.start()

    def is_valid_binary(self, path, binary_name):
        # Check if the path is not empty, the file exists and the filename ends with the correct binary name
        if path and os.path.isfile(path):
            filename = os.path.basename(path)
            if sys.platform == "win32":
                # On Windows, check if the filename ends with .exe (case insensitive)
                return filename.lower() == f"{binary_name}.exe"
            else:
                # On other platforms, just check the filename (case insensitive)
                return filename.lower() == binary_name.lower()
        return False

    def download_ps3dec(self, ps3decButton, textbox):
        urllib.request.urlretrieve("https://github.com/Redrrx/ps3dec/releases/download/0.1.0/ps3dec.exe", "ps3dec.exe")
        self.ps3dec_binary = os.path.join(os.getcwd(), "ps3dec.exe")
        self.settings.setValue('ps3dec_binary', self.ps3dec_binary)

        # Update the button
        ps3decButton.setText('PS3Dec downloaded! ✅')
        ps3decButton.setEnabled(False)

        self.ps3dec_binary = './ps3dec' if sys.platform != "Windows" else './ps3dec.exe'
        self.settings.setValue('ps3dec_binary', self.ps3dec_binary)
        textbox.setText(self.ps3dec_binary)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = GUIDownloader()
    sys.exit(app.exec_())
