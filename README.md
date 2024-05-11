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

alternatively grab a precompiled exe or linux binary from the releases tab

if you're on a linux distro like arch linux whose python environment is externally managed you can install requirements like so:
`sudo pacman -S python-requests python-beautifulsoup4 python-pyqt5 python-tqdm`

if you're on arch linux and you need ps3dec you can [get it from the aur](https://aur.archlinux.org/packages/ps3dec-git)

todo:
- better output
- clean up code
- add more game support for other consoles?
- multithreading

screenshots:

<img src="https://github.com/hadobedo/myrientgrabber-ps3/assets/34556645/86aec050-7dcc-4dfa-b785-3f262187b4eb" width="400" height="750">

use at your own risk etc etc