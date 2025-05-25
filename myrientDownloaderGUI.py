#!/usr/bin/env python3
import sys
import os
import platform
from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog, QStyleFactory
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QFontDatabase, QPalette, QColor

from gui.main_window import GUIDownloader
from core.settings import SettingsManager
from gui.ps3dec_dialog import PS3DecDownloadDialog

# Set Qt attributes before creating QApplication
QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# Global variable to track dark mode state
is_dark_mode = False

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

def style_dialog_for_dark_mode(dialog):
    """Apply dark mode styling to a dialog if dark mode is active."""
    global is_dark_mode
    if not is_dark_mode:
        return dialog
        
    # Apply dark styling to the dialog
    dialog.setStyleSheet("""
        QMessageBox {
            background-color: #2d2d2d;
            color: #ffffff;
        }
        QLabel {
            color: #ffffff;
        }
        QPushButton {
            background-color: #3c3c3c;
            color: #ffffff;
            border: 1px solid #767676;
            padding: 5px;
            border-radius: 2px;
        }
        QPushButton:hover {
            background-color: #4c4c4c;
        }
        QPushButton:pressed {
            background-color: #2a82da;
        }
    """)
    return dialog
    
def show_styled_message_box(icon, title, text, parent=None):
    """Show a message box with proper styling based on system theme."""
    msg_box = QMessageBox(parent)
    msg_box.setIcon(icon)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    style_dialog_for_dark_mode(msg_box)
    return msg_box.exec_()

def check_ps3dec(app):
    """Check if PS3Dec is available and prompt to download if not."""
    if platform.system() != 'Windows':
        return True
    
    settings_manager = SettingsManager()
    
    # Check if PS3Dec is available
    if settings_manager.ps3dec_binary and os.path.isfile(settings_manager.ps3dec_binary):
        return True
    
    # PS3Dec not found, show dialog
    dialog = PS3DecDownloadDialog()
    style_dialog_for_dark_mode(dialog)
    result = dialog.exec_()
    
    if result == QDialog.Accepted:
        # User clicked download
        try:
            if settings_manager.download_ps3dec():
                # Use styled message box
                show_styled_message_box(
                    QMessageBox.Information, 
                    "Download Complete", 
                    "PS3Dec was downloaded successfully."
                )
                return True
            else:
                # Use styled message box
                show_styled_message_box(
                    QMessageBox.Critical, 
                    "Download Failed", 
                    "Failed to download PS3Dec. Please try again later."
                )
                return True  # Continue even if download failed
        except Exception as e:
            # Use styled message box
            show_styled_message_box(
                QMessageBox.Critical, 
                "Download Error", 
                f"Error downloading PS3Dec: {str(e)}"
            )
            return True  # Continue despite error
    else:
        # User cancelled - just show a warning
        # Use styled message box
        show_styled_message_box(
            QMessageBox.Warning,
            "Limited Functionality",
            "PS3Dec was not downloaded. PS3 ISO decryption functionality will be limited."
        )
        return True  # Continue anyway when user cancels

def apply_system_theme(app):
    """Apply system theme (light or dark mode) to the application."""
    # Check if system is using dark mode
    global is_dark_mode
    dark_mode = False
    
    # Detect dark mode on different platforms
    if platform.system() == 'Windows':
        try:
            import winreg
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
            dark_mode = 1 - winreg.QueryValueEx(key, 'AppsUseLightTheme')[0]  # 0 is light, 1 is dark
        except Exception as e:
            dark_mode = False
    elif platform.system() == 'Darwin':  # macOS
        try:
            import subprocess
            cmd = 'defaults read -g AppleInterfaceStyle'
            result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
            dark_mode = result.stdout.strip() == 'Dark'
        except Exception as e:
            dark_mode = False
    elif platform.system() == 'Linux':
        # Try to detect dark mode on Linux
        # This is more complex due to the variety of desktop environments
        try:
            # Check various environment variables
            color_scheme = os.environ.get('GTK_THEME', '').lower()
            desktop_env = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
            
            if 'dark' in color_scheme:
                dark_mode = True
            elif desktop_env in ['gnome', 'unity']:
                import subprocess
                # Check GNOME color scheme
                cmd = 'gsettings get org.gnome.desktop.interface color-scheme'
                result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
                dark_mode = 'dark' in result.stdout.lower()
            elif desktop_env == 'kde':
                import subprocess
                # Check KDE color scheme
                cmd = 'kreadconfig5 --group Colors:Window --key BackgroundNormal'
                result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
                # If the background color is dark, assume dark mode
                color_value = result.stdout.strip()
                if color_value:
                    try:
                        r, g, b = map(int, color_value.split(','))
                        # Simple brightness calculation
                        brightness = (0.299 * r + 0.587 * g + 0.114 * b) / 255
                        dark_mode = brightness < 0.5
                    except:
                        dark_mode = False
        except Exception as e:
            dark_mode = False
    
    # Set global dark mode flag
    is_dark_mode = dark_mode
    
    if dark_mode:
        # Apply dark palette
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(35, 35, 35))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, QColor(25, 25, 25))
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        app.setPalette(palette)
        
        # Set stylesheet for additional elements
        app.setStyleSheet("""
            QToolTip { color: #ffffff; background-color: #2a2a2a; border: 1px solid #767676; }
            QListWidget { background-color: #2d2d2d; color: #ffffff; }
            QListView::item:selected { background-color: #2a82da; }
            QTabWidget::pane { border: 1px solid #767676; }
            QTabBar::tab { background-color: #3c3c3c; color: #ffffff; }
            QTabBar::tab:selected { background-color: #4c4c4c; }
            QLineEdit { background-color: #2d2d2d; color: #ffffff; border: 1px solid #767676; }
            QTextEdit { background-color: #2d2d2d; color: #ffffff; }
            QProgressBar { border: 1px solid #767676; background-color: #2d2d2d; }
            QProgressBar::chunk { background-color: #2a82da; }
            QCheckBox { color: #ffffff; }
            QRadioButton { color: #ffffff; }
            QGroupBox { color: #ffffff; border: 1px solid #767676; }
            QPushButton { background-color: #3c3c3c; color: #ffffff; border: 1px solid #767676; padding: 5px; }
            QPushButton:hover { background-color: #4c4c4c; }
            QPushButton:pressed { background-color: #2a82da; }
            
            /* Scrollbar styling for dark theme */
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 14px;
                margin: 15px 3px 15px 3px;
                border: 1px solid #2d2d2d;
                border-radius: 4px;
            }
            
            QScrollBar::handle:vertical {
                background-color: #555555;
                min-height: 30px;
                border-radius: 4px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: #666666;
            }
            
            QScrollBar::handle:vertical:pressed {
                background-color: #777777;
            }
            
            QScrollBar::sub-line:vertical {
                border: none;
                background-color: #3c3c3c;
                height: 15px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                subcontrol-position: top;
                subcontrol-origin: margin;
            }
            
            QScrollBar::add-line:vertical {
                border: none;
                background-color: #3c3c3c;
                height: 15px;
                border-bottom-left-radius: 4px;
                border-bottom-right-radius: 4px;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
            }
            
            QScrollBar::sub-line:vertical:hover,
            QScrollBar::add-line:vertical:hover {
                background-color: #4c4c4c;
            }
            
            QScrollBar::sub-line:vertical:pressed,
            QScrollBar::add-line:vertical:pressed {
                background-color: #2a82da;
            }
            
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                background: none;
            }
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background-color: #2d2d2d;
            }
            
            /* Horizontal scrollbar styling */
            QScrollBar:horizontal {
                background-color: #2d2d2d;
                height: 14px;
                margin: 3px 15px 3px 15px;
                border: 1px solid #2d2d2d;
                border-radius: 4px;
            }
            
            QScrollBar::handle:horizontal {
                background-color: #555555;
                min-width: 30px;
                border-radius: 4px;
            }
            
            QScrollBar::handle:horizontal:hover {
                background-color: #666666;
            }
            
            QScrollBar::handle:horizontal:pressed {
                background-color: #777777;
            }
            
            QScrollBar::sub-line:horizontal {
                border: none;
                background-color: #3c3c3c;
                width: 15px;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                subcontrol-position: left;
                subcontrol-origin: margin;
            }
            
            QScrollBar::add-line:horizontal {
                border: none;
                background-color: #3c3c3c;
                width: 15px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                subcontrol-position: right;
                subcontrol-origin: margin;
            }
            
            QScrollBar::sub-line:horizontal:hover,
            QScrollBar::add-line:horizontal:hover {
                background-color: #4c4c4c;
            }
            
            QScrollBar::sub-line:horizontal:pressed,
            QScrollBar::add-line:horizontal:pressed {
                background-color: #2a82da;
            }
            
            QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal {
                background: none;
            }
            
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background-color: #2d2d2d;
            }
        """)
    else:
        # Use default light theme
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(app.style().standardPalette())
        app.setStyleSheet("")

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
    
    # Apply system theme
    apply_system_theme(app)
    
    # Check for ps3dec on Windows
    check_ps3dec(app)  # We always continue now, regardless of the return value
    
    # Create main window
    ex = GUIDownloader()
    
    # Transfer captured output to the application's output window
    buffer.transfer_to_output(ex.output_window)
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
