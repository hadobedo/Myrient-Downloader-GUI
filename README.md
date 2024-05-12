# myrientgrabber-ps3
PS3 ISO downloader/decryptor/splitter, written in Python
![Screenshot_20240512_045047](https://github.com/hadobedo/myrientgrabber-ps3/assets/34556645/68b227d3-67b9-49a3-a47e-7606217e0964)

Features:
- Downloads, decrypts and splits PS3 ISO's 'automatically' from [the Myrient Video Game Preservationists](https://myrient.erista.me)
- User-friendly setup (prompts users to download binaries, has option to grab automatically etc)
- Cross platform, should work on Windows and Linux, may work on macOS

Installation and Usage:
1. Clone repo & cd into folder `git clone https://github.com/hadobedo/myrientgrabber-ps3/ && cd myrientgrabber-ps3/`
2. Install the requirements (if on Arch Linux see below) `pip install -r requirements.txt`
3. Run the script! `python3 ./myrientDownloaderGUI.py`

~~Alternatively grab a precompiled EXE or Linux binary from the releases tab~~ (nvm Windows Defender saw my pyinstaller script as trojan, will try again after cleaning up code(?) )

If you're on a Arch Linux where the Python environment is externally managed you can install requirements like so:
`sudo pacman -S python-requests python-beautifulsoup4 python-pyqt5 python-tqdm`

If you're on Arch Linux and you need PS3Dec you can [get it from the aur](https://aur.archlinux.org/packages/ps3dec-git)

Credits:
- [Myrient Video Game Preservationists](https://myrient.erista.me) [(Give them a donation if you can!)](https://myrient.erista.me/donate/])
- [Redrrx's PS3Dec](https://github.com/Redrrx/ps3dec) (uses their ps3dec.exe Rust rewrite for Windows, it rocks)
- [bucanero's ps3iso-utils](https://github.com/bucanero/ps3iso-utils) (uses their splitps3iso binary)
- gpt-4 :)

TODO:
- clean up code
- add more game support for other consoles?

screenshots:
![Screenshot_20240512_045047](https://github.com/hadobedo/myrientgrabber-ps3/assets/34556645/68b227d3-67b9-49a3-a47e-7606217e0964)
![Screenshot_20240511_032153](https://github.com/hadobedo/myrientgrabber-ps3/assets/34556645/a2be69ad-424f-45da-a6b3-db06519d65a4)


use at your own risk etc etc
