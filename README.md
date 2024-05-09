installation and usage:
1. `git clone https://github.com/hadobedo/myrientgrabber-ps3/ && cd myrientgrabber-ps3/`
2. `pip install -r requirements.txt`
3. `./myrientDownloaderGUI.py`

if you're on a linux distro like arch that manages python on its own via pacman, install requirements with the following command:
`sudo pacman -S python-requests python-beautifulsoup4 python-pyqt5 python-tqdm`

todo:
- windows support (settings button w/ support for setting custom `PS3Dec`, `splitps3iso` binary paths)
- better output
