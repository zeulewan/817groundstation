from flask import Flask, jsonify, request
import time
import subprocess
import re
import board
import busio
import adafruit_bme680
import os
import shutil
from datetime import datetime

# ---------- BME680 SETUP ----------
i2c = busio.I2C(board.SCL, board.SDA)
bme = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=0x77)

# ---------- LOGGING — YOUR REAL PATH ----------
LOG_DIR = "/home/drone/GIT/groundstation/flight_logs"
os.makedirs(LOG_DIR, exist_ok=True)
current_log_file = None
current_log_handle = None

# ---------- SHELL CWD (for /api/run_command, if you still want it) ----------
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

# ---------- SYSTEM STATS (GROUND STATION) ----------
def get_system_stats():
    cpu_temp_c = None
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            cpu_temp_c = int(f.read().strip()) / 1000.0
    except:
        pass

    load_1m = load_5m = load_15m = None
    try:
        load_1m, load_5m, load_15m = os.getloadavg()
    except:
        pass

    mem_total_kb = None
    mem_avail_kb = None
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail_kb = int(line.split()[1])
    except:
        pass

    mem_total_mb = mem_used_mb = None
    if mem_total_kb and mem_avail_kb:
        mem_total_mb = mem_total_kb / 1024.0
        mem_used_mb = (mem_total_kb - mem_avail_kb) / 1024.0

    disk_free_gb = disk_used_pct = None
    try:
        total, used, free = shutil.disk_usage(LOG_DIR)
        disk_free_gb = free / (1024.0 ** 3)
        disk_used_pct = used * 100.0 / total
    except:
        pass

    ip_address = None
    try:
        ip_out = subprocess.check_output(["hostname", "-I"], text=True).strip()
        if ip_out:
            ip_address = ip_out.split()[0]
    except:
        pass

    wifi_rssi_dbm = None
    try:
        iw = subprocess.check_output(
            ["iwconfig", "wlan0"],
            text=True,
            stderr=subprocess.DEVNULL
        )
        m = re.search(r"Signal level=(-?\d+)\s*dBm", iw)
        if m:
            wifi_rssi_dbm = int(m.group(1))
    except:
        pass

    return {
        "cpu_temp_c": cpu_temp_c,
        "load_1m": load_1m,
        "mem_total_mb": mem_total_mb,
        "mem_used_mb": mem_used_mb,
        "disk_free_gb": disk_free_gb,
        "disk_used_pct": disk_used_pct,
        "ip_address": ip_address,
        "wifi_rssi_dbm": wifi_rssi_dbm,
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
      --bg:#111827;
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
      grid-template-columns:320px 2.1fr 400px;
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
      padding:12px;
      display:flex;
      flex-direction:column;
      gap:8px;
      overflow-y:auto;
    }

    .card {
      background:var(--panel);
      border:1px solid var(--border);
      padding:12px;
      box-shadow:none;
    }

    .card-title {
      font-size:11px;
      text-transform:uppercase;
      letter-spacing:1.5px;
      color:var(--text-muted);
      margin-bottom:6px;
    }

    .value {
      font-size:24px;
      font-weight:400;
    }

    .unit {
      font-size:12px;
      color:var(--text-muted);
      margin-left:4px;
    }

    button#logBtn {
      width:100%;
      padding:10px;
      font-size:13px;
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
      margin-top:4px;
      font-size:11px;
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
      padding:6px 8px;
      background:#111827;
      border:1px solid var(--border);
      font-size:12px;
    }

    .sys-row {
      font-size:12px;
      color:var(--text-muted);
      line-height:1.4;
    }

    .notes-textarea {
      width:100%;
      height:70px;
      background:#111827;
      border:1px solid var(--border);
      color:var(--text);
      font-size:12px;
      padding:6px;
      outline:none;
      resize:none;
    }

    /* CENTER COLUMN: VIDEO + LIVE LOG */

    .center-column {
      display:flex;
      flex-direction:column;
      gap:8px;
      padding:12px 12px 12px 0;
      overflow:hidden;
    }

    .video-container {
      flex:1.2;
      min-height:0;
      border:1px solid var(--border);
      background:#000;
    }

    .log-card {
      flex:1;
      min-height:0;
      display:flex;
      flex-direction:column;
    }

    .log-container {
      border:1px solid var(--border);
      background:#111827;
      margin-top:4px;
      height:100%;
      display:flex;
      flex-direction:column;
      font-size:11px;
    }

    .log-header {
      padding:4px 6px;
      border-bottom:1px solid var(--border);
      color:var(--text-muted);
    }

    .log-body {
      flex:1;
      overflow-y:auto;
    }

    .log-table {
      width:100%;
      border-collapse:collapse;
      font-family:'SF Mono', Menlo, monospace;
      font-size:11px;
    }

    .log-table thead {
      position:sticky;
      top:0;
      background:#111827;
    }

    .log-table th,
    .log-table td {
      padding:2px 4px;
      border-bottom:1px solid #1f2933;
      white-space:nowrap;
    }

    .log-table th {
      text-align:left;
      color:var(--text-muted);
      font-weight:400;
    }

    .log-table tbody tr:nth-child(even) {
      background:#101623;
    }

    /* RIGHT COLUMN: DATA */

    .data-column {
      border-left:1px solid var(--border);
      padding:12px 12px 12px 0;
      display:flex;
      flex-direction:column;
      gap:8px;
      overflow-y:hidden;
    }

    .metric-card .value {
      font-size:20px;
    }

    .battery-bar {
      height:6px;
      background:#111827;
      border:1px solid var(--border);
      margin-top:4px;
    }

    .battery-fill {
      height:100%;
      width:0%;
      background:var(--primary);
      transition:width 0.4s;
    }

    .status {
      font-size:11px;
      padding:6px;
      border:1px solid var(--border);
      background:#111827;
      color:var(--text-muted);
      text-align:left;
    }

    .compact-grid {
      display:grid;
      grid-template-columns:1fr 1fr;
      gap:4px 8px;
      font-size:12px;
      color:var(--text-muted);
    }

    .compact-grid div span {
      color:var(--text);
      margin-left:2px;
    }

    canvas {
      width:100%;
      height:50px;
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
        <div id="log-info" style="margin-top:4px;font-size:11px;color:var(--text-muted);"></div>
      </div>

      <div class="card">
        <div class="card-title">System</div>
        <div class="sys-row">CPU: <span id="sys-cpu-temp">--</span></div>
        <div class="sys-row">Load: <span id="sys-load">--</span></div>
        <div class="sys-row">RAM: <span id="sys-ram">--</span></div>
        <div class="sys-row">Disk: <span id="sys-disk">--</span></div>
      </div>

      <div class="card">
        <div class="card-title">Link</div>
        <div class="sys-row">Latency: <span id="link-lat">--</span></div>
        <div class="sys-row">Loss (30s): <span id="link-loss">--</span></div>
      </div>

      <div class="card">
        <div class="card-title">Network</div>
        <div class="sys-row">IP: <span id="net-ip">--</span></div>
        <div class="sys-row">RSSI: <span id="net-rssi">--</span></div>
      </div>

      <div class="card">
        <div class="card-title">Mission Notes</div>
        <textarea id="mission-notes" class="notes-textarea" placeholder="Notes, location, operator..."></textarea>
      </div>
    </div>

    <!-- CENTER: VIDEO + LIVE LOG -->
    <div class="center-column">
      <div class="video-container">
        <iframe src="http://drone.local:8080/webrtc"
                allow="camera; microphone; autoplay"
                title=""></iframe>
      </div>

      <div class="card log-card">
        <div class="card-title">Live Log</div>
        <div class="log-container">
          <div class="log-header">Streaming recent logged samples while recording</div>
          <div class="log-body" id="live-log-container">
            <table class="log-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Temp (°C)</th>
                  <th>Hum (%)</th>
                  <th>Press (hPa)</th>
                  <th>Gas (Ω)</th>
                  <th>Bat (%)</th>
                  <th>Bat (mV)</th>
                </tr>
              </thead>
              <tbody id="live-log-body"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- RIGHT: DATA (compact, no scroll) -->
    <div class="data-column">
      <div class="card metric-card">
        <div class="card-title">Battery</div>
        <div class="value">
          <span id="battery">--</span><span class="unit">%</span>
        </div>
        <div id="battery_raw" style="font-size:11px;color:var(--text-muted);margin-top:2px;"></div>
        <div class="battery-bar">
          <div class="battery-fill" id="battery_fill"></div>
        </div>
        <canvas id="batteryChart" width="380" height="50"></canvas>
      </div>

      <div class="card metric-card">
        <div class="card-title">Temperature</div>
        <div class="value"><span id="temp">--</span><span class="unit"> °C</span></div>
        <canvas id="tempChart" width="380" height="50"></canvas>
      </div>

      <div class="card">
        <div class="card-title">Environment</div>
        <div class="compact-grid">
          <div>Humidity<span id="hum">--</span><span class="unit">%</span></div>
          <div>Pressure<span id="press">--</span><span class="unit">hPa</span></div>
          <div>Gas<span id="gas">--</span><span class="unit">Ω</span></div>
        </div>
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
    let elapsedSeconds = 0;
    let lastUpdate = 0;

    const cssVars = getComputedStyle(document.documentElement);
    const colorPrimary = cssVars.getPropertyValue('--primary').trim() || '#38bdf8';
    const colorGreen   = cssVars.getPropertyValue('--green').trim()   || '#22c55e';
    const colorMuted   = cssVars.getPropertyValue('--text-muted').trim() || '#9ca3af';
    const colorDanger  = cssVars.getPropertyValue('--danger').trim()  || '#ef4444';
    const colorWarning = cssVars.getPropertyValue('--warning').trim() || '#f59e0b';

    const HISTORY_LEN = 120;
    const batteryHistory = [];
    const tempHistory = [];
    const linkHistory = [];
    const MAX_LINK_SAMPLES = 30;

    function pushHistory(arr, value) {
      if (value === null || value === undefined) return;
      arr.push(value);
      if (arr.length > HISTORY_LEN) arr.shift();
    }

    function drawSparkline(canvasId, data, color, fixedMin = null, fixedMax = null) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;

      ctx.clearRect(0, 0, w, h);

      if (!data || data.length < 2) {
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
        min -= 1;
        max += 1;
      }

      const paddingX = 2;
      const paddingY = 3;
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

    function recordLink(ok) {
      linkHistory.push({ ok });
      if (linkHistory.length > MAX_LINK_SAMPLES) linkHistory.shift();
      const total = linkHistory.length;
      if (total === 0) {
        document.getElementById('link-loss').textContent = '--';
        return;
      }
      const good = linkHistory.filter(x => x.ok).length;
      const lossPct = 100 * (total - good) / total;
      document.getElementById('link-loss').textContent = lossPct.toFixed(0) + '%';
    }

    setInterval(() => {
      const n = new Date();
      document.getElementById('utc').textContent   = n.toISOString().substr(11, 8);
      document.getElementById('local').textContent = n.toTimeString().substr(0, 8);
    }, 500);

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

        elapsedSeconds = 0;
        missionStart = Date.now();

        b.textContent = 'STOP LOGGING';
        b.classList.add('recording');
        i.classList.add('active');
        logging = true;
      } else {
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

    async function upd() {
      const start = performance.now();
      try {
        const r = await fetch('/api/telemetry');
        const d = await r.json();

        const latency = performance.now() - start;
        document.getElementById('link-lat').textContent = latency.toFixed(0) + ' ms';
        recordLink(true);

        lastUpdate = Date.now();

        document.getElementById('temp').textContent  = d.temperature_c.toFixed(1);
        document.getElementById('hum').textContent   = d.humidity.toFixed(1);
        document.getElementById('press').textContent = d.pressure_hpa.toFixed(1);
        document.getElementById('gas').textContent   = Math.round(d.gas_ohms).toLocaleString();

        if (d.battery_percent !== null) {
          const pct  = d.battery_percent;
          const fill = document.getElementById('battery_fill');
          const val  = document.getElementById('battery');

          val.textContent = pct;
          document.getElementById('battery_raw').textContent = d.battery_mv + ' mV';
          fill.style.width = pct + '%';

          let color = colorPrimary;
          if (pct <= 20)      color = colorDanger;
          else if (pct <= 40) color = colorWarning;
          fill.style.background = color;

          pushHistory(batteryHistory, pct);
        }

        pushHistory(tempHistory, d.temperature_c);

        if (d.cpu_temp_c != null) {
          document.getElementById('sys-cpu-temp').textContent = d.cpu_temp_c.toFixed(1) + '°C';
        } else {
          document.getElementById('sys-cpu-temp').textContent = '--';
        }

        if (d.load_1m != null) {
          document.getElementById('sys-load').textContent = d.load_1m.toFixed(2);
        } else {
          document.getElementById('sys-load').textContent = '--';
        }

        if (d.mem_total_mb != null && d.mem_used_mb != null) {
          document.getElementById('sys-ram').textContent =
            d.mem_used_mb.toFixed(0) + ' / ' + d.mem_total_mb.toFixed(0) + ' MB';
        } else {
          document.getElementById('sys-ram').textContent = '--';
        }

        if (d.disk_free_gb != null && d.disk_used_pct != null) {
          document.getElementById('sys-disk').textContent =
            d.disk_used_pct.toFixed(0) + '% • ' + d.disk_free_gb.toFixed(1) + ' GB free';
        } else {
          document.getElementById('sys-disk').textContent = '--';
        }

        document.getElementById('net-ip').textContent = d.ip_address || '--';
        document.getElementById('net-rssi').textContent =
          (d.wifi_rssi_dbm != null) ? d.wifi_rssi_dbm + ' dBm' : '--';

        let status = 'Telemetry OK';
        if (d.battery_percent !== null && d.battery_percent <= 20) {
          status += ' • LOW BATTERY';
        }

        document.getElementById('status').textContent =
          status + ' • ' + new Date(d.timestamp * 1000).toLocaleString().slice(0, 24);

        drawSparkline('batteryChart', batteryHistory, colorPrimary, 0, 100);
        drawSparkline('tempChart',    tempHistory,    colorGreen,  null, null);

        if (logging) {
          const tbody = document.getElementById('live-log-body');
          const tr = document.createElement('tr');
          const t = new Date(d.timestamp * 1000);
          const timeStr = t.toISOString().slice(11, 19);

          tr.innerHTML = `
            <td>${timeStr}</td>
            <td>${d.temperature_c.toFixed(2)}</td>
            <td>${d.humidity.toFixed(1)}</td>
            <td>${d.pressure_hpa.toFixed(1)}</td>
            <td>${Math.round(d.gas_ohms)}</td>
            <td>${d.battery_percent !== null ? d.battery_percent : ''}</td>
            <td>${d.battery_mv !== null ? d.battery_mv : ''}</td>
          `;
          tbody.appendChild(tr);

          while (tbody.rows.length > HISTORY_LEN) {
            tbody.deleteRow(0);
          }

          const container = document.getElementById('live-log-container');
          container.scrollTop = container.scrollHeight;
        }
      } catch (e) {
        document.getElementById('status').textContent = 'Connection lost';
        recordLink(false);
      }
    }

    setInterval(upd, 1000);
    upd();

    setInterval(() => {
      if (lastUpdate && Date.now() - lastUpdate > 5000) {
        const s = document.getElementById('status');
        if (!s.textContent.includes('Stale')) {
          s.textContent += ' • Telemetry stale';
        }
      }
    }, 2000);

    window.addEventListener('load', () => {
      const notes = localStorage.getItem('missionNotes');
      if (notes !== null) {
        document.getElementById('mission-notes').value = notes;
      }
    });

    document.getElementById('mission-notes').addEventListener('input', e => {
      localStorage.setItem('missionNotes', e.target.value);
    });

    window.addEventListener('keydown', e => {
      const tag = e.target && e.target.tagName;
      if (e.key === 'l' && tag !== 'INPUT' && tag !== 'TEXTAREA') {
        document.getElementById('logBtn').click();
      }
    });

    window.addEventListener('beforeunload', function (e) {
      if (!logging) return;
      e.preventDefault();
      e.returnValue = '';
    });
  </script>
</body>
</html>"""

# ---------- ROUTES ----------

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

    if cmd is None or cmd.strip() == "":
        return jsonify(output="", error=False, cwd=current_cwd)

    if len(cmd) > 200:
        return jsonify(output="Command too long", error=True, cwd=current_cwd)

    stripped = cmd.strip()

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
    sys_stats = get_system_stats()
    resp = jsonify(
        temperature_c=bme_data["temperature_c"],
        humidity=bme_data["humidity"],
        pressure_hpa=bme_data["pressure_hpa"],
        gas_ohms=bme_data["gas_ohms"],
        battery_percent=battery_pct,
        battery_mv=battery_mv,
        timestamp=time.time(),
        **sys_stats
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

# ---------- START SERVER ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
