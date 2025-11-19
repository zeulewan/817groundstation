from flask import Flask, jsonify
import time
import subprocess
import re

import board
import busio
import adafruit_bme680

# ---------- BME680 SETUP ----------

i2c = busio.I2C(board.SCL, board.SDA)
bme = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=0x77)

# You can tweak oversampling etc here if needed:
# bme.sea_level_pressure = 1013.25

# ---------- LiFePO4wered UPS HELPERS ----------

def get_battery_percent():
    """
    Read VBAT via lifepo4wered-cli and convert to an approximate percentage.
    For LiFePO4: treat ~3.20V as 0%, ~3.60V as 100% (very rough).
    """
    try:
        out = subprocess.check_output(
            ["lifepo4wered-cli", "get", "VBAT"],
            text=True
        ).strip()
        # Handle either "VBAT=3450 mV" or just "3450" formats
        m = re.search(r"(\d+)", out)
        if not m:
            return None

        mv = int(m.group(1))  # millivolts
        low = 3200
        high = 3600

        if mv <= low:
            return 0
        if mv >= high:
            return 100

        pct = int((mv - low) * 100 / (high - low))
        return pct
    except Exception as e:
        print("Battery read error:", e)
        return None

def get_bme_readings():
    return {
        "temperature_c": float(bme.temperature),
        "humidity": float(bme.humidity),
        "pressure_hpa": float(bme.pressure),
        "gas_ohms": float(bme.gas),
    }

# ---------- FLASK APP ----------

app = Flask(__name__)

INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Drone Ground Station</title>
  <style>
    body { font-family: system-ui, sans-serif; background:#111; color:#eee; margin:0; padding:0; }
    .layout { display:flex; flex-direction:row; height:100vh; }
    iframe { border:0; flex:2; background:#000; }
    .sidebar { flex:1; padding:16px; box-sizing:border-box; background:#181818; overflow-y:auto; }
    h1 { font-size:20px; margin-top:0; }
    .card { background:#222; padding:12px 16px; margin-bottom:12px; border-radius:8px; }
    .label { color:#aaa; font-size:11px; text-transform:uppercase; letter-spacing:1px; }
    .value { font-size:24px; margin-top:4px; }
    .small { font-size:12px; color:#888; margin-top:4px; }
  </style>
</head>
<body>
<div class="layout">
  <!-- Camera stream from camera-streamer -->
  <iframe src="http://drone.local:8080/webrtc" allow="camera; microphone"></iframe>

  <!-- Telemetry sidebar -->
  <div class="sidebar">
    <h1>Drone Ground Station</h1>

    <div class="card">
      <div class="label">Battery</div>
      <div class="value" id="battery">-- %</div>
      <div class="small" id="battery_raw"></div>
    </div>

    <div class="card">
      <div class="label">Temperature</div>
      <div class="value"><span id="temp">--</span> °C</div>
    </div>

    <div class="card">
      <div class="label">Humidity</div>
      <div class="value"><span id="hum">--</span> %</div>
    </div>

    <div class="card">
      <div class="label">Pressure</div>
      <div class="value"><span id="press">--</span> hPa</div>
    </div>

    <div class="card">
      <div class="label">Gas</div>
      <div class="value"><span id="gas">--</span> Ω</div>
    </div>

    <div class="card">
      <div class="label">Status</div>
      <div class="small" id="status">Connecting…</div>
    </div>
  </div>
</div>

<script>
async function refreshTelemetry() {
  try {
    const resp = await fetch('/api/telemetry');
    const data = await resp.json();

    if (data.battery_percent !== null) {
      document.getElementById('battery').textContent = data.battery_percent + ' %';
      if (data.battery_mv !== null) {
        document.getElementById('battery_raw').textContent = data.battery_mv + ' mV';
      }
    } else {
      document.getElementById('battery').textContent = 'N/A';
      document.getElementById('battery_raw').textContent = '';
    }

    document.getElementById('temp').textContent = data.temperature_c.toFixed(1);
    document.getElementById('hum').textContent = data.humidity.toFixed(1);
    document.getElementById('press').textContent = data.pressure_hpa.toFixed(1);
    document.getElementById('gas').textContent = Math.round(data.gas_ohms);

    const d = new Date(data.timestamp * 1000);
    document.getElementById('status').textContent = 'Last update: ' + d.toLocaleTimeString();
  } catch (e) {
    console.error(e);
    document.getElementById('status').textContent = 'Error talking to /api/telemetry';
  }
}

setInterval(refreshTelemetry, 1000);
refreshTelemetry();
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return INDEX_HTML

@app.route("/api/telemetry")
def telemetry():
    bme = get_bme_readings()

    # Also expose raw VBAT in mV for debugging
    battery_mv = None
    battery_pct = None
    try:
        out = subprocess.check_output(
            ["lifepo4wered-cli", "get", "VBAT"],
            text=True
        ).strip()
        m = re.search(r"(\\d+)", out)
        if m:
            battery_mv = int(m.group(1))
    except Exception as e:
        print("VBAT read error:", e)

    if battery_mv is not None:
        low = 3200
        high = 3600
        if battery_mv <= low:
            battery_pct = 0
        elif battery_mv >= high:
            battery_pct = 100
        else:
            battery_pct = int((battery_mv - low) * 100 / (high - low))

    return jsonify(
        temperature_c=bme["temperature_c"],
        humidity=bme["humidity"],
        pressure_hpa=bme["pressure_hpa"],
        gas_ohms=bme["gas_ohms"],
        battery_percent=battery_pct,
        battery_mv=battery_mv,
        timestamp=time.time()
    )

if __name__ == "__main__":
    # Bind on all interfaces so you can hit it from your LAN
    app.run(host="0.0.0.0", port=5000)
