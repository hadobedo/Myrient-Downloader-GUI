import os
import subprocess
import zipfile
import sys
import requests
from urllib.parse import unquote
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QComboBox, QLineEdit, QListWidget, QLabel, QCheckBox, QTextEdit
from PyQt5.QtCore import Qt
from tqdm import tqdm

# Function to run a command and check its success
def run_command(command, output_window):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in iter(process.stdout.readline, b''):
        output_window.append('<pre>' + line.decode() + '</pre>')
        QApplication.processEvents()
    process.stdout.close()
    return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)

# Function to download a file over HTTPS with progress bar
def download_file(url, filename):
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    progress_bar = tqdm(total=total_size, unit='iB', unit_scale=True)
    with open(filename, 'wb') as file:
        for chunk in response.iter_content(chunk_size=8192):
            file.write(chunk)
            progress_bar.update(len(chunk))
    progress_bar.close()

class OutputWindow(QTextEdit):
    def __init__(self, *args, **kwargs):
        super(OutputWindow, self).__init__(*args, **kwargs)
        sys.stdout = self
        sys.stderr = self
        self.setReadOnly(True)

    def write(self, text):
        self.append('<pre>' + text + '</pre>')
        QApplication.processEvents()

    def flush(self):
        pass

class MyApp(QWidget):
    def __init__(self):
        super().__init__()

        # Get list of ISOs from the HTTPS directory
        response = requests.get("https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%203/")
        soup = BeautifulSoup(response.text, 'html.parser')
        self.iso_list = [unquote(link.get('href')) for link in soup.find_all('a') if link.get('href').endswith('.zip')]

        self.initUI()

    def initUI(self):
        vbox = QVBoxLayout()

        # Create a search box
        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText('Search...')
        self.search_box.textChanged.connect(self.update_results)
        vbox.addWidget(self.search_box)

        # Create a list for results
        self.result_list = QListWidget(self)
        vbox.addWidget(self.result_list)

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

        # Create a button to start the process
        self.start_button = QPushButton('Start', self)
        self.start_button.clicked.connect(self.start_process)
        vbox.addWidget(self.start_button)

        # Create a button to stop the process
        self.stop_button = QPushButton('Stop', self)
        self.stop_button.clicked.connect(self.stop_process)
        vbox.addWidget(self.stop_button)

        # Create an output window
        self.output_window = OutputWindow(self)
        vbox.addWidget(self.output_window)

        self.setLayout(vbox)

        self.setWindowTitle('Myrient PS3 Downloader')
        self.show()

    def update_results(self):
        # Get the search term from the search box
        search_term = self.search_box.text()

        # Filter the ISO list based on the search term
        filtered_iso_list = [iso for iso in self.iso_list if search_term.lower() in iso.lower()]

        # Update the result list
        self.result_list.clear()
        self.result_list.addItems(filtered_iso_list)

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


    def start_process(self):
        # Get the selected ISO from the result list
        selected_iso = self.result_list.currentItem().text()

        # Get the selected operation from the dropdown menu
        operation = self.operation_dropdown.currentText()

        # Check if the selected ISO already exists
        if not os.path.isfile(os.path.splitext(selected_iso)[0]):
            # Download the selected ISO
            download_file(f"https://myrient.erista.me/files/Redump/Sony - PlayStation 3/{selected_iso}", selected_iso)

            # Unzip the ISO and delete the ZIP file
            with zipfile.ZipFile(selected_iso, 'r') as zip_ref:
                zip_ref.extractall('.')
            os.remove(selected_iso)

        # Check if the corresponding dkey file already exists
        if not os.path.isfile(f"{os.path.splitext(selected_iso)[0]}.dkey"):
            # Download the corresponding dkey file
            download_file(f"https://myrient.erista.me/files/Redump/Sony - PlayStation 3 - Disc Keys TXT/{os.path.splitext(selected_iso)[0]}.zip", f"{os.path.splitext(selected_iso)[0]}.zip")

            # Unzip the dkey file and delete the ZIP file
            with zipfile.ZipFile(f"{os.path.splitext(selected_iso)[0]}.zip", 'r') as zip_ref:
                zip_ref.extractall('.')
            os.remove(f"{os.path.splitext(selected_iso)[0]}.zip")

        # Read the first 32 characters of the .dkey file
        with open(f"{os.path.splitext(selected_iso)[0]}.dkey", 'r') as file:
            key = file.read(32)

        # Run the PS3Dec command if decryption is enabled
        if 'Decrypt' in operation:
            run_command(['PS3Dec', 'd', 'key', key, f"{os.path.splitext(selected_iso)[0]}.iso"], self.output_window)
            # Rename the original ISO file to .iso.enc
            os.rename(f"{os.path.splitext(selected_iso)[0]}.iso", f"{os.path.splitext(selected_iso)[0]}.iso.enc")
            os.rename(f"{os.path.splitext(selected_iso)[0]}.iso.dec", f"{os.path.splitext(selected_iso)[0]}.iso")

        # Run splitps3iso on the processed .iso file if splitting is enabled
        if 'Split' in operation:
            run_command(['splitps3iso', f"{os.path.splitext(selected_iso)[0]}.iso"], self.output_window)
            print(f"splitps3iso completed for {os.path.splitext(selected_iso)[0]}")
            # Delete the .iso file if the 'Keep unsplit decrypted ISO' checkbox is unchecked
            if not self.keep_unsplit_dec_checkbox.isChecked():
                os.remove(f"{os.path.splitext(selected_iso)[0]}.iso")

        # Delete the .dkey file if the 'Keep dkey file' checkbox is unchecked
        if not self.keep_dkey_checkbox.isChecked():
            os.remove(f"{os.path.splitext(selected_iso)[0]}.dkey")

        # Delete the .iso.enc file if the checkbox is unchecked
        if not self.keep_enc_checkbox.isChecked():
            os.remove(f"{os.path.splitext(selected_iso)[0]}.iso.enc")

    def stop_process(self):
        # TODO: Implement the logic to stop the current process
        pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MyApp()
    sys.exit(app.exec_())
