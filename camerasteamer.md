# Camera Streamer Setup – Documentation
### (IMX708, Raspberry Pi CSI Camera, 720p60 WebRTC)

---

## Overview

This Raspberry Pi uses a CSI camera (IMX708 / Camera Module 3) accessed through libcamera, not `/dev/video0`.

We installed camera-streamer (Raspberry Pi build) and configured it to:

- Start automatically on boot
- Use the IMX708 CSI camera
- Stream at 720p 60 FPS
- Use auto exposure
- Enable autofocus
- Provide a WebRTC viewer at:
  http://drone.local:8080/webrtc

A systemd service ensures persistence and restarts on failure.

---

## Camera Details

- Camera type: libcamera
- Sensor path:
  /base/soc/i2c0mux/i2c@1/imx708@1a
- Features:
  - Autofocus
  - 30–120 FPS depending on resolution
  - Hardware H.264 encoding
  - Auto exposure / AWB

libcamera resets settings each run → all settings must be placed in the systemd service file.

---

## Systemd Service Configuration

Service file path:
`/etc/systemd/system/camera-streamer.service`

Full contents:

[Unit]
Description=Camera Streamer (IMX708, 720p60)
After=network.target

[Service]
ExecStart=/usr/bin/camera-streamer \
  --camera-type=libcamera \
  --camera-path=/base/soc/i2c0mux/i2c@1/imx708@1a \
  --camera-width=1280 \
  --camera-height=720 \
  --camera-fps=60 \
  --camera-auto_focus=1 \
  --http-listen=0.0.0.0 \
  --http-port=8080
Restart=always
User=drone

[Install]
WantedBy=multi-user.target

### Explanation of options

| Option | Purpose |
|--------|---------|
| --camera-type=libcamera | Use CSI camera backend |
| --camera-path=...imx708@1a | Target IMX708 module |
| --camera-width=1280 | 720p width |
| --camera-height=720 | 720p height |
| --camera-fps=60 | 60 FPS target |
| --camera-auto_focus=1 | Enable autofocus |
| --http-listen=0.0.0.0 | Serve on all network interfaces |
| --http-port=8080 | Web UI & WebRTC port |
| Restart=always | Auto-restart |
| User=drone | Run as non-root |

---

## Managing the Service

Enable on boot:
sudo systemctl enable camera-streamer.service

Start:
sudo systemctl start camera-streamer.service

Stop:
sudo systemctl stop camera-streamer.service

Restart:
sudo systemctl restart camera-streamer.service

Check status:
sudo systemctl status camera-streamer.service

View logs:
journalctl -u camera-streamer.service -n 40 --no-pager

---

## Accessing the Stream

Main UI:
http://drone.local:8080/

WebRTC low-latency viewer:
http://drone.local:8080/webrtc

---

## Why Settings Must Be in the Service File

- libcamera does not persist settings
- camera-streamer resets to defaults on start
- settings must be explicitly provided via systemd ExecStart

This ensures:
- 720p resolution
- 60 FPS
- Autofocus
- Auto exposure
- Stream starts on every boot

---

## Testing Persistence After Reboot

Reboot:
sudo reboot

Then verify the stream loads at:
http://drone.local:8080/webrtc

If it loads, persistence works.

---

## File Locations

| Path | Description |
|------|-------------|
| /etc/systemd/system/camera-streamer.service | Persistent config |
| /usr/bin/camera-streamer | Main binary |
| /usr/share/camera-streamer/ | Example configs |

---

## Optional Enhancements

Available tuning:
- Lower latency mode
- Better autofocus
- WiFi bitrate optimization
- Night mode
- Alternate profiles (1080p30, etc.)

Ask if you want any additional tuning.
