import sys
import os
from PyQt5.QtWidgets import QApplication

# Mock X11 to run headless
os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication(sys.argv)

from core.settings import SettingsManager
from core.config_manager import ConfigManager

try:
    print("Testing ConfigManager...")
    cm = ConfigManager()
    
    print("Testing SettingsManager migration...")
    sm = SettingsManager(config_manager=cm)
    
    print("Initialization successful!")
    print(f"Data dir exists: {os.path.exists('data')}")
    print(f"Bin dir exists: {os.path.exists('bin')}")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
