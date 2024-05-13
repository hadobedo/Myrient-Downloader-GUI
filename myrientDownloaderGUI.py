import os
import subprocess
import zipfile
import sys
import requests
import traceback
import platform
import urllib.request
import tarfile
import shutil
import multiprocessing
import urllib
import json
import time
import aiohttp, asyncio
import urllib.parse
from urllib.parse import unquote
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QComboBox, QLineEdit, QListWidget, QLabel, QCheckBox, QTextEdit, QFileDialog, QMessageBox, QDialog, QHBoxLayout, QAbstractItemView, QProgressBar, QTabWidget
from PyQt5.QtCore import QThread, pyqtSignal, QSettings, QEventLoop
from PyQt5.QtGui import QTextCursor
from threading import Lock

class GetPS3ISOListThread(QThread):
    signal = pyqtSignal('PyQt_PyObject')

    def __init__(self):
        QThread.__init__(self)

    def run(self):
        ps3iso_list = []
        if os.path.exists('ps3isolist.json'):
            with open('ps3isolist.json', 'r') as file:
                ps3iso_list = json.load(file)
        
        if not ps3iso_list:
            url = "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%203/"
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            ps3iso_list = [unquote(link.get('href')) for link in soup.find_all('a') if link.get('href').endswith('.zip')]
            with open('ps3isolist.json', 'w') as file:
                json.dump(ps3iso_list, file)

        self.signal.emit(ps3iso_list)

class GetPS3PSNSoftwareListThread(QThread):
    signal = pyqtSignal('PyQt_PyObject')

    def __init__(self):
        QThread.__init__(self)

    def run(self):
        psn_list = []
        if os.path.exists('psnlist.json'):
            with open('psnlist.json', 'r') as file:
                psn_list = json.load(file)
        
        if not psn_list:
            url = "https://myrient.erista.me/files/No-Intro/Sony%20-%20PlayStation%203%20(PSN)%20(Content)"
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            psn_list = [unquote(link.get('href')) for link in soup.find_all('a') if link.get('href').endswith('.zip')]
            with open('psnlist.json', 'w') as file:
                json.dump(psn_list, file)

        self.signal.emit(psn_list)

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
def run_command(command, output_window):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
    
    # If on Windows, send a newline character to ps3dec's standard input
    if platform.system() == 'Windows':
        process.stdin.write(b'\n')
        process.stdin.flush()
        
    for line in iter(process.stdout.readline, b''):
        # Strip newline characters from the end of the line before appending
        output_window.append(line.decode().rstrip('\n'))
        QApplication.processEvents()
    process.stdout.close()
    return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)

# Function to unzip a file with progress
def unzip_file(zip_path, output_path, output_window):
    extracted_files = []
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for i, file in enumerate(zip_ref.infolist(), start=1):
            output_window.write(f"Extracting {file.filename} (program may look frozen, please wait!)\n")
            zip_ref.extract(file, output_path)
            extracted_files.append(file.filename)
            QApplication.processEvents()
    return extracted_files


class DownloadThread(QThread):
    progress_signal = pyqtSignal(int)
    speed_signal = pyqtSignal(str)
    eta_signal = pyqtSignal(str)
    download_complete_signal = pyqtSignal()

    def __init__(self, url, filename, retries=10):
        QThread.__init__(self)
        self.url = url
        self.filename = filename
        self.retries = retries
        self.existing_file_size = 0 # used for speed, eta calc
        self.start_time = None # used for speed, eta calc
        self.current_session_downloaded = 0  # used for speed, eta calc

    async def download(self):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }

        for i in range(self.retries):
            try:
                # If the file already exists, get its size and set the Range header
                if os.path.exists(self.filename):
                    self.existing_file_size = os.path.getsize(self.filename)
                    headers['Range'] = f'bytes={self.existing_file_size}-'

                async with aiohttp.ClientSession() as session:
                    async with session.get(self.url, headers=headers) as response:
                        if response.status not in (200, 206):  # 200 = OK, 206 = Partial Content
                            raise aiohttp.ClientPayloadError()

                        # Get the total file size from the Content-Range header
                        if 'content-range' in response.headers:
                            total_size = int(response.headers['content-range'].split('/')[-1])
                        else:
                            total_size = int(response.headers.get('content-length'))

                        # Open the file in append mode, and write each chunk to the file
                        with open(self.filename, 'ab') as file:
                            self.start_time = time.time()
                            while True:
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                file.write(chunk)
                                self.existing_file_size += len(chunk)
                                self.current_session_downloaded += len(chunk)  # Update the current_session_downloaded
                                self.progress_signal.emit(int((self.existing_file_size / total_size) * 100))  # Emit the progress signal

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
                if i == self.retries - 1:  # If this was the last retry
                    raise  # Re-raise the exception
            except asyncio.TimeoutError:
                print(f"Download interrupted. Retrying ({i+1}/{self.retries})...")
                if i == self.retries - 1:  # If this was the last retry
                    raise  # Re-raise the exception

    def run(self):
        asyncio.run(self.download())
        self.download_complete_signal.emit()

def download_file(self, url, filename):
    self.progress_bar.reset()  # Reset the progress bar to 0 when new download begins
    self.download_thread = DownloadThread(url, filename)
    self.download_thread.start()

class GUIDownloader(QWidget):
    def __init__(self):
        super().__init__()

        # Load the user's settings
        self.settings = QSettings('./myrientDownloaderGUI.ini', QSettings.IniFormat)
        self.ps3dec_binary = self.settings.value('ps3dec_binary', '')
        self.splitps3iso_binary = self.settings.value('splitps3iso_binary', '')

        # Check if the saved binary paths exist
        if not os.path.isfile(self.ps3dec_binary):
            self.ps3dec_binary = ''
            self.settings.setValue('ps3dec_binary', '')
        if not os.path.isfile(self.splitps3iso_binary):
            self.splitps3iso_binary = ''
            self.settings.setValue('splitps3iso_binary', '')

        # Check if ps3dec and splitps3iso are in the user's PATH
        ps3dec_in_path = shutil.which("ps3dec") or shutil.which("PS3Dec") or shutil.which("ps3dec.exe") or shutil.which("PS3Dec.exe")
        splitps3iso_in_path = shutil.which("splitps3iso") or shutil.which("SplitPS3ISO") or shutil.which("splitps3iso.exe") or shutil.which("SplitPS3ISO.exe")

        if ps3dec_in_path:
            self.ps3dec_binary = ps3dec_in_path
            self.settings.setValue('ps3dec_binary', self.ps3dec_binary)

        if splitps3iso_in_path:
            self.splitps3iso_binary = splitps3iso_in_path
            self.settings.setValue('splitps3iso_binary', self.splitps3iso_binary)

        # Check if the saved settings are valid
        if not self.is_valid_binary(self.ps3dec_binary, 'ps3dec') or not self.is_valid_binary(self.splitps3iso_binary, 'splitps3iso'):
            # If not, open the first startup prompt
            self.first_startup()

        self.ps3iso_list = ['Loading from https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%203/...']
        self.psn_list = ['Loading from https://myrient.erista.me/files/No-Intro/Sony%20-%20PlayStation%203%20(PSN)%20(Content)...']

        # Get list of ISOs from the HTTPS directory
        self.get_ps3iso_list_thread = GetPS3ISOListThread()
        self.get_ps3iso_list_thread.signal.connect(self.set_ps3iso_list)
        self.get_ps3iso_list_thread.start()

        # Get list of PSN software from the HTTPS directory
        self.get_psn_list_thread = GetPS3PSNSoftwareListThread()
        self.get_psn_list_thread.signal.connect(self.set_psn_list)
        self.get_psn_list_thread.start()

        # For displaying queue position in OutputWindow
        self.processed_items = 0 
        self.total_items = 0 

        self.initUI()

    def initUI(self):
        vbox = QVBoxLayout()

        # Add a header for the software list
        iso_list_header = QLabel('Software')
        vbox.addWidget(iso_list_header)

        # Create a search box
        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText('Search...')
        self.search_box.textChanged.connect(self.update_results)
        vbox.addWidget(self.search_box)

        # Create a list for results (software list)
        self.result_list = QTabWidget(self)
        self.result_list.addTab(QListWidget(), "ISOs")
        self.result_list.addTab(QListWidget(), "PSN")
        self.result_list.widget(0).addItems(self.ps3iso_list)
        self.result_list.widget(1).addItems(self.psn_list)
        self.result_list.currentChanged.connect(self.update_add_to_queue_button)
        vbox.addWidget(self.result_list)

        # Connect the itemSelectionChanged signal to the update_add_to_queue_button method
        self.result_list.widget(0).itemSelectionChanged.connect(self.update_add_to_queue_button)
        self.result_list.widget(1).itemSelectionChanged.connect(self.update_add_to_queue_button)

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

        # Add a header for the Queue
        queue_header = QLabel('Queue')
        vbox.addWidget(queue_header)

        # Create queue list
        self.queue_list = QListWidget(self)
        self.queue_list.setSelectionMode(QAbstractItemView.MultiSelection)  
        self.queue_list.itemSelectionChanged.connect(self.update_remove_from_queue_button) 
        vbox.addWidget(self.queue_list)

        # Add a header for the options
        queue_header = QLabel('ISO Options')
        vbox.addWidget(queue_header)

        # Create a dropdown menu for selecting the operation
        self.operation_dropdown = QComboBox(self)
        self.operation_dropdown.addItems(['Decrypt and Split', 'Decrypt Only', 'Download Only'])
        self.operation_dropdown.currentTextChanged.connect(self.update_checkboxes)
        vbox.addWidget(self.operation_dropdown)

        # Create a checkbox for keeping or deleting the encrypted ISO file
        self.keep_enc_checkbox = QCheckBox('Keep encrypted ISO', self)
        self.keep_enc_checkbox.setChecked(False)
        vbox.addWidget(self.keep_enc_checkbox)

        # Create a checkbox for keeping or deleting the unsplit decrypted ISO file
        self.keep_unsplit_dec_checkbox = QCheckBox('Keep unsplit decrypted ISO', self)
        self.keep_unsplit_dec_checkbox.setChecked(False)
        vbox.addWidget(self.keep_unsplit_dec_checkbox)

        # Create a checkbox for keeping or deleting the dkey file
        self.keep_dkey_checkbox = QCheckBox('Keep dkey file', self)
        self.keep_dkey_checkbox.setChecked(False)
        vbox.addWidget(self.keep_dkey_checkbox)

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

        self.setWindowTitle('Myrient PS3 Downloader')
        self.resize(800, 600)
        self.show()

    def start_download(self):
        if self.queue_list.count() > 0:
            item_text = self.queue_list.item(0).text()
            operation = self.operation_dropdown.currentText()  # Get the current operation from the dropdown

            # Get the total number of items in the queue
            if self.processed_items == 0:  # Only update total_items at the start of the download process
                self.total_items = self.queue_list.count()

            # Increment the processed_items counter
            self.processed_items += 1

            if item_text in self.ps3iso_list:
                self.downloadps3isozip(item_text, f"{self.processed_items}/{self.total_items}", operation)
            else:
                self.downloadps3psnzip(item_text, f"{self.processed_items}/{self.total_items}", operation)

    def downloadhelper(self, selected_iso, queue_position, operation, url):
        # URL-encode the selected_iso
        selected_iso_encoded = urllib.parse.quote(selected_iso)
        
        # Load the user's settings
        settings = QSettings('./myrientDownloaderGUI.ini', QSettings.IniFormat)
        ps3dec_binary = settings.value('ps3dec_binary', '')
        splitps3iso_binary = settings.value('splitps3iso_binary', '')

        # Compute base_name from selected_iso
        base_name = os.path.splitext(selected_iso)[0]

        # Check if the selected ISO already exists
        if not os.path.isfile(base_name):
            # Download the selected ISO
            self.output_window.append(f"({queue_position}) Download started for {base_name}...\n")
            self.progress_bar.reset()  # Reset the progress bar to 0
            self.download_thread = DownloadThread(f"{url}/{selected_iso_encoded}", selected_iso)
            self.download_thread.progress_signal.connect(self.progress_bar.setValue)
            self.download_thread.speed_signal.connect(self.download_speed_label.setText)
            self.download_thread.eta_signal.connect(self.download_eta_label.setText)


            # Create a QEventLoop
            loop = QEventLoop()
            self.download_thread.finished.connect(loop.quit)

            # Start the thread and the event loop
            self.download_thread.start()
            loop.exec_()


    def downloadps3isozip(self, selected_iso, queue_position, operation):
        url = "https://myrient.erista.me/files/Redump/Sony - PlayStation 3"
        base_name = os.path.splitext(selected_iso)[0]
        self.downloadhelper(selected_iso, queue_position, operation, url)

        # Unzip the ISO and delete the ZIP file
        unzip_file(selected_iso, '.', self.output_window)
        os.remove(selected_iso)

        # Check if the corresponding dkey file already exists
        if not os.path.isfile(f"{os.path.splitext(selected_iso)[0]}.dkey"):
            # Download the corresponding dkey file
            self.output_window.append(f"({queue_position}) Getting dkey for {base_name}...")
            self.progress_bar.reset()  # Reset the progress bar to 0
            self.download_thread = DownloadThread(f"https://myrient.erista.me/files/Redump/Sony - PlayStation 3 - Disc Keys TXT/{os.path.splitext(selected_iso)[0]}.zip", f"{os.path.splitext(selected_iso)[0]}.zip")
            self.download_thread.progress_signal.connect(self.progress_bar.setValue)

            # Create a QEventLoop
            loop = QEventLoop()
            self.download_thread.finished.connect(loop.quit)

            # Start the thread and the event loop
            self.download_thread.start()
            loop.exec_()
                
            # Unzip the dkey file and delete the ZIP file
            with zipfile.ZipFile(f"{os.path.splitext(selected_iso)[0]}.zip", 'r') as zip_ref:
                zip_ref.extractall('.')
            os.remove(f"{os.path.splitext(selected_iso)[0]}.zip")

        # Read the first 32 characters of the .dkey file
        with open(f"{os.path.splitext(selected_iso)[0]}.dkey", 'r') as file:
            key = file.read(32)

        # Run the PS3Dec command if decryption is enabled
        self.output_window.append(f"({queue_position}) Decrypting ISO for {base_name}...")
        if 'Decrypt' in operation:
            if platform.system() == 'Windows':
                thread_count = multiprocessing.cpu_count() // 2
                run_command([f"{self.ps3dec_binary}", "--iso", f"{os.path.splitext(selected_iso)[0]}.iso", "--dk", key, "--tc", str(thread_count)],  self.output_window)
                # Rename the decrypted ISO file to remove '_decrypted'
                os.rename(f"{os.path.splitext(selected_iso)[0]}.iso", f"{os.path.splitext(selected_iso)[0]}.iso.enc")
                os.rename(f"{os.path.splitext(selected_iso)[0]}.iso_decrypted.iso", f"{os.path.splitext(selected_iso)[0]}.iso")
            else:
                run_command([self.ps3dec_binary, 'd', 'key', key, f"{os.path.splitext(selected_iso)[0]}.iso"],  self.output_window)
                # Rename the original ISO file to .iso.enc
                os.rename(f"{os.path.splitext(selected_iso)[0]}.iso", f"{os.path.splitext(selected_iso)[0]}.iso.enc")
                os.rename(f"{os.path.splitext(selected_iso)[0]}.iso.dec", f"{os.path.splitext(selected_iso)[0]}.iso")

        # Run splitps3iso on the processed .iso file if splitting is enabled
        self.output_window.append(f"({queue_position}) Splitting ISO for {base_name}...")
        if 'Split' in operation:
            run_command([self.splitps3iso_binary, f"{os.path.splitext(selected_iso)[0]}.iso"],  self.output_window)
            self.output_window.append(f"({queue_position}) splitps3iso completed for {base_name}")
            # Delete the .iso file if the 'Keep unsplit decrypted ISO' checkbox is unchecked
            if not self.keep_unsplit_dec_checkbox.isChecked():
                os.remove(f"{os.path.splitext(selected_iso)[0]}.iso")

        # Delete the .dkey file if the 'Keep dkey file' checkbox is unchecked
        if not self.keep_dkey_checkbox.isChecked():
            os.remove(f"{os.path.splitext(selected_iso)[0]}.dkey")

        # Delete the .iso.enc file if the checkbox is unchecked
        if not self.keep_enc_checkbox.isChecked():
            os.remove(f"{os.path.splitext(selected_iso)[0]}.iso.enc")

        self.queue_list.takeItem(0)

        self.output_window.append(f"({queue_position}) {base_name} ready!")

        # If there are more items in the queue, start the next download
        if self.queue_list.count() > 0:
            self.start_download()

        # Re-enable the buttons
        self.settings_button.setEnabled(True)
        self.add_to_queue_button.setEnabled(True)
        self.remove_from_queue_button.setEnabled(True)
        self.operation_dropdown.setEnabled(True)
        self.keep_dkey_checkbox.setEnabled(True)
        self.keep_enc_checkbox.setEnabled(True)
        self.keep_unsplit_dec_checkbox.setEnabled(True)
        self.keep_dkey_checkbox.setEnabled(True)
        self.start_button.setEnabled(True)

    def downloadps3psnzip(self, selected_iso, queue_position, operation):
        url = "https://download.mtcontent.rs/files/No-Intro/Sony%20-%20PlayStation%203%20(PSN)%20(Content)"
        base_name = os.path.splitext(selected_iso)[0]
        self.downloadhelper(selected_iso, queue_position, operation, url)

        # Unzip the ISO and delete the ZIP file
        extracted_files = unzip_file(selected_iso, '.', self.output_window)
        os.remove(selected_iso)

        # Rename the extracted .pkg and .rap files to the original name of the zip file
        for file in extracted_files:
            if file.endswith('.pkg') or file.endswith('.rap'):
                os.rename(file, f"{os.path.splitext(selected_iso)[0]}{os.path.splitext(file)[1]}")

        self.queue_list.takeItem(0)

        self.output_window.append(f"({queue_position}) {base_name} ready!")

        # If there are more items in the queue, start the next download
        if self.queue_list.count() > 0:
            self.start_download()

        # Re-enable the buttons
        self.settings_button.setEnabled(True)
        self.add_to_queue_button.setEnabled(True)
        self.remove_from_queue_button.setEnabled(True)
        self.operation_dropdown.setEnabled(True)
        self.keep_dkey_checkbox.setEnabled(True)
        self.keep_enc_checkbox.setEnabled(True)
        self.keep_unsplit_dec_checkbox.setEnabled(True)
        self.keep_dkey_checkbox.setEnabled(True)
        self.start_button.setEnabled(True)

    def add_to_queue(self):
        selected_items = self.result_list.currentWidget().selectedItems()
        for item in selected_items:
            item_text = item.text()
            # Check if the item already exists in the queue
            if not any(item_text == self.queue_list.item(i).text() for i in range(self.queue_list.count())):
                self.queue_list.addItem(item_text)

    def update_add_to_queue_button(self):
        self.add_to_queue_button.setEnabled(bool(self.result_list.currentWidget().selectedItems()))

    def update_remove_from_queue_button(self):
        # Enable the 'Remove from Queue' button if one or more items are selected in the queue list
        self.remove_from_queue_button.setEnabled(bool(self.queue_list.selectedItems()))

    def remove_from_queue(self):
        selected_items = self.queue_list.selectedItems()
        for item in selected_items:
            self.queue_list.takeItem(self.queue_list.row(item))

    def stop_process(self):
        # TODO: Implement the logic to stop the current process
        pass

    def set_ps3iso_list(self, ps3iso_list):
        self.ps3iso_list = ps3iso_list
        self.result_list.widget(0).clear()
        self.result_list.widget(0).addItems(self.ps3iso_list)

    def set_psn_list(self, psn_list):
        self.psn_list = psn_list
        self.result_list.widget(1).clear()
        self.result_list.widget(1).addItems(self.psn_list)

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

    def download_splitps3iso(self, splitps3isoButton, textbox):
        # Create a new directory called 'workdir'
        os.makedirs('workdir', exist_ok=True)
        os.chdir('workdir')

        if platform.system() == 'Windows':
            url = "https://github.com/bucanero/ps3iso-utils/releases/download/277db7de/ps3iso-277db7de-Win64.zip"
        elif platform.system() == 'Linux':
            url = "https://github.com/bucanero/ps3iso-utils/releases/download/277db7de/ps3iso-277db7de-ubuntu.zip"
        elif platform.system() == 'Darwin':
            url = "https://github.com/bucanero/ps3iso-utils/releases/download/277db7de/ps3iso-277db7de-macos.zip"

        urllib.request.urlretrieve(url, "ps3isotools.zip")
        with zipfile.ZipFile("ps3isotools.zip", 'r') as zip_ref:
            zip_ref.extractall('.')
        os.remove("ps3isotools.zip")  # delete the zip file

        # Extract the tar.gz file
        with tarfile.open("build.tar.gz", 'r:gz') as tar_ref:
            tar_ref.extractall('.')
        os.remove("build.tar.gz")  # delete the tar.gz file

        # Rename the splitps3iso directory
        os.rename("splitps3iso", "splitps3iso-dir")

        # Move the splitps3iso binary
        binary_name = "splitps3iso.exe" if platform.system() == 'Windows' else "splitps3iso"
        shutil.move(f"splitps3iso-dir/{binary_name}", "..")

        # Change back to the original directory
        os.chdir('..')

        # Set binary path
        self.splitps3iso_binary = os.path.join(os.getcwd(), binary_name)
        self.settings.setValue('splitps3iso_binary', self.splitps3iso_binary)

        # Delete the 'workdir' directory
        shutil.rmtree('workdir')

        # Update the button
        splitps3isoButton.setText('splitps3iso downloaded! ✅')
        splitps3isoButton.setEnabled(False)
        self.splitps3iso_binary = './splitps3iso' if sys.platform != "Windows" else './splitps3iso.exe'
        self.settings.setValue('splitps3iso_binary', self.splitps3iso_binary)
        textbox.setText(self.splitps3iso_binary)

    def settings_welcome_dialog(self, title, close_button_text, add_iso_list_section=False, welcome_text=None):
        dialog = QDialog()
        dialog.setWindowTitle(title)
        vbox = QVBoxLayout(dialog)

        # Adds welcome text if provided
        if welcome_text is not None:
            welcome_label = QLabel(welcome_text)
            vbox.addWidget(welcome_label)

        def create_binary_section(name, download_button, select_button, path_textbox):
            section_label = QLabel(name)
            vbox.addWidget(section_label)

            vbox_buttons = QHBoxLayout()
            vbox_buttons.addWidget(download_button)
            vbox_buttons.addWidget(select_button)
            vbox.addLayout(vbox_buttons)

            vbox.addWidget(path_textbox)

        # PS3Dec section
        ps3decButton = QPushButton('Download PS3Dec')
        ps3decSelectButton = QPushButton('Choose PS3Dec Binary')
        ps3decPathTextbox = QLineEdit(self.ps3dec_binary)  # Initialize with existing path if available

        # Disable the button and change the text if the user is not on Windows
        if platform.system() != 'Windows':
            ps3decButton.setEnabled(False)
            ps3decButton.setText("Can't get prebuilt PS3Dec on Linux")

        # Check if ps3dec is detected
        if os.path.isfile("ps3dec") or os.path.isfile("ps3dec.exe"):
            ps3decButton.setText('PS3Dec detected! ✅')
            ps3decButton.setEnabled(False)

        # Connect download button to the download_ps3dec method
        ps3decButton.clicked.connect(lambda: self.download_ps3dec(ps3decButton, ps3decPathTextbox))

        # Connect select button to the open_file_dialog_ps3dec method
        ps3decSelectButton.clicked.connect(lambda: self.open_file_dialog_ps3dec(ps3decPathTextbox))

        create_binary_section("PS3Dec:", ps3decButton, ps3decSelectButton, ps3decPathTextbox)

        # splitps3iso section
        splitps3isoButton = QPushButton('Download splitps3iso')
        splitps3isoSelectButton = QPushButton('Choose splitps3iso Binary')
        splitps3isoPathTextbox = QLineEdit(self.splitps3iso_binary)  # Initialize with existing path if available

        # Check if splitps3iso is detected
        if os.path.isfile("splitps3iso") or os.path.isfile("splitps3iso.exe"):
            splitps3isoButton.setText('splitps3iso detected! ✅')
            splitps3isoButton.setEnabled(False)

        # Connect download button to the download_splitps3iso method
        splitps3isoButton.clicked.connect(lambda: self.download_splitps3iso(splitps3isoButton, splitps3isoPathTextbox))

        # Connect select button to the open_file_dialog_splitps3iso method
        splitps3isoSelectButton.clicked.connect(lambda: self.open_file_dialog_splitps3iso(splitps3isoPathTextbox))

        create_binary_section("splitps3iso:", splitps3isoButton, splitps3isoSelectButton, splitps3isoPathTextbox)

        # ISO List section
        if add_iso_list_section:
            iso_list_button = QPushButton('Update ISO List')
            iso_list_button.clicked.connect(self.update_iso_list)
            vbox.addWidget(iso_list_button)

        # Close button
        closeButton = QPushButton(close_button_text)
        closeButton.clicked.connect(dialog.close)
        vbox.addWidget(closeButton)

        # Show the dialog
        dialog.exec_()

    def open_settings(self):
        self.settings_welcome_dialog("Tools", "Close", add_iso_list_section=True)

    def first_startup(self):
        welcome_text = "Welcome! The script can attempt to grab PS3Dec and splitps3iso automatically or you can set them manually"
        self.settings_welcome_dialog("Welcome!", "Continue", welcome_text=welcome_text)

    def update_iso_list(self):
        self.get_iso_list_thread.start()

    def open_file_dialog_ps3dec(self, textbox):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        fileName, _ = QFileDialog.getOpenFileName(self, "Select PS3Dec binary", "", "All Files (*);;Executable Files (*.exe)", options=options)
        if fileName:
            self.ps3dec_binary = fileName
            self.settings.setValue('ps3dec_binary', fileName)
            textbox.setText(fileName)  # Update the textbox with the new path

    def open_file_dialog_splitps3iso(self, textbox):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        fileName, _ = QFileDialog.getOpenFileName(self, "Select splitps3iso binary", "", "All Files (*);;Executable Files (*.exe)", options=options)
        if fileName:
            self.splitps3iso_binary = fileName
            self.settings.setValue('splitps3iso_binary', fileName)
            textbox.setText(fileName)  # Update the textbox with the new path

    def update_results(self):
        # Get the search term from the search box
        search_term = self.search_box.text().lower()

        # Determine which list to search based on the currently selected tab
        if self.result_list.currentIndex() == 0:
            list_to_search = self.ps3iso_list
        else:
            list_to_search = self.psn_list

        # Filter the list based on the search term
        filtered_list = [item for item in list_to_search if search_term in item.lower()]

        # Clear the current list widget and add the filtered items
        current_list_widget = self.result_list.currentWidget()
        current_list_widget.clear()
        current_list_widget.addItems(filtered_list)


    def update_checkboxes(self):
        # Show or hide the 'Keep unsplit decrypted ISO' checkbox based on the selected operation
        if self.operation_dropdown.currentText() == 'Decrypt and Split':
            self.keep_unsplit_dec_checkbox.show()
            self.keep_dkey_checkbox.setChecked(False)
        else:
            self.keep_unsplit_dec_checkbox.hide()

        # Show or hide the 'Keep encrypted ISO' checkbox based on the selected operation
        if self.operation_dropdown.currentText() == 'Download Only':
            self.keep_enc_checkbox.hide()
            self.keep_dkey_checkbox.setChecked(True)
        else:
            self.keep_dkey_checkbox.setChecked(False)
            self.keep_enc_checkbox.show()

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        ex = GUIDownloader()
        sys.exit(app.exec_())
    except Exception:
        print(traceback.format_exc())
