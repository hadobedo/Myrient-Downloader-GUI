import os
import yaml
import sys

class ConfigManager:
    """Manages application configuration loaded from YAML files."""
    
    DEFAULT_CONFIG_PATH = "MyrientDownloads/myrient_urls.yaml"
    # Class variable to track if we've already printed the config loaded message
    _config_loaded_message_shown = False
    
    # Textual fallback in case GitHub is unreachable
    DEFAULT_URLS_YAML_CONTENT = """# Default configuration for Myrient URLs
# You can add more platforms here as needed!

ps3:
  tab_name: "PS3 (ISO)"
  url: "https://f3.erista.me/files/Redump/Sony - PlayStation 3"
  dkeys: "https://f3.erista.me/files/Redump/Sony - PlayStation 3 - Disc Keys TXT/"
  show_ps3dec: true

psn:
  tab_name: "PS3/PSN (PKG)"
  url: "https://f6.erista.me/files/No-Intro/Sony%20-%20PlayStation%203%20(PSN)%20(Content)"
  show_pkg_split: true

ps2:
  tab_name: "PS2 (ISO)"  
  url: "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%202/"

psx:
  tab_name: "PSX (ISO)"
  url: "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation/"

psp:
  tab_name: "PSP (ISO)"
  url: "https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation%20Portable/"

gamecube:
  tab_name: "GameCube (RVZ)"
  url: "https://myrient.erista.me/files/Redump/Nintendo%20-%20GameCube%20-%20NKit%20RVZ%20[zstd-19-128k]/"

wii:
  tab_name: "Wii (RVZ)"
  url: "https://myrient.erista.me/files/Redump/Nintendo%20-%20Wii%20-%20NKit%20RVZ%20[zstd-19-128k]/"
"""
    
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
            
            # Only print the message if it hasn't been shown before
            if not ConfigManager._config_loaded_message_shown:
                sys.stdout.write(f"Loaded configuration from {self.config_file}\n")
                
                # Add message about customizing the config file
                config_path = os.path.abspath(self.config_file)
                sys.stdout.write(f"You can add other URLs by editing the YAML file at {config_path}\n")
                sys.stdout.flush()
                
                # Mark that we've shown the message
                ConfigManager._config_loaded_message_shown = True
                
        except Exception as e:
            sys.stderr.write(f"Error loading configuration: {str(e)}\n")
            sys.stderr.flush()
    
    def ensure_config_exists(self):
        """Ensure the configuration file exists, downloading it from GitHub if needed."""
        # Check in working directory
        config_filename = os.path.basename(self.config_file)
        if os.path.exists(config_filename):
            self.config_file = config_filename
            return
        
        # Check in config directory
        if os.path.exists(self.config_file):
            return
        
        # Neither location has the config, generate default
        sys.stderr.write(f"Configuration file not found at {self.config_file}\n")
        sys.stderr.write("Generating default myrient_urls.yaml configuration offline.\n")
        sys.stderr.flush()
        
        try:
            # Create config directory if it doesn't exist
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            # Write default configuration
            with open(self.config_file, 'w') as f:
                f.write(self.DEFAULT_URLS_YAML_CONTENT)
            sys.stderr.write(f"Successfully generated default configuration file to {self.config_file}\n")
            sys.stderr.flush()
            return
        except Exception as e:
            sys.stderr.write(f"Error creating default configuration file: {str(e)}\n")
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
