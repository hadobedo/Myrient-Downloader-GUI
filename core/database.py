import sqlite3
import os
import json

class AppDatabase:
    """Manages the centralized SQLite database for application state and cache."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppDatabase, cls).__new__(cls)
            cls._instance.db_path = os.path.join("MyrientDownloads", "data", "myrient.db")
            cls._instance.init_db()
        return cls._instance
        
    def init_db(self):
        """Initialize the database and tables if they don't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create queue table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    size TEXT,
                    position INTEGER NOT NULL
                )
            ''')
            
            # Create lists_cache table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lists_cache (
                    platform_id TEXT PRIMARY KEY,
                    json_data TEXT NOT NULL
                )
            ''')
            
            conn.commit()
            
    # Queue Operations
    def get_queue(self):
        """Get all items from the queue, ordered by position."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT filename, size FROM queue ORDER BY position ASC')
            return [{'name': row[0], 'size': row[1] if row[1] else ""} for row in cursor.fetchall()]
            
    def save_queue(self, items):
        """Save a new queue, entirely replacing the old one."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM queue')
            
            for idx, item in enumerate(items):
                cursor.execute(
                    'INSERT INTO queue (filename, size, position) VALUES (?, ?, ?)',
                    (item['name'], item.get('size', ""), idx)
                )
            
            conn.commit()
            
    # List Cache Operations
    def get_list_cache(self, platform_id):
        """Get the cached software list for a platform."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT json_data FROM lists_cache WHERE platform_id = ?', (platform_id,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except json.JSONDecodeError:
                    return None
            return None
            
    def save_list_cache(self, platform_id, data):
        """Save a software list cache for a platform."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            json_str = json.dumps(data)
            cursor.execute(
                'INSERT OR REPLACE INTO lists_cache (platform_id, json_data) VALUES (?, ?)',
                (platform_id, json_str)
            )
            conn.commit()
