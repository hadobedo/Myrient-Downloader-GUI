# myrientgrabber-ps3

ps3 game grabber/decryptor/splitter written in python

features:
- automatic download, decryption and splitting of ps3 isos
- option to download ps3dec, splitps3iso binaries automatically from within the gui
- cross platform, should work on windows and linux, may work on macos

installation and usage:
1. `git clone https://github.com/hadobedo/myrientgrabber-ps3/ && cd myrientgrabber-ps3/`
2. `pip install -r requirements.txt`
3. `python3 ./myrientDownloaderGUI.py`

alternatively grab a precompiled exe or linux binary from the releases tab (nvm windows defender sees pyinstaller scripts as trojans :( )

if you're on a linux distro like arch linux whose python environment is externally managed you can install requirements like so:
`sudo pacman -S python-requests python-beautifulsoup4 python-pyqt5 python-tqdm`

if you're on arch linux and you need ps3dec you can [get it from the aur](https://aur.archlinux.org/packages/ps3dec-git)

credit:
[Redrrx's PS3Dec](https://github.com/Redrrx/ps3dec) (uses their ps3dec.exe Rust rewrite for Windows, it rocks)
[bucanero's ps3iso-utils](https://github.com/bucanero/ps3iso-utils) (uses their splitps3iso binary)

todo:
- better output
- clean up code
- add more game support for other consoles?
- multithreading

screenshots:
![Screenshot_20240512_045047](https://github.com/hadobedo/myrientgrabber-ps3/assets/34556645/68b227d3-67b9-49a3-a47e-7606217e0964)
![Screenshot_20240511_032153](https://github.com/hadobedo/myrientgrabber-ps3/assets/34556645/a2be69ad-424f-45da-a6b3-db06519d65a4)


use at your own risk etc etc
