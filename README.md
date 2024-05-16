# Myrient-Downloader-GUI
Tool to download software from Myrient, written in Python
![image](https://github.com/hadobedo/Myrient-Downloader-GUI/assets/34556645/5d499a6b-b53e-4a09-bafe-785e01261973)

Features:
- Downloads software over HTTP from [the Myrient Video Game Preservationists](https://myrient.erista.me)
- Options to decrypts and split downloaded software for use on consoles, storage on FAT32 devices
- User-friendly setup (prompts users to download required binaries automatically)
- Cross platform (macOS = ?)

Usage:
1. [Download the latest release for your platform](https://github.com/hadobedo/Myrient-Downloader-GUI/releases/latest)
2. Run the exe

On first run the user must download/specify location of PS3Dec and optionally set destination folders for downloaded software

To run the script as a .py file:
1. Clone repo & cd into folder `git clone https://github.com/hadobedo/Myrient-Downloader-GUI/ && cd Myrient-Downloader-GUI/`
2. Install the requirements (if on Arch Linux see below) `pip install -r requirements.txt`
3. Run the script `python3 ./myrientDownloaderGUI.py`

Requirements on Arch Linux can be installed like so:
`sudo pacman -S python-aiohttp python-beautifulsoup4 python-pyqt5 python-requests`

PS3Dec is available from the AUR as [`ps3dec-git`](https://aur.archlinux.org/packages/ps3dec-git)
Instructions to build PS3Dec on Linux [can be found here](https://github.com/al3xtjames/PS3Dec)

Credits/Binaries used:
- [Myrient Video Game Preservationists](https://myrient.erista.me) [[Donation Link]](https://myrient.erista.me/donate/)
- [Redrrx's PS3Dec rewrite in Rust](https://github.com/Redrrx/ps3dec)
- [gotbletu's `ps3-split-iso` and `ps3-split-pkg` scripts 'ported'/adapted into Python)](https://github.com/gotbletu/shownotes/blob/master/ps3_split_merge_games.md)
- [bucanero's ps3iso-utils](https://github.com/bucanero/ps3iso-utils) (used their splitps3iso binary in the past)
- gpt-4 :)

TODO:
- add support for more software
- add support for user specified software
- clean up code

screenshots:
![image](https://github.com/hadobedo/Myrient-Downloader-GUI/assets/34556645/4447999e-d90f-409b-aab5-e68416e54637)
![image](https://github.com/hadobedo/Myrient-Downloader-GUI/assets/34556645/3d2af247-1eeb-4821-993f-715c21e14084)
