#!/bin/bash
# One-time setup on the Raspberry Pi. Run from inside the flightwall folder:  bash install.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
LIB="$HOME/rpi-rgb-led-matrix"

echo "==> Installing system packages"
sudo apt-get update
sudo apt-get install -y git build-essential python3-dev python3-venv python3-setuptools \
    python3-pil python3-requests cython3 cmake

echo "==> Turning off onboard audio (it conflicts with the LED driver)"
CFG=/boot/firmware/config.txt
sudo sed -i 's/^dtparam=audio=on/dtparam=audio=off/' "$CFG"
grep -q '^dtparam=audio=off' "$CFG" || echo 'dtparam=audio=off' | sudo tee -a "$CFG" >/dev/null
echo 'blacklist snd_bcm2835' | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf >/dev/null

echo "==> Building the LED matrix library (takes a few minutes)"
[ -d "$LIB" ] || git clone https://github.com/hzeller/rpi-rgb-led-matrix.git "$LIB"
python3 -m venv --system-site-packages "$DIR/.venv"
"$DIR/.venv/bin/pip" install "$LIB"

echo "==> Creating config.toml"
[ -f "$DIR/config.toml" ] || cp "$DIR/config.example.toml" "$DIR/config.toml"
chmod +x "$DIR/run.sh"

echo "==> Setting up the start-on-boot service (not turned on yet)"
sudo tee /etc/systemd/system/flightwall.service >/dev/null <<EOF
[Unit]
Description=FlightWall LED display
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python $DIR/main.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload

echo
echo "Done! Reboot once with:   sudo reboot"
echo "Then test the panels with: cd $DIR && ./run.sh --mock"
