# Myrient-Downloader-GUI
Tool to download software from Myrient, written in Python
![image](https://github.com/hadobedo/Myrient-Downloader-GUI/assets/34556645/5d499a6b-b53e-4a09-bafe-785e01261973)

Features:
- Downloads software from [the Myrient Video Game Preservationists](https://myrient.erista.me), decrypts and splits downloaded software 'automatically' as necessary
- User-friendly setup (prompts users to download required binaries automatically)
- Cross platform, should work on Windows and Linux, may work on macOS

Usage:
1. [Download the latest release for your platform](https://github.com/hadobedo/myrientgrabber-ps3/releases/latest)
2. Run the exe, download/specify location of PS3Dec and you're good to go

If you'd like to run this script as a .py file instead of a binary:
1. Clone repo & cd into folder `git clone https://github.com/hadobedo/Myrient-Downloader-GUI/ && cd Myrient-Downloader-GUI/`
2. Install the requirements (if on Arch Linux see below) `pip install -r requirements.txt`
3. Run the script! `python3 ./myrientDownloaderGUI.py`

Alternatively grab a precompiled EXE or Linux binary from the releases tab!

If you're on a Arch Linux where the Python environment is externally managed you can install requirements like so:
`sudo pacman -S python-aiohttp python-beautifulsoup4 python-pyqt5 python-requests`

If you're on Arch Linux and you need PS3Dec you can [get it from the aur](https://aur.archlinux.org/packages/ps3dec-git)

Credits:
- [Myrient Video Game Preservationists](https://myrient.erista.me) [(Give them a donation if you can!)](https://myrient.erista.me/donate/])
- [Redrrx (uses their PS3Dec Rust rewrite for Windows, it rocks)](https://github.com/Redrrx/ps3dec)
- [gotbletu (uses their ps3-split-iso and ps3-split-pkg script adapted into python)](https://github.com/gotbletu/shownotes/blob/master/ps3_split_merge_games.md)
- [bucanero's ps3iso-utils](https://github.com/bucanero/ps3iso-utils) (used their splitps3iso binary in the past)
- gpt-4 :)

TODO:
- clean up code

screenshots:
![image](https://github.com/hadobedo/Myrient-Downloader-GUI/assets/34556645/4447999e-d90f-409b-aab5-e68416e54637)
![image](https://github.com/hadobedo/Myrient-Downloader-GUI/assets/34556645/3d2af247-1eeb-4821-993f-715c21e14084)
