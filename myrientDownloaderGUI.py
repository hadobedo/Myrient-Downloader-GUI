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
    """Enhanced detection of system dark mode preference, especially for Linux."""
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
            # Enhanced Linux dark mode detection
            
            # Check GTK theme preference
            gtk_theme = os.environ.get('GTK_THEME', '').lower()
            if 'dark' in gtk_theme:
                return True
            
            # Check gsettings for GNOME-based desktops
            try:
                import subprocess
                result = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.interface', 'gtk-theme'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and 'dark' in result.stdout.lower():
                    return True
                    
                # Also check for color scheme preference
                result = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.interface', 'color-scheme'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and 'dark' in result.stdout.lower():
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            
            # Check KDE plasma theme
            kde_config_dirs = [
                os.path.expanduser('~/.config/kdeglobals'),
                os.path.expanduser('~/.kde/share/config/kdeglobals'),
                os.path.expanduser('~/.kde4/share/config/kdeglobals')
            ]
            
            for config_file in kde_config_dirs:
                try:
                    if os.path.exists(config_file):
                        with open(config_file, 'r') as f:
                            content = f.read().lower()
                            if 'dark' in content or 'breezedark' in content:
                                return True
                except (OSError, IOError):
                    pass
            
            # Check environment variables that might indicate dark theme
            dark_indicators = [
                'dark' in os.environ.get('QT_STYLE_OVERRIDE', '').lower(),
                'dark' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower(),
                os.environ.get('KDE_SESSION_VERSION') and 'dark' in os.environ.get('KDEDIRS', '').lower()
            ]
            
            if any(dark_indicators):
                return True
                
    except Exception as e:
        print(f"Error detecting system dark mode: {e}")
    
    # Default to False for Linux if we can't detect
    return False

def apply_theme(app):
    """Apply theme using Qt's built-in system with user preference."""
    global app_settings
    
    # Migrate folders into MyrientDownloads if needed
    base_dir = './MyrientDownloads'
    config_dir = os.path.join(base_dir, 'config')
    
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, exist_ok=True)
        
    for folder in ['config', 'data', 'bin']:
        old_path = f'./{folder}'
        new_path = os.path.join(base_dir, folder)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            import shutil
            try:
                shutil.move(old_path, new_path)
                print(f"Migrated {folder}/ to MyrientDownloads/{folder}/")
            except Exception as e:
                print(f"Failed to migrate {folder}/ to MyrientDownloads: {e}")
                
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    
    app_settings = QSettings('./MyrientDownloads/config/myrientDownloaderGUI.ini', QSettings.IniFormat)
    
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
        
        # Use colors with good contrast ratios - improved for Linux/Wayland compatibility
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
        
        # Additional colors for better Wayland/Linux compatibility
        palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
        
        app.setPalette(palette)
        
        # Enhanced stylesheet for better Linux/Wayland compatibility
        app.setStyleSheet("""
            QToolTip {
                color: #ffffff;
                background-color: #353535;
                border: 1px solid #767676;
                padding: 3px;
                border-radius: 3px;
            }
            QGroupBox {
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 3px;
                margin-top: 0.5em;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #2d2d2d;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 6px 12px;
                margin-right: 1px;
            }
            QTabBar::tab:selected {
                background-color: #2d2d2d;
                border-bottom: 2px solid #42a5f5;
            }
            QTabBar::tab:hover:!selected {
                background-color: #484848;
            }
        """)
    else:
        # Use Qt's default light theme with some enhancements
        app.setStyle(QStyleFactory.create("Fusion"))
        palette = app.style().standardPalette()
        app.setPalette(palette)
        
        # Light theme enhancements
        app.setStyleSheet("""
            QGroupBox {
                border: 1px solid #c0c0c0;
                border-radius: 3px;
                margin-top: 0.5em;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)

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
        # Use a shared SettingsManager instance — callers (main()) should pass
        # one if they need it later, but for a lightweight startup check the
        # instance created here is inexpensive and short-lived.
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

def detect_wayland():
    """Detect if running under Wayland and apply necessary fixes."""
    # Check multiple indicators for Wayland session
    wayland_indicators = [
        os.environ.get("XDG_SESSION_TYPE") == "wayland",
        os.environ.get("WAYLAND_DISPLAY") is not None,
        os.environ.get("GDK_BACKEND") == "wayland",
        "wayland" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    ]
    
    is_wayland = any(wayland_indicators)
    
    if is_wayland:
        # Force Qt to use X11 backend for better compatibility
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        # Disable auto scaling which can cause issues on Wayland
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
        # Additional Wayland compatibility settings
        os.environ["QT_SCALE_FACTOR"] = "1"
        os.environ["QT_SCREEN_SCALE_FACTORS"] = ""
        # Force software rendering if needed
        if not os.environ.get("QT_QUICK_BACKEND"):
            os.environ["QT_QUICK_BACKEND"] = "software"
    
    return is_wayland

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
        
        # IMPORTANT: Detect and fix Wayland issues BEFORE creating QApplication
        is_wayland = detect_wayland()
        
        # Initialize Qt application AFTER Wayland fixes
        app = QApplication(sys.argv)
        
        # Apply theme settings
        is_dark = apply_theme(app)
        
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
