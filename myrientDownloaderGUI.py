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
import glob
import multiprocessing
from urllib.parse import unquote
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QComboBox, QLineEdit, QListWidget, QLabel, QCheckBox, QTextEdit, QFileDialog, QMessageBox, QDialog, QHBoxLayout
from PyQt5.QtCore import QSettings
from tqdm import tqdm

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

# Function to run a command and check its success
def run_command(command, output_window):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
    
    # If on Windows, send a newline character to ps3dec's standard input
    if platform.system() == 'Windows':
        process.stdin.write(b'\n')
        process.stdin.flush()
        
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


class GUIDownloader(QWidget):
    def __init__(self):
        super().__init__()

        # Load the user's settings
        self.settings = QSettings('hadobedo', 'myrientDownloaderGUI')
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
            # If not, open the settings dialog
            self.open_settings()

        # Get list of ISOs from the HTTPS directory
        response = requests.get("https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%203/")
        soup = BeautifulSoup(response.text, 'html.parser')
        self.iso_list = [unquote(link.get('href')) for link in soup.find_all('a') if link.get('href').endswith('.zip')]

        self.initUI()


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


    def initUI(self):
        vbox = QVBoxLayout()

        # Create a settings button
        self.settings_button = QPushButton('Settings', self)
        self.settings_button.clicked.connect(self.open_settings)
        vbox.addWidget(self.settings_button)

        # Create a search box
        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText('Search...')
        self.search_box.textChanged.connect(self.update_results)
        vbox.addWidget(self.search_box)

        # Create a list for results
        self.result_list = QListWidget(self)
        self.result_list.addItems(self.iso_list) 
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

        # Create an output window
        self.output_window = OutputWindow(self)
        vbox.addWidget(self.output_window)

        self.setLayout(vbox)

        self.setWindowTitle('Myrient PS3 Downloader')
        self.resize(800, 600)
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

    def open_settings(self):
        dialog = QDialog()
        dialog.setWindowTitle("Tools")
        vbox = QVBoxLayout(dialog)

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

        # Close button
        closeButton = QPushButton('Continue')
        closeButton.clicked.connect(dialog.close)
        vbox.addWidget(closeButton)

        # Show the dialog
        dialog.exec_()

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




    def start_process(self):
        # Check if both binaries are specified
        if not self.ps3dec_binary or not self.splitps3iso_binary:
            # Create a popup telling the user which binary/binaries are missing
            missing_binaries = []
            if not self.ps3dec_binary:
                missing_binaries.append('PS3Dec')
            if not self.splitps3iso_binary:
                missing_binaries.append('splitps3iso')
            QMessageBox.warning(self, 'Missing Binaries', f"The following binary/binaries are missing: {', '.join(missing_binaries)}")

            # Open the settings window
            self.open_settings()

            return  # exit the method

        # Get the selected ISO from the result list
        selected_iso = self.result_list.currentItem().text()

        # Get the selected operation from the dropdown menu
        operation = self.operation_dropdown.currentText()

        # Use the stored paths for the binaries
        ps3dec_binary = self.ps3dec_binary
        splitps3iso_binary = self.splitps3iso_binary

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
            if platform.system() == 'Windows':
                thread_count = multiprocessing.cpu_count() // 2
                run_command([f"{ps3dec_binary}", "--iso", f"{os.path.splitext(selected_iso)[0]}.iso", "--dk", key, "--tc", str(thread_count)], self.output_window)
                # Rename the decrypted ISO file to remove '_decrypted'
                os.rename(f"{os.path.splitext(selected_iso)[0]}.iso", f"{os.path.splitext(selected_iso)[0]}.iso.enc")
                os.rename(f"{os.path.splitext(selected_iso)[0]}.iso_decrypted.iso", f"{os.path.splitext(selected_iso)[0]}.iso")
            else:
                run_command([ps3dec_binary, 'd', 'key', key, f"{os.path.splitext(selected_iso)[0]}.iso"], self.output_window)
                # Rename the original ISO file to .iso.enc
                os.rename(f"{os.path.splitext(selected_iso)[0]}.iso", f"{os.path.splitext(selected_iso)[0]}.iso.enc")
                os.rename(f"{os.path.splitext(selected_iso)[0]}.iso.dec", f"{os.path.splitext(selected_iso)[0]}.iso")


        # Run splitps3iso on the processed .iso file if splitting is enabled
        if 'Split' in operation:
            run_command([splitps3iso_binary, f"{os.path.splitext(selected_iso)[0]}.iso"], self.output_window)
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
    try:
        app = QApplication(sys.argv)
        ex = GUIDownloader()
        sys.exit(app.exec_())
    except Exception:
        print(traceback.format_exc())
