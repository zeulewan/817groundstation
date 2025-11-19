# Drone Ground Station – Documentation
### (WebRTC Video + BME680 Telemetry + LiFePO4wered Pi UPS Battery)

---

## Overview

This project provides a local “ground station” web dashboard for a Raspberry Pi–based drone.  
The dashboard displays:

- Live **WebRTC low-latency video** from camera-streamer  
- Live **BME680 environmental sensor data**  
- Live **battery percentage** from the LiFePO4wered Pi UPS  
- All combined into a single web page accessible at:  
  http://drone.local:5000/

This dashboard runs automatically on boot via a systemd service.

---

## Prerequisites

### I²C Enabled
Enable I2C:

sudo raspi-config  
→ Interface Options → I2C → Enable

Verify connected devices:

i2cdetect -y 1

Expected:
- `0x77` → BME680
- `0x43` → LiFePO4wered Pi UPS

---

## Installing Dependencies

Install system packages:

sudo apt update
sudo apt install -y python3-pip python3-venv python3-smbus i2c-tools git

Set up a Python virtual environment:

python3 -m venv ~/groundstation-venv
source ~/groundstation-venv/bin/activate

Install Python libraries:

pip install flask adafruit-circuitpython-bme680 adafruit-blinka

---

## Setting Up LiFePO4wered Pi Tools

Clone and install UPS utilities (only once):

cd ~
git clone https://github.com/xorbit/LiFePO4wered-Pi.git
cd LiFePO4wered-Pi
make
sudo make install

This installs `lifepo4wered-cli`, used to read VBAT voltage.

---

## Ground Station Application

Create the directory:

mkdir -p ~/groundstation
cd ~/groundstation

Create `app.py` with the complete Flask app:

(Already provided above; this file handles WebRTC embedding, BME680 reads, and UPS battery reads.)

Run manually to test:

source ~/groundstation-venv/bin/activate
cd ~/groundstation
python app.py

Open in browser:

http://drone.local:5000/

You should see:
- WebRTC video stream on the left  
- Sensor telemetry on the right  

---

## Systemd Service for Persistence

Create service:

sudo nano /etc/systemd/system/groundstation.service

Contents:

[Unit]
Description=Drone Ground Station Web UI
After=network.target

[Service]
User=drone
WorkingDirectory=/home/drone/groundstation
ExecStart=/home/drone/groundstation-venv/bin/python /home/drone/groundstation/app.py
Restart=always

[Install]
WantedBy=multi-user.target

Enable and start:

sudo systemctl daemon-reload
sudo systemctl enable groundstation.service
sudo systemctl start groundstation.service

Check status:

sudo systemctl status groundstation.service

---

## Accessing the Dashboard

Main dashboard (video + telemetry):

http://drone.local:5000/

Raw camera-streamer interface (optional):

http://drone.local:8080/

WebRTC viewer from camera-streamer:

http://drone.local:8080/webrtc

---

## Telemetry Data Explanation

### BME680 Readings
- Temperature (°C)
- Humidity (%)
- Pressure (hPa)
- Gas resistance (Ω)

### LiFePO4wered Pi UPS
- Reads `VBAT` in millivolts via `lifepo4wered-cli get VBAT`
- Converts voltage to percentage:
  - 3200 mV ≈ 0%
  - 3600 mV ≈ 100%

### Update rate
Telemetry updates every 1 second in the browser via `/api/telemetry`.

---

## File Locations

| Path | Description |
|------|-------------|
| `/home/drone/groundstation/app.py` | The dashboard server code |
| `/home/drone/groundstation-venv/` | Python virtual environment |
| `/etc/systemd/system/groundstation.service` | systemd service file |
| `/usr/bin/lifepo4wered-cli` | UPS utility |
| `/usr/bin/camera-streamer` | camera-streamer binary |

---

## Notes

- WebRTC is streamed directly from camera-streamer inside an iframe.
- Flask app only handles telemetry, not the video itself.
- Systemd ensures both camera-streamer and the ground station run automatically on boot.

---

## Next Steps (Optional)

- Add GPS, IMU, or barometer telemetry
- Create a “flight HUD”
- Add joystick control over WebRTC data channels
- Add mission logging into CSV files

Ask if you'd like to extend the dashboard.
