import os
import json
import time
from datetime import datetime

class StateManager:
    """Manages application state persistence for pause/resume functionality."""
    
    PAUSE_STATE_FILE = "pause_state.json"
    
    @staticmethod
    def save_pause_state(current_item, queue_position, operation, file_path, processed_items, total_items, remaining_queue):
        """Save the current state when paused."""
        state = {
            "timestamp": datetime.now().isoformat(),
            "current_item": current_item,
            "queue_position": queue_position,
            "operation": operation,
            "file_path": file_path,
            "processed_items": processed_items,
            "total_items": total_items,
            "remaining_queue": remaining_queue  # Save remaining queue items
        }
        
        with open(StateManager.PAUSE_STATE_FILE, 'w') as f:
            json.dump(state, f)
            
        print(f"Pause state saved: {current_item} - {operation}")
    
    @staticmethod
    def load_pause_state():
        """Load the saved pause state if it exists."""
        if not os.path.exists(StateManager.PAUSE_STATE_FILE):
            return None
            
        try:
            with open(StateManager.PAUSE_STATE_FILE, 'r') as f:
                state = json.load(f)
            return state
        except Exception as e:
            print(f"Error loading pause state: {str(e)}")
            return None
    
    @staticmethod
    def clear_pause_state():
        """Clear the saved pause state."""
        if os.path.exists(StateManager.PAUSE_STATE_FILE):
            os.remove(StateManager.PAUSE_STATE_FILE)
