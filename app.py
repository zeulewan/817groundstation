from flask import Flask, jsonify, request
import time
import subprocess
import re
import board
import busio
import adafruit_bme680
import os
from datetime import datetime

# ---------- BME680 SETUP ----------
i2c = busio.I2C(board.SCL, board.SDA)
bme = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=0x77)

# ---------- LOGGING SETUP ----------
LOG_DIR = "/home/drone/flight_logs"
os.makedirs(LOG_DIR, exist_ok=True)
current_log_file = None
current_log_handle = None

# ---------- BATTERY HELPERS ----------
def get_battery_percent():
    try:
        out = subprocess.check_output(
            ["lifepo4wered-cli", "get", "VBAT"], text=True
        ).strip()
        m = re.search(r"(\d+)", out)
        if not m:
            return None, None
        mv = int(m.group(1))  # millivolts
        low, high = 3200, 3600
        if mv <= low:
            pct = 0
        elif mv >= high:
            pct = 100
        else:
            pct = int((mv - low) * 100 / (high - low))
        return pct, mv
    except Exception as e:
        print("Battery read error:", e)
        return None, None

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
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Drone Ground Station • Flight Test Telemetry</title>
  <style>
    :root {
      --bg: #0f172a;
      --surface: #1e293b;
      --border: #334155;
      --text: #e2e8f0;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --success: #22c55e;
      --warning: #f59e0b;
      --danger: #ef4444;
    }
    * { margin:0; padding:0; box-sizing:border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      height: 100vh;
      display: grid;
      grid-template-columns: 1fr 460px;
      overflow: hidden;
    }
    iframe { border: none; background: #000; }
    .sidebar {
      background: linear-gradient(to bottom, #1e293b, #0f172a);
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 20px;
      overflow-y: auto;
    }
    .header {
      text-align: center;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }
    .header h1 {
      font-size: 24px;
      font-weight: 600;
      letter-spacing: -0.5px;
    }
    .header .subtitle {
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 4px;
    }
    .clocks {
      display: flex;
      justify-content: space-between;
      padding: 12px 16px;
      background: rgba(0,0,0,0.3);
      border-radius: 8px;
      font-family: 'SF Mono', Monaco, monospace;
      font-size: 14px;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .card-title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: var(--text-muted);
      margin-bottom: 12px;
      font-weight: 500;
    }
    .value {
      font-size: 36px;
      font-weight: 300;
      line-height: 1;
    }
    .unit {
      font-size: 16px;
      color: var(--text-muted);
      margin-left: 4px;
    }
    .row {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .log-controls {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    button {
      padding: 14px 20px;
      font-size: 16px;
      font-weight: 600;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
    }
    #logBtn {
      background: var(--primary);
      color: white;
    }
    #logBtn.recording {
      background: var(--danger);
      animation: pulse 2s infinite;
    }
    #logBtn:hover { transform: translateY(-1px); box-shadow: 0 8px 20px rgba(56,189,248,0.3); }
    #logBtn.recording:hover { box-shadow: 0 8px 20px rgba(239,68,68,0.4); }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.8; }
    }
    .recording-indicator {
      display: none;
      color: var(--danger);
      font-size: 14px;
      align-items: center;
      gap: 8px;
    }
    .recording-indicator.active { display: flex; }
    .dot {
      width: 10px;
      height: 10px;
      background: var(--danger);
      border-radius: 50%;
      animation: blink 1.5s infinite;
    }
    @keyframes blink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
    .status {
      font-size: 13px;
      color: var(--text-muted);
      text-align: center;
      padding: 12px;
      background: rgba(0,0,0,0.2);
      border-radius: 8px;
      margin-top: auto;
    }
  </style>
</head>
<body>
  <iframe src="http://drone.local:8080/webrtc" allow="camera; microphone; autoplay"></iframe>

  <div class="sidebar">
    <div class="header">
      <h1>Drone Ground Station</h1>
      <div class="subtitle">Flight Test Telemetry • Raspberry Pi Platform</div>
    </div>

    <div class="clocks">
      <div>
        <div style="color:var(--text-muted);">UTC</div>
        <div id="utc">--:--:--</div>
      </div>
      <div style="text-align:right;">
        <div style="color:var(--text-muted);">Local</div>
        <div id="local">--:--:--</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Mission Timer</div>
      <div class="value" id="timer">00:00:00</div>
    </div>

    <div class="card log-controls">
      <button id="logBtn">START LOGGING</button>
      <div class="recording-indicator" id="recIndicator">
        <div class="dot"></div>
        <span>Recording flight data...</span>
      </div>
      <div style="font-size:12px; color:var(--text-muted);">
        Log saved to: <code style="background:rgba(0,0,0,0.3); padding:2px 6px; border-radius:4px;">/home/drone/flight_logs/</code>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Battery</div>
      <div class="row">
        <div class="value" id="battery">--<span class="unit">%</span></div>
        <div style="font-size:14px; color:var(--text-muted);" id="battery_raw"></div>
      </div>
      <div style="margin-top:8px; height:6px; background:#334155; border-radius:3px; overflow:hidden;">
        <div id="battery_bar" style="height:100%; width:0%; background:var(--primary); transition:width 0.6s ease;"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Temperature</div>
      <div class="value" id="temp">--<span class="unit"> °C</span></div>
    </div>

    <div class="card">
      <div class="card-title">Humidity</div>
      <div class="value" id="hum">--<span class="unit"> %</span></div>
    </div>

    <div class="card">
      <div class="card-title">Pressure</div>
      <div class="value" id="press">--<span class="unit"> hPa</span></div>
    </div>

    <div class="card">
      <div class="card-title">Gas Resistance</div>
      <div class="value" id="gas">--<span class="unit"> Ω</span></div>
    </div>

    <div class="status" id="status">Waiting for telemetry...</div>
  </div>

  <script>
    let logging = false;
    let missionStartTime = null;

    function updateClocks() {
      const now = new Date();
      document.getElementById('utc').textContent = now.toISOString().substr(11,8);
      document.getElementById('local').textContent = now.toTimeString().substr(0,8);
    }
    setInterval(updateClocks, 500);
    updateClocks();

    function updateTimer() {
      if (!missionStartTime) {
        document.getElementById('timer').textContent = '00:00:00';
        return;
      }
      const elapsed = Math.floor((Date.now() - missionStartTime) / 1000);
      const h = String(Math.floor(elapsed / 3600)).padStart(2,'0');
      const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2,'0');
      const s = String(elapsed % 60).padStart(2,'0');
      document.getElementById('timer').textContent = `${h}:${m}:${s}`;
    }
    setInterval(updateTimer, 500);

    document.getElementById('logBtn').addEventListener('click', async () => {
      const btn = document.getElementById('logBtn');
      const indicator = document.getElementById('recIndicator');

      if (!logging) {
        const name = prompt("Flight log name (optional):", "flight_" + new Date().toISOString().slice(0,10));
        const filename = name ? name.replace(/[^a-zA-Z0-9_-]/g, '_') : "unnamed";
        await fetch('/api/start_log', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({filename})
        });
        btn.textContent = 'STOP LOGGING';
        btn.classList.add('recording');
        indicator.classList.add('active');
        logging = true;
        missionStartTime = Date.now();
      } else {
        await fetch('/api/stop_log', {method: 'POST'});
        btn.textContent = 'START LOGGING';
        btn.classList.remove('recording');
        indicator.classList.remove('active');
        logging = false;
      }
    });

    async function refreshTelemetry() {
      try {
        const resp = await fetch('/api/telemetry');
        const data = await resp.json();

        document.getElementById('temp').textContent = data.temperature_c.toFixed(1);
        document.getElementById('hum').textContent = data.humidity.toFixed(1);
        document.getElementById('press').textContent = data.pressure_hpa.toFixed(1);
        document.getElementById('gas').textContent = Math.round(data.gas_ohms).toLocaleString();

        if (data.battery_percent !== null) {
          document.getElementById('battery').textContent = data.battery_percent;
          document.getElementById('battery_raw').textContent = data.battery_mv + ' mV';
          document.getElementById('battery_bar').style.width = data.battery_percent + '%';
        }

        document.getElementById('status').textContent = 
          `Telemetry OK • ${new Date(data.timestamp*1000).toLocaleString()}`;
      } catch (e) {
        document.getElementById('status').textContent = 'Telemetry lost • Reconnecting...';
      }
    }

    setInterval(refreshTelemetry, 1000);
    refreshTelemetry();
  </script>
</body>
</html>"""

@app.route("/")
def index():
    return INDEX_HTML

@app.route("/api/start_log", methods=["POST"])
def start_log():
    global current_log_file, current_log_handle
    data = request.get_json() or {}
    filename = data.get("filename", "flight") + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(LOG_DIR, filename + ".csv")
    
    current_log_file = filepath
    current_log_handle = open(filepath, "w")
    current_log_handle.write("timestamp_iso,timestamp_unix,temperature_c,humidity,pressure_hpa,gas_ohms,battery_percent,battery_mv\n")
    current_log_handle.flush()
    print(f"Started logging to {filepath}")
    return jsonify({"status": "logging", "file": filepath})

@app.route("/api/stop_log", methods=["POST"])
def stop_log():
    global current_log_file, current_log_handle
    if current_log_handle:
        current_log_handle.close()
        current_log_handle = None
        print(f"Stopped logging • Saved: {current_log_file}")
        current_log_file = None
    return jsonify({"status": "stopped"})

@app.route("/api/telemetry")
def telemetry():
    bme_data = get_bme_readings()
    battery_pct, battery_mv = get_battery_percent()

    response = jsonify(
        temperature_c=bme_data["temperature_c"],
        humidity=bme_data["humidity"],
        pressure_hpa=bme_data["pressure_hpa"],
        gas_ohms=bme_data["gas_ohms"],
        battery_percent=battery_pct,
        battery_mv=battery_mv,
        timestamp=time.time()
    )

    # Append to log if active
    if current_log_handle:
        iso = datetime.now().isoformat(timespec='seconds')
        line = f"{iso},{time.time():.3f},{bme_data['temperature_c']:.2f},{bme_data['humidity']:.1f},{bme_data['pressure_hpa']:.2f},{bme_data['gas_ohms']:.0f},{battery_pct or ''},{battery_mv or ''}\n"
        current_log_handle.write(line)
        current_log_handle.flush()

    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)