import os
import json
import time
from datetime import datetime

class StateManager:
    """Manages application state persistence for pause/resume functionality."""
    
    CONFIG_DIR = "MyrientDownloads/config"
    PAUSE_STATE_FILE = os.path.join(CONFIG_DIR, "pause_state.json")
    
    @staticmethod
    def save_pause_state(current_item, queue_position, operation, file_path, processed_items, total_items, remaining_queue):
        """Save the current state when paused."""
        # Ensure config directory exists
        os.makedirs(StateManager.CONFIG_DIR, exist_ok=True)
        
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
    
    @staticmethod
    def load_pause_state():
        """Load the saved pause state if it exists."""
        if not os.path.exists(StateManager.PAUSE_STATE_FILE):
            # Check for old pause state file in root directory
            old_file_path = "pause_state.json"
            if os.path.exists(old_file_path):
                try:
                    # Ensure config directory exists
                    os.makedirs(StateManager.CONFIG_DIR, exist_ok=True)
                    
                    # Migrate old file to new location
                    with open(old_file_path, 'r') as old_file:
                        state = json.load(old_file)
                    
                    with open(StateManager.PAUSE_STATE_FILE, 'w') as new_file:
                        json.dump(state, new_file)
                    
                    # Remove old file after successful migration
                    os.remove(old_file_path)
                    print(f"Migrated pause state from root to {StateManager.PAUSE_STATE_FILE}")
                    
                    return state
                except Exception as e:
                    print(f"Error migrating pause state: {str(e)}")
                    return None
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
        
        # Also clear old file if it exists
        old_file_path = "pause_state.json"
        if os.path.exists(old_file_path):
            os.remove(old_file_path)
