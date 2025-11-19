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

# ---------- LOGGING — YOUR REAL PATH ----------
LOG_DIR = "/home/drone/GIT/groundstation/flight_logs"
os.makedirs(LOG_DIR, exist_ok=True)
current_log_file = None
current_log_handle = None

# ---------- SHELL CWD FOR CONSOLE ----------
current_cwd = os.path.expanduser("~")

# ---------- REALISTIC BATTERY ----------
def get_battery_percent():
    try:
        out = subprocess.check_output(
            ["lifepo4wered-cli", "get", "VBAT"], text=True
        ).strip()
        m = re.search(r"(\d+)", out)
        if not m:
            return None, None
        mv = int(m.group(1))
        if mv >= 3400:
            pct = 100
        elif mv >= 3330:
            pct = 75 + (mv - 3330) * 25 / 70
        elif mv >= 3300:
            pct = 50 + (mv - 3300) * 25 / 30
        elif mv >= 3250:
            pct = 20 + (mv - 3250) * 30 / 50
        elif mv >= 3200:
            pct = max(0, (mv - 3200) * 20 / 50)
        else:
            pct = 0
        return int(pct), mv
    except:
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
  <title>NAPALM Ground Station – Fire Detection</title>
  <style>
    :root {
      --bg:#111827;          /* dark grey/blue */
      --surface:#111827;
      --panel:#111827;
      --border:#374151;
      --text:#e5e7eb;
      --text-muted:#9ca3af;
      --primary:#38bdf8;
      --danger:#ef4444;
      --warning:#f59e0b;
      --green:#22c55e;
    }

    * {
      margin:0;
      padding:0;
      box-sizing:border-box;
    }

    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Mono", Menlo, monospace;
      background:var(--bg);
      color:var(--text);
      height:100vh;
      display:grid;
      grid-template-rows:56px 1fr;
    }

    header {
      background:#111827;
      border-bottom:1px solid var(--border);
      display:flex;
      align-items:center;
      padding:0 24px;
      font-size:18px;
      font-weight:500;
      color:#f9fafb;
    }

    .main {
      display:grid;
      grid-template-columns:320px 2.1fr 420px;
      height:calc(100vh - 56px);
    }

    iframe {
      width:100%;
      height:100%;
      border:none;
      background:#000;
      outline:none;
    }

    /* LEFT COLUMN: CONTROLS */

    .controls {
      background:var(--surface);
      border-right:1px solid var(--border);
      padding:16px;
      display:flex;
      flex-direction:column;
      gap:12px;
      overflow-y:auto;
    }

    .card {
      background:var(--panel);
      border:1px solid var(--border);
      padding:16px;
      box-shadow:none;
    }

    .card-title {
      font-size:11px;
      text-transform:uppercase;
      letter-spacing:1.5px;
      color:var(--text-muted);
      margin-bottom:8px;
    }

    .value {
      font-size:28px;
      font-weight:400;
    }

    .unit {
      font-size:14px;
      color:var(--text-muted);
      margin-left:4px;
    }

    button#logBtn {
      width:100%;
      padding:12px;
      font-size:14px;
      font-weight:600;
      border:none;
      background:var(--primary);
      color:white;
      cursor:pointer;
      text-align:center;
    }

    button#logBtn.recording {
      background:var(--danger);
      animation:pulse 2s infinite;
    }

    @keyframes pulse {
      0%,100%{opacity:1}
      50%{opacity:0.85}
    }

    .rec {
      display:none;
      align-items:center;
      gap:6px;
      color:var(--danger);
      margin-top:6px;
      font-size:12px;
    }

    .rec.active {
      display:flex;
    }

    .dot {
      width:8px;
      height:8px;
      background:var(--danger);
      border-radius:0;
      animation:blink 1.5s infinite;
    }

    @keyframes blink {
      0%,100%{opacity:1}
      50%{opacity:0.3}
    }

    .clocks {
      display:flex;
      justify-content:space-between;
      padding:8px 10px;
      background:#111827;
      border:1px solid var(--border);
      font-size:13px;
    }

    /* CENTER COLUMN: VIDEO + CONSOLE */

    .center-column {
      display:flex;
      flex-direction:column;
      gap:12px;
      padding:16px 16px 16px 0;
      overflow:hidden;
    }

    .video-container {
      flex:1.2;
      min-height:0;
      border:1px solid var(--border);
      background:#000;
    }

    .terminal-card {
      flex:1;
      min-height:0;
      display:flex;
      flex-direction:column;
    }

    .terminal {
      background:#111827;
      border:1px solid var(--border);
      padding:10px;
      font-family:'SF Mono', Menlo, monospace;
      font-size:12px;
      height:100%;
      display:flex;
      flex-direction:column;
    }

    #term-output {
      flex:1;
      overflow-y:auto;
      color:#c7d2fe;
      white-space:pre-wrap;
      margin-bottom:8px;
      padding-right:4px;
    }

    .prompt {
      color:#22c55e;
    }

    #term-output .error {
      color:#f97373;
    }

    .term-input {
      display:flex;
      gap:6px;
      align-items:center;
      border-top:1px solid var(--border);
      padding-top:6px;
    }

    .term-input span {
      color:#22c55e;
      font-size:12px;
    }

    #term-input {
      flex:1;
      background:transparent;
      border:none;
      color:#e5e7eb;
      outline:none;
      font-family:inherit;
      font-size:12px;
    }

    /* RIGHT COLUMN: DATA */

    .data-column {
      border-left:1px solid var(--border);
      padding:16px 16px 16px 0;
      display:flex;
      flex-direction:column;
      gap:12px;
      overflow-y:auto;
    }

    .metric-card .value {
      font-size:24px;
    }

    .battery-bar {
      height:6px;
      background:#111827;
      border:1px solid var(--border);
      margin-top:6px;
    }

    .battery-fill {
      height:100%;
      width:0%;
      background:var(--primary);
      transition:width 0.6s;
    }

    .status {
      font-size:12px;
      padding:8px;
      border:1px solid var(--border);
      background:#111827;
      color:var(--text-muted);
      text-align:left;
    }

    canvas {
      width:100%;
      height:80px;
      display:block;
      background:#111827;
    }
  </style>
</head>
<body>
  <header>NAPALM Ground Station – Fire Detection</header>

  <div class="main">
    <!-- LEFT: CONTROLS -->
    <div class="controls">
      <div class="card">
        <div class="card-title">Mission Timer</div>
        <div class="value" id="timer">00:00:00</div>
      </div>

      <div class="card">
        <div class="clocks">
          <div>
            <div style="color:var(--text-muted);font-size:11px;">UTC</div>
            <div id="utc">--:--:--</div>
          </div>
          <div style="text-align:right">
            <div style="color:var(--text-muted);font-size:11px;">Local</div>
            <div id="local">--:--:--</div>
          </div>
        </div>
      </div>

      <div class="card">
        <button id="logBtn">START LOGGING</button>
        <div class="rec" id="recIndicator">
          <div class="dot"></div>
          <span>Recording flight data...</span>
        </div>
        <div id="log-info" style="margin-top:6px;font-size:11px;color:var(--text-muted);"></div>
      </div>
    </div>

    <!-- CENTER: VIDEO + CONSOLE -->
    <div class="center-column">
      <div class="video-container">
        <iframe src="http://drone.local:8080/webrtc"
                allow="camera; microphone; autoplay"
                title=""></iframe>
      </div>

      <div class="card terminal-card">
        <div class="card-title">System Console</div>
        <div class="terminal">
          <div id="term-output">
            <span class="prompt"><span id="prompt-path">~</span>$</span> Ready. Type any command.
          </div>
          <div class="term-input">
            <span class="prompt"><span id="prompt-path-inline">~</span>$</span>
            <input type="text" id="term-input" autocomplete="off">
          </div>
        </div>
      </div>
    </div>

    <!-- RIGHT: DATA -->
    <div class="data-column">
      <div class="card metric-card">
        <div class="card-title">Battery</div>
        <div class="value">
          <span id="battery">--</span><span class="unit">%</span>
        </div>
        <div id="battery_raw" style="font-size:13px;color:var(--text-muted);margin-top:2px;"></div>
        <div class="battery-bar">
          <div class="battery-fill" id="battery_fill"></div>
        </div>
      </div>

      <div class="card metric-card">
        <div class="card-title">Temperature</div>
        <div class="value"><span id="temp">--</span><span class="unit"> °C</span></div>
      </div>

      <div class="card metric-card">
        <div class="card-title">Humidity</div>
        <div class="value"><span id="hum">--</span><span class="unit"> %</span></div>
      </div>

      <div class="card metric-card">
        <div class="card-title">Pressure</div>
        <div class="value"><span id="press">--</span><span class="unit"> hPa</span></div>
      </div>

      <div class="card metric-card">
        <div class="card-title">Gas Resistance</div>
        <div class="value"><span id="gas">--</span><span class="unit"> Ω</span></div>
      </div>

      <div class="card">
        <div class="card-title">Battery – Last 2 Minutes</div>
        <canvas id="batteryChart" width="400" height="80"></canvas>
      </div>

      <div class="card">
        <div class="card-title">Temperature – Last 2 Minutes</div>
        <canvas id="tempChart" width="400" height="80"></canvas>
      </div>

      <div class="card">
        <div class="card-title">Status</div>
        <div class="status" id="status">Initializing…</div>
      </div>
    </div>
  </div>

  <script>
    let logging = false;
    let missionStart = null;
    let elapsedSeconds = 0;  // total elapsed in seconds for the last mission
    let lastUpdate = 0;

    const out = document.getElementById('term-output');
    const inp = document.getElementById('term-input');
    const promptPath = document.getElementById('prompt-path');
    const promptPathInline = document.getElementById('prompt-path-inline');

    // Colors for charts from CSS vars
    const cssVars = getComputedStyle(document.documentElement);
    const colorPrimary = cssVars.getPropertyValue('--primary').trim() || '#38bdf8';
    const colorGreen = cssVars.getPropertyValue('--green').trim() || '#22c55e';
    const colorMuted = cssVars.getPropertyValue('--text-muted').trim() || '#9ca3af';

    // Simple history buffers for charts (approx 2 minutes at 1 Hz)
    const HISTORY_LEN = 120;
    const batteryHistory = [];
    const tempHistory = [];

    function pushHistory(arr, value) {
      if (value === null || value === undefined) return;
      arr.push(value);
      if (arr.length > HISTORY_LEN) arr.shift();
    }

    function drawSparkline(canvasId, data, color, fixedMin=null, fixedMax=null) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;

      ctx.clearRect(0, 0, w, h);

      // No data or single point: nothing to draw
      if (!data || data.length < 2) {
        // draw a subtle baseline
        ctx.strokeStyle = colorMuted;
        ctx.beginPath();
        ctx.moveTo(0, h - 1);
        ctx.lineTo(w, h - 1);
        ctx.stroke();
        return;
      }

      let min = fixedMin !== null ? fixedMin : Math.min.apply(null, data);
      let max = fixedMax !== null ? fixedMax : Math.max.apply(null, data);
      if (min === max) {
        // avoid division by zero
        min -= 1;
        max += 1;
      }

      const paddingX = 2;
      const paddingY = 4;
      const innerW = w - paddingX * 2;
      const innerH = h - paddingY * 2;

      const stepX = innerW / (data.length - 1);

      ctx.strokeStyle = colorMuted;
      ctx.beginPath();
      ctx.moveTo(paddingX, h - paddingY);
      ctx.lineTo(w - paddingX, h - paddingY);
      ctx.stroke();

      ctx.strokeStyle = color;
      ctx.beginPath();
      data.forEach((v, i) => {
        const x = paddingX + i * stepX;
        const norm = (v - min) / (max - min);
        const y = paddingY + (1 - norm) * innerH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    function setPromptPath(cwd) {
      if (!cwd) return;
      promptPath.textContent = cwd + ' ';
      promptPathInline.textContent = cwd + ' ';
    }

    // Clocks
    setInterval(() => {
      const n = new Date();
      document.getElementById('utc').textContent = n.toISOString().substr(11, 8);
      document.getElementById('local').textContent = n.toTimeString().substr(0, 8);
    }, 500);

    // Mission timer (stops when logging stops, keeps final value)
    setInterval(() => {
      let s = elapsedSeconds;
      if (missionStart) {
        s += Math.floor((Date.now() - missionStart) / 1000);
      }
      const h = String(Math.floor(s / 3600)).padStart(2, '0');
      const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
      const sec = String(s % 60).padStart(2, '0');
      document.getElementById('timer').textContent = `${h}:${m}:${sec}`;
    }, 500);

    // Logging button
    document.getElementById('logBtn').onclick = async () => {
      const b = document.getElementById('logBtn');
      const i = document.getElementById('recIndicator');
      const logInfo = document.getElementById('log-info');

      if (!logging) {
        const now = new Date();
        const defName =
          "fire_mission_" +
          now.getFullYear().toString() +
          String(now.getMonth() + 1).padStart(2, '0') +
          String(now.getDate()).padStart(2, '0') + "_" +
          String(now.getHours()).padStart(2, '0') +
          String(now.getMinutes()).padStart(2, '0') +
          String(now.getSeconds()).padStart(2, '0');

        const n = prompt("Log name (optional):", defName);
        const note = prompt("Mission note (optional):", "");

        const res = await fetch('/api/start_log', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({
            filename:(n || defName).replace(/[^a-zA-Z0-9_-]/g,'_'),
            note:note || ""
          })
        });

        const data = await res.json();
        if (data.logfile) {
          logInfo.textContent = 'Logging to: ' + data.logfile;
        } else {
          logInfo.textContent = '';
        }

        // New mission: reset elapsed and start timer
        elapsedSeconds = 0;
        missionStart = Date.now();

        b.textContent = 'STOP LOGGING';
        b.classList.add('recording');
        i.classList.add('active');
        logging = true;
      } else {
        // Stop mission timer, keep final time displayed
        if (missionStart) {
          elapsedSeconds += Math.floor((Date.now() - missionStart) / 1000);
          missionStart = null;
        }

        await fetch('/api/stop_log', {method:'POST'});
        if (logInfo.textContent.startsWith('Logging to: ')) {
          logInfo.textContent = 'Last log: ' + logInfo.textContent.replace('Logging to: ', '');
        }

        b.textContent = 'START LOGGING';
        b.classList.remove('recording');
        i.classList.remove('active');
        logging = false;
      }
    };

    // Terminal
    inp.addEventListener('keydown', async e => {
      if (e.key !== 'Enter') return;
      const c = inp.value.trim();
      if (!c) {
        inp.value = '';
        return;
      }

      out.innerHTML += `<br><span class="prompt">${promptPathInline.textContent}$</span> ${c}<br>`;

      const r = await fetch('/api/run_command', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({cmd:c})
      });
      const d = await r.json();
      if (d.cwd) {
        setPromptPath(d.cwd);
      }

      const t = (d.output || '').replace(/\\n/g,'<br>').replace(/\\t/g,'&nbsp;&nbsp;&nbsp;&nbsp;');
      out.innerHTML += `<span class="${d.error ? 'error' : ''}">${t || '(no output)'}</span><br>`;
      out.scrollTop = out.scrollHeight;
      inp.value = '';
    });

    // Initialize prompt cwd
    (async () => {
      try {
        const r = await fetch('/api/run_command', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({cmd:""})
        });
        const d = await r.json();
        if (d.cwd) setPromptPath(d.cwd);
      } catch (e) {
        // ignore
      }
    })();

    // Telemetry updater
    async function upd() {
      try {
        const r = await fetch('/api/telemetry');
        const d = await r.json();

        lastUpdate = Date.now();

        document.getElementById('temp').textContent = d.temperature_c.toFixed(1);
        document.getElementById('hum').textContent = d.humidity.toFixed(1);
        document.getElementById('press').textContent = d.pressure_hpa.toFixed(1);
        document.getElementById('gas').textContent = Math.round(d.gas_ohms).toLocaleString();

        if (d.battery_percent !== null) {
          const pct = d.battery_percent;
          const fill = document.getElementById('battery_fill');
          const val = document.getElementById('battery');

          val.textContent = pct;
          document.getElementById('battery_raw').textContent = d.battery_mv + ' mV';
          fill.style.width = pct + '%';

          let color = colorPrimary;
          if (pct <= 20) color = cssVars.getPropertyValue('--danger').trim() || '#ef4444';
          else if (pct <= 40) color = cssVars.getPropertyValue('--warning').trim() || '#f59e0b';
          fill.style.background = color;

          pushHistory(batteryHistory, pct);
        }

        pushHistory(tempHistory, d.temperature_c);

        let status = 'Telemetry OK';
        if (d.battery_percent !== null && d.battery_percent <= 20) {
          status += ' • LOW BATTERY';
        }

        document.getElementById('status').textContent =
          status + ' • ' + new Date(d.timestamp * 1000).toLocaleString().slice(0, 24);

        // Redraw charts
        drawSparkline('batteryChart', batteryHistory, colorPrimary, 0, 100);
        drawSparkline('tempChart', tempHistory, colorGreen, null, null);
      } catch {
        document.getElementById('status').textContent = 'Connection lost';
      }
    }

    setInterval(upd, 1000);
    upd();

    // Stale telemetry watchdog
    setInterval(() => {
      if (lastUpdate && Date.now() - lastUpdate > 5000) {
        const s = document.getElementById('status');
        if (!s.textContent.includes('Stale')) {
          s.textContent += ' • Telemetry stale';
        }
      }
    }, 2000);

    // Focus terminal on load
    window.addEventListener('load', () => {
      inp.focus();
    });

    // 'L' hotkey to toggle logging (ignore if typing in an input)
    window.addEventListener('keydown', e => {
      if (e.key === 'l' && !(e.target && e.target.tagName === 'INPUT')) {
        document.getElementById('logBtn').click();
      }
    });

    // Warn before leaving if logging is active
    window.addEventListener('beforeunload', function (e) {
      if (!logging) return;
      e.preventDefault();
      e.returnValue = '';
    });
  </script>
</body>
</html>"""

# ———————— ROUTES ————————

@app.route("/")
def index():
    return INDEX_HTML

@app.route("/api/start_log", methods=["POST"])
def start_log():
    global current_log_file, current_log_handle
    data = request.get_json() or {}
    mission_note = (data.get("note") or "").replace("\n", " ")
    filename = (data.get("filename", "fire_mission") + "_" +
                datetime.now().strftime("%Y%m%d_%H%M%S"))
    filepath = os.path.join(LOG_DIR, filename + ".csv")
    current_log_file = filepath
    current_log_handle = open(filepath, "w")
    if mission_note:
        current_log_handle.write(f"# note: {mission_note}\n")
    current_log_handle.write(
        "timestamp_iso,timestamp_unix,temperature_c,humidity,pressure_hpa,"
        "gas_ohms,battery_percent,battery_mv\n"
    )
    current_log_handle.flush()
    print(f"Logging → {filepath}")
    return jsonify(success=True, logfile=filepath)

@app.route("/api/stop_log", methods=["POST"])
def stop_log():
    global current_log_file, current_log_handle
    if current_log_handle:
        current_log_handle.close()
        current_log_handle = None
        print(f"Log saved → {current_log_file}")
    return jsonify(success=True)

@app.route("/api/run_command", methods=["POST"])
def run_command():
    global current_cwd
    cmd = request.json.get("cmd", "")

    # Empty cmd: just return current cwd (for prompt init)
    if cmd is None or cmd.strip() == "":
        return jsonify(output="", error=False, cwd=current_cwd)

    if len(cmd) > 200:
        return jsonify(output="Command too long", error=True, cwd=current_cwd)

    stripped = cmd.strip()

    # Handle "cd" commands to persist working directory
    if stripped.startswith("cd"):
        parts = stripped.split(None, 1)
        target = parts[1] if len(parts) > 1 else os.path.expanduser("~")
        try:
            if not os.path.isabs(target):
                new_dir = os.path.abspath(os.path.join(current_cwd, target))
            else:
                new_dir = target
            current_cwd = new_dir
            return jsonify(output="", error=False, cwd=current_cwd)
        except Exception as e:
            return jsonify(output=str(e), error=True, cwd=current_cwd)

    dangerous = [
        "rm -rf", "mkfs", "dd if=", ":(){", "sudo rm",
        "shutdown", "halt", "mklabel"
    ]
    # allow "reboot" explicitly if you want; everything else here is blocked
    if any(d in cmd.lower() for d in dangerous):
        if "reboot" not in cmd.lower():
            return jsonify(output="Blocked: dangerous command", error=True, cwd=current_cwd)

    try:
        result = subprocess.check_output(
            cmd, shell=True, text=True, timeout=15, cwd=current_cwd
        )
        return jsonify(output=result, error=False, cwd=current_cwd)
    except Exception as e:
        return jsonify(output=str(e), error=True, cwd=current_cwd)

@app.route("/api/telemetry")
def telemetry():
    bme_data = get_bme_readings()
    battery_pct, battery_mv = get_battery_percent()
    resp = jsonify(
        temperature_c=bme_data["temperature_c"],
        humidity=bme_data["humidity"],
        pressure_hpa=bme_data["pressure_hpa"],
        gas_ohms=bme_data["gas_ohms"],
        battery_percent=battery_pct,
        battery_mv=battery_mv,
        timestamp=time.time()
    )
    if current_log_handle:
        line = (
            f"{datetime.now().isoformat(timespec='seconds')},"
            f"{time.time():.3f},"
            f"{bme_data['temperature_c']:.2f},"
            f"{bme_data['humidity']:.1f},"
            f"{bme_data['pressure_hpa']:.2f},"
            f"{bme_data['gas_ohms']:.0f},"
            f"{battery_pct or ''},"
            f"{battery_mv or ''}\n"
        )
        current_log_handle.write(line)
        current_log_handle.flush()
    return resp

# ———————— START SERVER ————————
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
