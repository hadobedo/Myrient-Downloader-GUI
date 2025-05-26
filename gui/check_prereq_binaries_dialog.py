import os
import platform
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QDialogButtonBox

class PrereqBinaryDialog(QDialog):
    """Dialog to prompt the user to download required binaries."""
    
    def __init__(self, binary_type, parent=None):
        super().__init__(parent)
        self.binary_type = binary_type
        
        # Configure dialog based on binary type
        if binary_type == "ps3dec":
            self.setWindowTitle("PS3Dec Required")
            message_text = (
                "PS3Dec is required to decrypt PS3 ISOs.\n\n"
                "This tool was not found on your system. Would you like to download it now?\n\n"
                "Note: The download is approximately 233KB and will be saved to the application directory."
            )
        elif binary_type == "extractps3iso":
            self.setWindowTitle("extractps3iso Required")
            message_text = (
                "extractps3iso is required to extract PS3 ISO contents.\n\n"
                "This tool was not found on your system. Would you like to download it now?\n\n"
                "Note: The download is approximately 600KB and will be saved to the application directory."
            )
        else:
            self.setWindowTitle("Binary Required")
            message_text = f"The {binary_type} tool is required but was not found on your system."
        
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Add explanation text
        message = QLabel(message_text)
        message.setWordWrap(True)
        layout.addWidget(message)
        
        # Add buttons
        buttons = QDialogButtonBox()
        download_button = QPushButton(f"Download {binary_type}")
        cancel_button = QPushButton("Cancel")
        
        buttons.addButton(download_button, QDialogButtonBox.AcceptRole)
        buttons.addButton(cancel_button, QDialogButtonBox.RejectRole)
        
        layout.addWidget(buttons)
        self.setLayout(layout)
        
        # Connect signals
        download_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
