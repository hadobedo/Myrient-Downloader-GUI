# Myrient-Downloader-GUI
GUI that manages the downloading and processing video game ROMs/ISOs from [Myrient Video Game Preservationists](https://myrient.erista.me). Written in Python! 

> [!IMPORTANT]
> **Myrient is scheduled to shut down on March 31st, 2026.** This is primarily due to a lack of donations covering essential hosting and maintenance costs, further exacerbated by the rise of paywalled download managers that actively divert funds away from the preservationists who dedicate their time and money to server upkeep...
> 
> If Myrient and the broader mission of video game & software preservation matter to you, **PLEASE MAKE A DONATION TO MYRIENT AS SOON AS POSSIBLE** to potentially support their continued operation and fairly compensate the team for their immense efforts.
> 
> **[CLICK HERE TO DONATE TO MYRIENT](https://myrient.erista.me/donate/)**

## Features
- **Multi-Platform Support**: Download ROMs/ISOs from multiple gaming platforms
  - Available platforms are easily extensible via YAML configuration
- **PS3 ISO Decryption & Extraction**: Option to decrypts and extract downloaded PS3 software for use on consoles and/or emulators like RPCS3
- **User-Friendly Setup**: Required binaries are retrieved & set automatically (on Windows)
- **Cross Platform**: Should work across all platforms!

## Quick Start

### Pre-built Releases (Recommended)
1. **[Download the latest release](https://github.com/hadobedo/Myrient-Downloader-GUI/releases/latest) for your platform**
2. **Extract** and **run** the executable
3. _**That's it!**_ File lists/necessary files will be retrieved automatically and stored in `config/`.

### Required files for PS3 processing - Windows
- **Simply launch `Myrient-Downloader-GUI` and you should be prompted to automatically download the required tools from their respective repositories!**
  - Alternatively, you can download the binaries `PS3Dec` and `extractps3iso` from below and manually specify them via `Settings`

### Required files for PS3 processing - Linux
```bash
# Arch Linux (AUR)
yay -S ps3dec-git ps3iso-utils-git

# Or install manually from source repositories
```

## Configuration
### Platform Configuration
The application uses a dynamic YAML-based configuration system located in [`config/myrient_urls.yaml`](config/myrient_urls.yaml), allowing for easy addition of new platforms without changing code.

### Settings Menu
The destination folders of in-progress and completed downloads for each platform can be defined via the Settings menu. Settings are saved to `config/myrientDownloaderGUI.ini`.

## Running from Source

#### Prerequisites
```bash
# Install Python dependencies
pip install -r requirements.txt

# Or on Arch Linux:
sudo pacman -S python-aiohttp python-beautifulsoup4 python-pyqt5 python-requests python-yaml python-pycdlib
```

#### Installation
```bash
# Clone the repository
git clone https://github.com/hadobedo/Myrient-Downloader-GUI.git
cd Myrient-Downloader-GUI

# Install dependencies
pip install -r requirements.txt

# Run the application
python3 ./myrientDownloaderGUI.py
```

## Credits/Binaries used:
- **[Myrient Video Game Preservationists](https://myrient.erista.me)** - Game preservation and hosting [[Support Myrient]](https://myrient.erista.me/donate/)
- **[Redrrx's PS3Dec](https://github.com/Redrrx/ps3dec)** - Modern PS3 ISO decryption tool
- **[bucanero's ps3iso-utils](https://github.com/bucanero/ps3iso-utils)** - PS3 ISO extraction utilities
- **[gotbletu's `ps3-split-iso` and `ps3-split-pkg` scripts)](https://github.com/gotbletu/shownotes/blob/master/ps3_split_merge_games.md)** - PS3 ISO/PKG splitting scripts adapted into Python
- AI :)

## TODO
- Better logging
  - Also add toggle to enable/disable ps3 decryption logs on Windows
- Terminal interface
- Consolidate `myrient_urls.yaml` and `myrientDownloaderGUI.ini` into a single yaml (maybe)
- Improve downloading of filelist `jsons` and `myrient_urls.yaml`, goal is to make user 'more aware' of what's happening
- Add dropdown box/'hardcode' some myrient urls for easier system configuration (maybe)

## Screenshots:
![image](https://github.com/user-attachments/assets/d746212f-65b6-47b1-9f78-11264e73cd12)
![image](https://github.com/user-attachments/assets/d6d9d0e2-a0a8-401b-8a55-291e45254180)
![image](https://github.com/user-attachments/assets/79e3be21-7e65-4417-b000-365ae86dabd0)

