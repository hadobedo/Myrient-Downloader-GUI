#!/usr/bin/env python3
import sys
import os
import platform
import traceback
from traceback import format_exception

# Import Qt core module first and set attributes before any other Qt imports
from PyQt5.QtCore import Qt, QCoreApplication, QSettings

# Set Qt attributes before creating QApplication or importing other Qt modules
QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# Now import other Qt modules and application modules
from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog, QStyleFactory
from PyQt5.QtGui import QFontDatabase, QPalette, QColor

from gui.main_window import GUIDownloader
from core.settings import SettingsManager

# Global settings for theme
app_settings = None

def detect_system_dark_mode():
    """Simple detection of system dark mode preference."""
    try:
        if platform.system() == 'Windows':
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                              r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
                return value == 0  # 0 = dark, 1 = light
        elif platform.system() == 'Darwin':
            import subprocess
            result = subprocess.run(['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                                  capture_output=True, text=True, timeout=5)
            return result.stdout.strip().lower() == 'dark'
        elif platform.system() == 'Linux':
            # Simple check for common dark themes
            gtk_theme = os.environ.get('GTK_THEME', '').lower()
            return 'dark' in gtk_theme
    except Exception:
        pass
    return False

def apply_theme(app):
    """Apply theme using Qt's built-in system with user preference."""
    global app_settings
    app_settings = QSettings('./config/myrientDownloaderGUI.ini', QSettings.IniFormat)
    
    # Get user preference: 'auto', 'light', 'dark', 'system' - default to 'dark'
    theme_preference = app_settings.value('appearance/theme', 'dark')
    
    if theme_preference == 'dark':
        use_dark = True
    elif theme_preference == 'light':
        use_dark = False
    elif theme_preference == 'system':
        # Use Qt's default system theme
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(app.style().standardPalette())
        app.setStyleSheet("")
        return False
    else:  # 'auto' - follow system
        use_dark = detect_system_dark_mode()
    
    if use_dark:
        # Apply simple dark theme using Qt's palette system
        app.setStyle(QStyleFactory.create("Fusion"))
        palette = QPalette()
        
        # Use colors with good contrast ratios
        palette.setColor(QPalette.Window, QColor(45, 45, 45))
        palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
        palette.setColor(QPalette.Base, QColor(35, 35, 35))
        palette.setColor(QPalette.AlternateBase, QColor(60, 60, 60))
        palette.setColor(QPalette.ToolTipBase, QColor(35, 35, 35))
        palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
        palette.setColor(QPalette.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.Button, QColor(60, 60, 60))
        palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        
        app.setPalette(palette)
        
        # Minimal stylesheet for better readability
        app.setStyleSheet("""
            QToolTip {
                color: #ffffff;
                background-color: #353535;
                border: 1px solid #767676;
            }
        """)
    else:
        # Use Qt's default light theme
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(app.style().standardPalette())
        app.setStyleSheet("")
    
    return use_dark

def show_styled_message_box(icon, title, text, parent=None):
    """Show a message box with basic styling."""
    msg_box = QMessageBox(parent)
    msg_box.setIcon(icon)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    return msg_box.exec_()

def is_dark_mode():
    """Check if dark mode is currently active (for backward compatibility)."""
    global app_settings
    if app_settings:
        theme_preference = app_settings.value('appearance/theme', 'dark')
        if theme_preference == 'dark':
            return True
        elif theme_preference == 'light':
            return False
        elif theme_preference == 'auto':
            return detect_system_dark_mode()
    return True  # Default to dark mode

def style_dialog_for_theme(dialog):
    """Apply minimal theme styling to dialogs."""
    # Qt handles this automatically with the palette
    return dialog

def validate_startup_prerequisites():
    """Validate startup prerequisites using the new settings-based system."""
    try:
        from core.settings import SettingsManager
        settings_manager = SettingsManager()
        return settings_manager.validate_startup_prerequisites()
    except Exception as e:
        print(f"Error during startup prerequisite validation: {str(e)}")
        return True  # Continue on validation errors


def show_error_dialog(message, details=None):
    """Show an error dialog with optional details."""
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Critical)
    msg_box.setWindowTitle("Error")
    msg_box.setText(message)
    if details:
        msg_box.setDetailedText(details)
    msg_box.exec_()

def main():
    """Main entry point for the application."""
    try:
        # Set up global exception handler
        def global_except_hook(exc_type, exc_value, exc_traceback):
            error_details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            print(error_details)  # Print to console/log
            if QApplication.instance():
                show_error_dialog("An unexpected error occurred", error_details)
            sys.exit(1)
        
        sys.excepthook = global_except_hook
        
        # Initialize Qt application first
        app = QApplication(sys.argv)
        
        # Apply theme settings
        is_dark = apply_theme(app)
        
        # Detect Wayland and apply fixes
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            os.environ["QT_QPA_PLATFORM"] = "xcb"
            os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
        
        # Run startup validation
        validate_startup_prerequisites()
        
        # Create and show main window
        window = GUIDownloader()
        window.show()
        
        # Enter Qt event loop
        return app.exec_()
    except Exception as e:
        error_details = "".join(traceback.format_exception(*sys.exc_info()))
        print(f"Fatal error during startup: {error_details}")
        if QApplication.instance():
            show_error_dialog(
                "Failed to start application",
                f"Error: {str(e)}\n\nDetails:\n{error_details}"
            )
        return 1

if __name__ == '__main__':
    result = main()
    sys.exit(result)
