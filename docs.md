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

## Hardware Requirements

- Raspberry Pi with CSI camera (IMX708 / Camera Module 3)
- BME680 sensor on I²C address `0x77`
- LiFePO4wered Pi UPS on I²C address `0x43`
- Working WiFi or Ethernet connection

---

## Software Requirements

### System Packages (APT)

Install:

sudo apt update
sudo apt install -y \
    python3-full \
    python3-venv \
    python3-pip \
    python3-smbus \
    i2c-tools \
    git \
    zsh

Why these matter:

| Package | Purpose |
|--------|---------|
| python3-full | Required so venv + pip work (fixes PEP 668 issues) |
| python3-venv | Needed for creating isolated Python environments |
| python3-pip | Package installer used inside the venv |
| python3-smbus | Python access to I²C |
| i2c-tools | Tools like `i2cdetect` to debug sensors |
| git | Needed to install LiFePO4wered utilities |
| zsh | For your shell setup (optional) |

---

## Camera-Streamer Requirements

Make sure camera-streamer is installed and running.  
Its WebRTC viewer must be reachable at:

http://drone.local:8080/webrtc

If camera-streamer does not run:
- Reinstall ***
- Ensure systemd service is active (camera-streamer.service)

---

## Prerequisites

### I²C Enabled

Enable I²C:

sudo raspi-config  
→ Interface Options → I2C → Enable

Verify connected devices:

i2cdetect -y 1

Expected:
- `0x77` → BME680
- `0x43` → LiFePO4wered Pi UPS

---

## Creating the Python Virtual Environment

Create a venv:

python3 -m venv ~/groundstation-venv

Activate it:

source ~/groundstation-venv/bin/activate

Verify activation:

echo $VIRTUAL_ENV

It MUST output:

/home/drone/groundstation-venv

If it’s blank, you are NOT in the venv.

---

## Installing Python Libraries (Inside the venv)

pip install flask adafruit-circuitpython-bme680 adafruit-blinka

Why:

| Library | Purpose |
|---------|---------|
| Flask | Web dashboard server |
| adafruit-circuitpython-bme680 | Reads BME680 sensor data |
| adafruit-blinka | Hardware abstraction layer for I²C |

---

## Setting Up LiFePO4wered Pi Tools

Clone and install UPS utilities (only once):

cd ~  
git clone https://github.com/xorbit/LiFePO4wered-Pi.git  
cd LiFePO4wered-Pi  
make  
sudo make install  

This installs the command:

lifepo4wered-cli

Used to read VBAT battery voltage.

---

## Ground Station Application

Create the directory:

mkdir -p ~/groundstation  
cd ~/groundstation

Place `app.py` inside this folder.

This app:

- Embeds the WebRTC video using an HTML `<iframe>`
- Serves the ground station dashboard UI
- Polls `/api/telemetry` every 1 second
- Reads:
  - BME680 sensor values
  - LiFePO4wered UPS battery voltage
- Converts voltage into battery percentage
- Outputs JSON to the frontend

---

## Running the Ground Station Manually

source ~/groundstation-venv/bin/activate  
cd ~/groundstation  
python app.py

Then open:

http://drone.local:5000/

You should see:

- Live WebRTC camera feed (from camera-streamer)
- Temperature, humidity, pressure, gas readings
- Battery percentage + raw millivolt reading

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

Raw camera-streamer interface:

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
- Battery voltage read via:
  lifepo4wered-cli get VBAT
- Converted to percentage:
  - 3200 mV = 0%
  - 3600 mV = 100%

### Update Rate
Telemetry updates every 1 second via JavaScript polling `/api/telemetry`.

---

## File Locations

| Path | Description |
|------|-------------|
| `/home/drone/groundstation/app.py` | Ground station server code |
| `/home/drone/groundstation-venv/` | Python virtual environment |
| `/etc/systemd/system/groundstation.service` | systemd service file |
| `/usr/bin/lifepo4wered-cli` | UPS command |
| `/usr/bin/camera-streamer` | Camera-streamer binary |
| `/var/log/syslog` | System logs (fallback) |

---

## Notes

- WebRTC video is served by camera-streamer, NOT Flask.
- Flask only provides telemetry + UI.
- Systemd ensures both groundstation and camera-streamer run automatically.
- Virtual environments must be activated manually unless invoked from systemd.

---

## Optional Enhancements

- Add GPS, IMU, or additional sensors
- Add a live HUD overlay (altitude, velocity, heading)
- Log flight sessions to disk
- Stream telemetry over WebSocket instead of polling
- Add joystick or RC control using WebRTC DataChannels
- Add battery health prediction algorithms

Ask if you want help implementing any of these.
