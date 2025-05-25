import os
import yaml
import sys

class ConfigManager:
    """Manages application configuration loaded from YAML files."""
    
    DEFAULT_CONFIG_PATH = "config/myrient_urls.yaml"
    
    def __init__(self, config_file=None):
        self.config_file = config_file or self.DEFAULT_CONFIG_PATH
        self.config = {}
        self.ensure_config_exists()
        self.load_config()
    
    def load_config(self):
        """Load configuration from YAML file."""
        try:
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f)
            # Use sys.stdout.write to ensure it goes through our redirection
            sys.stdout.write(f"Loaded configuration from {self.config_file}\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"Error loading configuration: {str(e)}\n")
            sys.stderr.flush()
    
    def ensure_config_exists(self):
        """Ensure the configuration file exists."""
        if not os.path.exists(self.config_file):
            sys.stderr.write(f"ERROR: Configuration file not found at {self.config_file}\n")
            sys.stderr.write("Please ensure the myrient_urls.yaml file is present in the config directory.\n")
            sys.stderr.write("The application requires this file to function properly.\n")
            sys.stderr.flush()
            # Initialize with empty config rather than hardcoding defaults
            self.config = {}
    
    def get_platform_checkbox_settings(self, platform_id):
        """Get checkbox visibility settings for a platform."""
        if platform_id in self.config:
            return {
                'show_ps3dec': self.config[platform_id].get('show_ps3dec', False),
                'show_pkg_split': self.config[platform_id].get('show_pkg_split', False),
            }
        return {
            'show_ps3dec': False,
            'show_pkg_split': False,
        }
    
    def get_url(self, platform, url_type):
        """Get a specific URL from the configuration."""
        try:
            return self.config.get(platform, {}).get(url_type)
        except Exception:
            return None
    
    def get_platforms(self):
        """Get all platform information including tab names and URLs."""
        platforms = {}
        
        for key, data in self.config.items():
            if 'url' in data and 'tab_name' in data:
                platforms[key] = {
                    'tab_name': data['tab_name'],
                    'url': data['url']
                }
                # Copy additional fields
                if 'dkeys' in data:
                    platforms[key]['dkeys'] = data['dkeys']
        
        return platforms
    
    def get_platform_urls(self):
        """Get all platform URLs for loading software lists (legacy method)."""
        urls = {}
        
        platforms = self.get_platforms()
        for platform_id, data in platforms.items():
            # Map platform IDs to the legacy URL keys
            if platform_id == 'ps3':
                urls['ps3iso'] = data['url']
            elif platform_id == 'ps2':
                urls['ps2iso'] = data['url']
            elif platform_id == 'psx':
                urls['psxiso'] = data['url']
            elif platform_id == 'psp':
                urls['pspiso'] = data['url']
            elif platform_id == 'psn':
                urls['psn'] = data['url']
            else:
                # Add new platforms with their original IDs
                urls[platform_id] = data['url']
        
        return urls
