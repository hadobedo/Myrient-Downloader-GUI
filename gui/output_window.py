from PyQt5.QtWidgets import QTextEdit, QApplication
from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import pyqtSignal, QObject, QTimer
import sys
import re


class OutputRedirector(QObject):
    """A QObject that can safely redirect output across threads."""
    text_written = pyqtSignal(str)
    
    def __init__(self, output_window):
        super().__init__()
        self.output_window = output_window
        self.text_written.connect(self.output_window.append_text)
        self.buffer = ""
    
    def write(self, text):
        # Buffer the text until we get a complete line
        self.buffer += text
        
        # Process complete lines
        if '\n' in self.buffer:
            lines = self.buffer.split('\n')
            # Keep the last (potentially incomplete) line in the buffer
            self.buffer = lines[-1]
            
            # Send complete lines to the output window
            complete_lines = '\n'.join(lines[:-1])
            if complete_lines:
                self.text_written.emit(complete_lines + '\n')
        
        # If the buffer is getting too long without a newline, flush it
        elif len(self.buffer) > 1000:
            self.text_written.emit(self.buffer)
            self.buffer = ""
    
    def flush(self):
        if self.buffer:
            self.text_written.emit(self.buffer)
            self.buffer = ""


class OutputWindow(QTextEdit):
    """A custom QTextEdit that can be used as a stdout-like output window."""
    
    def __init__(self, *args, **kwargs):
        super(OutputWindow, self).__init__(*args, **kwargs)
        self.setReadOnly(True)
        
        # Store the original stdout for emergency use
        self.original_stdout = sys.stdout
        self.redirector = OutputRedirector(self)
        
        # Track if cursor is at the end
        self.atEnd = True
        
        # Track last written text to avoid double newlines
        self.lastWrittenEndsWithNewline = True
        
        # Create a single shot timer for deferred scrolling
        self.scrollTimer = QTimer()
        self.scrollTimer.setSingleShot(True)
        self.scrollTimer.timeout.connect(self.forceScrollToBottom)
        
    def set_as_stdout(self):
        """Set this OutputWindow as the system's stdout."""
        sys.stdout = self.redirector
        sys.stderr = self.redirector

    def restore_stdout(self):
        """Restore the original stdout."""
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stdout
    
    def append_text(self, text):
        """Append text to the output window (thread-safe method)."""
        # Clean up the text - normalize newlines and remove excessive ones
        text = text.replace('\r\n', '\n')
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Make sure all text ends with a newline
        if not text.endswith('\n'):
            text += '\n'
        
        # If the last text we wrote ended with a newline and this one starts with one,
        # remove the leading newline to avoid double spacing
        if self.lastWrittenEndsWithNewline and text.startswith('\n'):
            text = text[1:]
        
        # Remember if this text ends with a newline
        self.lastWrittenEndsWithNewline = text.endswith('\n')
        
        # Add the text
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.setTextCursor(cursor)
        
        # Scroll to bottom with multiple approaches to ensure it works
        self.ensureCursorVisible()
        self.forceScrollToBottom()
        
        # Schedule another scroll to bottom after event processing
        self.scrollTimer.start(50)  # 50ms delay
        
        # Clear any excess text if the document is getting too large
        document = self.document()
        if document.characterCount() > 100000:  # Limit to ~100K characters
            cursor = QTextCursor(document)
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 50000)  # Delete oldest 50K chars
            cursor.removeSelectedText()
        
        QApplication.processEvents()
    
    def forceScrollToBottom(self):
        """Force the text edit to scroll to the bottom."""
        # Move scrollbar to maximum position
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # Also make sure cursor is at the end
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
