# myrientgrabber-ps3
PS3 ISO downloader/decryptor/splitter, written in Python
![image](https://github.com/hadobedo/myrientgrabber-ps3/assets/34556645/76519cb9-38ce-4423-8591-a9f3f9d318cd)

Features:
- Downloads, decrypts and splits PS3 ISO's 'automatically' from [the Myrient Video Game Preservationists](https://myrient.erista.me)
- User-friendly setup (prompts users to download PS3Dec binary automatically)
- Cross platform, should work on Windows and Linux, may work on macOS

Usage:
1. [Download the latest release for your platform](https://github.com/hadobedo/myrientgrabber-ps3/releases/latest)
2. Run the exe, download/specify location of PS3Dec and you're good to go

If you'd like to run this script as a .py file instead of a binary:
1. Clone repo & cd into folder `git clone https://github.com/hadobedo/myrientgrabber-ps3/ && cd myrientgrabber-ps3/`
2. Install the requirements (if on Arch Linux see below) `pip install -r requirements.txt`
3. Run the script! `python3 ./myrientDownloaderGUI.py`

~~Alternatively grab a precompiled EXE or Linux binary from the releases tab (nvm Windows Defender saw my pyinstaller script as trojan, will try again after cleaning up code(?) )

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
- add more game support for other consoles?

screenshots:
![image](https://github.com/hadobedo/myrientgrabber-ps3/assets/34556645/76519cb9-38ce-4423-8591-a9f3f9d318cd)
![Screenshot_20240511_032153](https://github.com/hadobedo/myrientgrabber-ps3/assets/34556645/a2be69ad-424f-45da-a6b3-db06519d65a4)


use at your own risk etc etc
