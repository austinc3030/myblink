# myblink

## Install
```
git submodule update --init
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run on Startup
```
sudo cp myblink.service /etc/systemd/system/myblink.service
sudo systemctl daemon-reload
sudo systemctl enable myblink.service
sudo systemctl start myblink.service
sudo systemctl status myblink.service
```
