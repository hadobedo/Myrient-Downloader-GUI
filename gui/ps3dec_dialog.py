import os
import platform
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QDialogButtonBox

class PS3DecDownloadDialog(QDialog):
    """Dialog to prompt the user to download PS3Dec."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PS3Dec Required")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Add explanation text
        message = QLabel(
            "PS3Dec is required to decrypt and extract PS3 ISOs.\n\n"
            "This tool was not found on your system. Would you like to download it now?\n\n"
            "Note: The download is approximately 233KB and will be saved to the application directory."
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        
        # Add buttons
        buttons = QDialogButtonBox()
        download_button = QPushButton("Download PS3Dec")
        cancel_button = QPushButton("Cancel")
        
        buttons.addButton(download_button, QDialogButtonBox.AcceptRole)
        buttons.addButton(cancel_button, QDialogButtonBox.RejectRole)
        
        layout.addWidget(buttons)
        self.setLayout(layout)
        
        # Connect signals
        download_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
