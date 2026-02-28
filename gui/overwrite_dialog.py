from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QCheckBox, QFrame, QScrollArea, QWidget)
from PyQt5.QtCore import Qt, QObject, QMutex, QWaitCondition, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
import os

from core.utils import format_file_size


class OverwriteDialog(QDialog):
    """Dialog for handling file overwrite conflicts."""
    
    # Return codes for user actions
    OVERWRITE = 1
    SKIP = 2
    RENAME = 3
    CANCEL = 4
    
    def __init__(self, conflicts, operation_type="processing", parent=None):
        super().__init__(parent)
        self.conflicts = conflicts if isinstance(conflicts, list) else [conflicts]
        self.operation_type = operation_type
        self.user_choice = self.CANCEL
        self.apply_to_all = False
        
        self.setWindowTitle(f"File Conflicts - {operation_type.title()}")
        self.setModal(True)
        self.setMinimumSize(500, 300)
        self.setMaximumSize(800, 600)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout()
        
        # Title
        title_label = QLabel(f"File conflicts detected during {self.operation_type}")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Conflicts area
        if len(self.conflicts) > 1:
            # Multiple conflicts - show in scrollable area
            scroll_area = QScrollArea()
            scroll_widget = QWidget()
            scroll_layout = QVBoxLayout(scroll_widget)
            
            count_label = QLabel(f"Found {len(self.conflicts)} file conflicts:")
            count_font = QFont()
            count_font.setBold(True)
            count_label.setFont(count_font)
            scroll_layout.addWidget(count_label)
            
            for i, conflict in enumerate(self.conflicts[:10]):  # Show first 10
                conflict_widget = self._create_conflict_widget(conflict, i + 1)
                scroll_layout.addWidget(conflict_widget)
            
            if len(self.conflicts) > 10:
                more_label = QLabel(f"... and {len(self.conflicts) - 10} more files")
                more_font = QFont()
                more_font.setItalic(True)
                more_label.setFont(more_font)
                scroll_layout.addWidget(more_label)
            
            scroll_area.setWidget(scroll_widget)
            scroll_area.setMaximumHeight(200)
            layout.addWidget(scroll_area)
        else:
            # Single conflict
            conflict_widget = self._create_conflict_widget(self.conflicts[0])
            layout.addWidget(conflict_widget)
        
        # Options section
        options_label = QLabel("What would you like to do?")
        options_font = QFont()
        options_font.setBold(True)
        options_label.setFont(options_font)
        layout.addWidget(options_label)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Overwrite button
        self.overwrite_btn = QPushButton("Overwrite")
        self.overwrite_btn.setToolTip("Replace existing files with new ones")
        self.overwrite_btn.clicked.connect(lambda: self._set_choice(self.OVERWRITE))
        button_layout.addWidget(self.overwrite_btn)
        
        # Skip button
        self.skip_btn = QPushButton("Skip")
        self.skip_btn.setToolTip("Keep existing files, skip processing new ones")
        self.skip_btn.clicked.connect(lambda: self._set_choice(self.SKIP))
        button_layout.addWidget(self.skip_btn)
        
        # Rename button (for some operations)
        if self.operation_type in ["processing", "extraction"]:
            self.rename_btn = QPushButton("Rename")
            self.rename_btn.setToolTip("Create new files with different names")
            self.rename_btn.clicked.connect(lambda: self._set_choice(self.RENAME))
            button_layout.addWidget(self.rename_btn)
        
        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setToolTip("Cancel the operation")
        self.cancel_btn.clicked.connect(lambda: self._set_choice(self.CANCEL))
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Apply to all checkbox (for multiple conflicts)
        if len(self.conflicts) > 1:
            self.apply_all_cb = QCheckBox("Apply this choice to all conflicts")
            self.apply_all_cb.setChecked(True)
            layout.addWidget(self.apply_all_cb)
        
        self.setLayout(layout)
        
        # Set default button based on operation type
        if self.operation_type == "downloading":
            self.skip_btn.setDefault(True)
        else:
            self.overwrite_btn.setDefault(True)
    
    def _create_conflict_widget(self, conflict_info, index=None):
        """Create a widget showing conflict information."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 5, 10, 5)
        
        if index:
            index_label = QLabel(f"Conflict {index}:")
            index_font = QFont()
            index_font.setBold(True)
            index_label.setFont(index_font)
            layout.addWidget(index_label)
        
        # File path
        if isinstance(conflict_info, dict):
            file_path = conflict_info.get('path', 'Unknown file')
            existing_size = conflict_info.get('existing_size', 0)
            new_size = conflict_info.get('new_size', 0)
        else:
            file_path = str(conflict_info)
            existing_size = 0
            new_size = 0
        
        path_label = QLabel(f"File: {file_path}")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)
        
        # Size information if available
        if existing_size > 0 or new_size > 0:
            size_info = QLabel(f"Existing: {self._format_size(existing_size)} | New: {self._format_size(new_size)}")
            size_font = QFont()
            size_font.setPointSize(8)
            size_info.setFont(size_font)
            layout.addWidget(size_info)
        
        # Simple border styling that respects system theme
        widget.setStyleSheet("QWidget { border: 1px solid palette(mid); border-radius: 4px; margin: 2px; }")
        
        return widget
    
    def _set_choice(self, choice):
        """Set the user's choice and close dialog."""
        self.user_choice = choice
        if hasattr(self, 'apply_all_cb'):
            self.apply_to_all = self.apply_all_cb.isChecked()
        else:
            self.apply_to_all = False
        self.accept()
    
    def _format_size(self, size_bytes):
        """Format file size in human-readable format."""
        if size_bytes == 0:
            return "Unknown"
        return format_file_size(size_bytes)
    
    @staticmethod
    def ask_overwrite(conflicts, operation_type="processing", parent=None):
        """Show overwrite dialog and return user choice."""
        dialog = OverwriteDialog(conflicts, operation_type, parent)
        
        if dialog.exec_() == QDialog.Accepted:
            return dialog.user_choice, dialog.apply_to_all
        else:
            return OverwriteDialog.CANCEL, False


class OverwriteManager:
    """Manages overwrite decisions and applies user choices."""
    
    def __init__(self):
        self.global_choice = None
        self.apply_to_all = False
    
    def reset(self):
        """Reset global choices."""
        self.global_choice = None
        self.apply_to_all = False
    
    def handle_conflict(self, conflict_info, operation_type="processing", parent=None):
        """
        Handle a file conflict, either using global choice or asking user.
        
        Args:
            conflict_info: Dictionary with conflict details or file path string
            operation_type: Type of operation (downloading, extraction, processing)
            parent: Parent widget for dialog
        
        Returns:
            Tuple of (action, apply_to_all) where action is one of:
            OverwriteDialog.OVERWRITE, SKIP, RENAME, or CANCEL
        """
        # If we have a global choice that applies to all, use it
        if self.global_choice is not None and self.apply_to_all:
            return self.global_choice, True
        
        # Ask the user
        choice, apply_to_all = OverwriteDialog.ask_overwrite(
            conflict_info, operation_type, parent
        )
        
        # Store global choice if apply to all is selected
        if apply_to_all:
            self.global_choice = choice
            self.apply_to_all = True
        
        return choice, apply_to_all
    
    def should_overwrite(self, file_path, operation_type="processing", parent=None):
        """
        Simple helper to check if a file should be overwritten.
        
        Returns:
            True if should overwrite, False if should skip, None if cancelled
        """
        if not os.path.exists(file_path):
            return True  # No conflict
        
        # Get file size for conflict info
        try:
            existing_size = os.path.getsize(file_path)
        except OSError:
            existing_size = 0
        
        conflict_info = {
            'path': file_path,
            'existing_size': existing_size,
            'new_size': 0  # Unknown for simple checks
        }
        
        choice, _ = self.handle_conflict(conflict_info, operation_type, parent)
        
        if choice == OverwriteDialog.OVERWRITE:
            return True
        elif choice == OverwriteDialog.SKIP:
            return False
        else:  # CANCEL or RENAME
            return None  # Indicates cancellation


class ThreadSafeOverwriteManager(QObject):
    """Thread-safe overwrite manager that delegates dialog display to the main thread.

    Worker threads call handle_conflict() which emits a signal and blocks via
    QMutex/QWaitCondition until the main thread processes the request and calls
    provide_response().
    """

    # Signal: emitted from worker thread, connected to main-thread slot
    conflict_request = pyqtSignal(object, str)  # (conflict_info, operation_type)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mutex = QMutex()
        self._wait_condition = QWaitCondition()
        self._response_choice = OverwriteDialog.CANCEL
        self._response_apply_all = False
        self.global_choice = None
        self.apply_to_all = False

    def reset(self):
        """Reset global choices."""
        self.global_choice = None
        self.apply_to_all = False

    def handle_conflict(self, conflict_info, operation_type="processing", parent=None):
        """Thread-safe conflict handler. Blocks the calling thread until a response
        is provided by the main thread via provide_response().

        Args:
            conflict_info: Dictionary with conflict details or file path string
            operation_type: Type of operation (downloading, extraction, processing)
            parent: Ignored (dialog parent is determined by the main-thread handler)

        Returns:
            Tuple of (action, apply_to_all)
        """
        # If we have a global choice that applies to all, return immediately (no dialog needed)
        if self.global_choice is not None and self.apply_to_all:
            return self.global_choice, True

        # Emit signal to request dialog from main thread, then block
        self._mutex.lock()
        try:
            self.conflict_request.emit(conflict_info, operation_type)
            # Block until main thread calls provide_response()
            self._wait_condition.wait(self._mutex)
            choice = self._response_choice
            apply_all = self._response_apply_all
        finally:
            self._mutex.unlock()

        # Store global choice if apply to all is selected
        if apply_all:
            self.global_choice = choice
            self.apply_to_all = True

        return choice, apply_all

    def provide_response(self, choice, apply_to_all=False):
        """Called from the MAIN THREAD to unblock the waiting worker thread.

        Args:
            choice: One of OverwriteDialog.OVERWRITE, SKIP, RENAME, CANCEL
            apply_to_all: Whether to apply this choice to all future conflicts
        """
        self._mutex.lock()
        try:
            self._response_choice = choice
            self._response_apply_all = apply_to_all
            self._wait_condition.wakeAll()
        finally:
            self._mutex.unlock()