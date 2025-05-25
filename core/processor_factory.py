from core.file_processor_base import FileProcessorBase
from core.ps3_fileprocessor import PS3FileProcessor

class ProcessorFactory:
    """Factory for creating the appropriate file processor."""
    
    @staticmethod
    def create_processor(platform_id, settings_manager, output_window, progress_bar):
        """Create and return the appropriate processor for the given platform."""
        if platform_id == 'ps3' or platform_id == 'psn':
            return PS3FileProcessor(settings_manager, output_window, progress_bar)
        else:
            return FileProcessorBase(settings_manager, output_window, progress_bar)
