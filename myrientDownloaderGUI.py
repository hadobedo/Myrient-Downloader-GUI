#!/usr/bin/env python3
import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QFontDatabase

from gui.main_window import GUIDownloader

# Set Qt attributes before creating QApplication
QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# Capture early output
class OutputBuffer:
    def __init__(self):
        self.buffer = []
        self.orig_stdout = sys.stdout
        self.orig_stderr = sys.stderr
    
    def write(self, text):
        self.buffer.append(text)
        # Still write to original stdout for early debugging
        self.orig_stdout.write(text)
    
    def flush(self):
        pass
    
    def transfer_to_output(self, output_window):
        for text in self.buffer:
            output_window.append_text(text)
        self.buffer = []

def main():
    """Main entry point for the application."""
    
    # Create output buffer to capture early messages
    buffer = OutputBuffer()
    sys.stdout = buffer
    sys.stderr = buffer
    
    # Detect Wayland environment and apply necessary fixes
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        print("Wayland session detected, applying compatibility settings")
        # Force Qt to use x11 platform plugin for better compatibility
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        # Disable high DPI scaling which can cause rendering issues in dialogs
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
    
    # Initialize application
    app = QApplication(sys.argv)
    
    # Create main window
    ex = GUIDownloader()
    
    # Transfer captured output to the application's output window
    buffer.transfer_to_output(ex.output_window)
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
