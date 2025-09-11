import meshtastic
import meshtastic.tcp_interface
import datetime
import time
import requests
from pubsub import pub
from flask import Flask, render_template_string
from flask_socketio import SocketIO

# --- ANSI color codes (console only) ---
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
WHITE = "\033[97m"

# --- Meshtastic device ---
DEVICE_IP = "192.168.1.50"
DEVICE_PORT = 4403  # Meshtastic TCP port (default, auto-used)

# --- Discord webhook ---
DISCORD_WEBHOOK_URL = ""

# --- Flask / SocketIO ---
app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading")
MAX_LOG_LINES = 100

HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Meshtastic Ping-Pong Logs</title>
  <style>
    body { font-family: monospace; background: #1e1e1e; color: #eee; margin: 0; padding: 0; }
    h2 { margin: 10px; color: #00ff00; }
    #logs { height: 90vh; overflow-y: scroll; padding: 10px; box-sizing: border-box; background: #1e1e1e; }
    .log { margin: 0.2em 0; white-space: pre-wrap; }
    .cyan { color: #00ffff; }
    .green { color: #00ff00; }
    .yellow { color: #ffff00; }
    .red { color: #ff5555; }
    .magenta { color: #ff00ff; }
    .blue { color: #5555ff; }
    .bold { font-weight: bold; }
  </style>
</head>
<body>
  <h2>Meshtastic Ping-Pong Logs</h2>
  <div id="logs"></div>
  <script src="//cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.min.js"></script>
  <script>
    var socket = io();
    var logsDiv = document.getElementById("logs");
    var logLines = [];
    const MAX_LOG_LINES = {{ max_lines }};
    socket.on("log_message", function(data) {
      logLines.push(data);
      if (logLines.length > MAX_LOG_LINES) logLines.shift();
      logsDiv.innerHTML = logLines.join('');
      logsDiv.scrollTop = logsDiv.scrollHeight;
    });
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, max_lines=MAX_LOG_LINES)

# --- Utilities ---
def timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def send_discord(msg: str):
    """Send logs to Discord webhook"""
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
    except Exception as e:
        print(f"Discord webhook error: {e}")

def log_console(msg, color="white", bold=False):
    colors = {
        "cyan": CYAN, "green": GREEN, "yellow": YELLOW,
        "red": RED, "magenta": MAGENTA, "blue": BLUE, "white": WHITE,
    }
    c = colors.get(color, WHITE)
    style = BOLD if bold else ""
    line = f"{style}{c}[{timestamp()}]{RESET} {msg}"
    print(line)
    send_discord(f"[{timestamp()}] {msg}")

def log_web(msg, color="white", bold=False):
    html_msg = f'<div class="log {color}{" bold" if bold else ""}">[{timestamp()}] {msg}</div>'
    socketio.emit("log_message", html_msg)

# --- Extractors ---
def extract_rssi_snr(packet):
    rssi = None
    snr = None
    if "rxMetadata" in packet and packet["rxMetadata"]:
        rssi = packet["rxMetadata"][0].get("rssi")
        snr = packet["rxMetadata"][0].get("snr")
    if rssi is None and "rxRssi" in packet:
        rssi = packet["rxRssi"]
    if snr is None and "rxSnr" in packet:
        snr = packet["rxSnr"]
    return rssi if rssi is not None else "N/A", snr if snr is not None else "N/A"

def get_sender_name(packet):
    if "decoded" in packet and "user" in packet["decoded"]:
        user = packet["decoded"]["user"]
        return user.get("longName") or user.get("shortName")
    return packet.get("fromId", "Unknown")

# --- Format helpers (ANSI & HTML colors) ---
def ansi_rssi(rssi):
    try:
        r = int(rssi)
        return f"{GREEN}{r}{RESET}" if r > -70 else f"{YELLOW}{r}{RESET}" if r > -85 else f"{RED}{r}{RESET}"
    except: return str(rssi)

def ansi_snr(snr):
    try:
        s = float(snr)
        return f"{GREEN}{s:.2f}{RESET}" if s > 10 else f"{YELLOW}{s:.2f}{RESET}" if s >= 0 else f"{RED}{s:.2f}{RESET}"
    except: return str(snr)

def ansi_hops(hop_count, hop_start):
    try:
        if hop_count == 0: return f"{GREEN}{hop_count}/{hop_start}{RESET}"
        if hop_count < hop_start/2: return f"{YELLOW}{hop_count}/{hop_start}{RESET}"
        return f"{RED}{hop_count}/{hop_start}{RESET}"
    except: return f"{hop_count}/{hop_start}"

def html_rssi(rssi):
    try:
        r = int(rssi)
        return f'<span class="green">{r}</span>' if r > -70 else f'<span class="yellow">{r}</span>' if r > -85 else f'<span class="red">{r}</span>'
    except: return str(rssi)

def html_snr(snr):
    try:
        s = float(snr)
        return f'<span class="green">{s:.2f}</span>' if s > 10 else f'<span class="yellow">{s:.2f}</span>' if s >= 0 else f'<span class="red">{s:.2f}</span>'
    except: return str(snr)

def html_hops(hop_count, hop_start):
    try:
        if hop_count == 0: return f'<span class="green">{hop_count}/{hop_start}</span>'
        if hop_count < hop_start/2: return f'<span class="yellow">{hop_count}/{hop_start}</span>'
        return f'<span class="red">{hop_count}/{hop_start}</span>'
    except: return f"{hop_count}/{hop_start}"

# --- Rate limiting ---
last_reply_time = {}
REPLY_COOLDOWN = 15  # seconds

# --- Packet handler ---
TRIGGERS = ["ping", "hello", "test"]

def on_receive(packet=None, interface=None, **kwargs):
    if not packet or "decoded" not in packet or "text" not in packet["decoded"]:
        return
    msg = packet["decoded"]["text"].strip().lower()
    sender = get_sender_name(packet)
    sender_id = packet.get("fromId", sender)

    log_console(f"Incoming from {sender}: '{msg}'", "cyan", True)
    log_web(f"Incoming from {sender}: '{msg}'", "cyan", True)

    if msg in TRIGGERS:
        now = time.time()
        if sender_id in last_reply_time and (now - last_reply_time[sender_id]) < REPLY_COOLDOWN:
            log_console(f"Rate-limited reply to {sender}", "yellow")
            log_web(f"Rate-limited reply to {sender}", "yellow")
            send_discord(f"[{timestamp()}] Rate-limited reply to {sender}")
            return

        last_reply_time[sender_id] = now
        rssi, snr = extract_rssi_snr(packet)
        hop_start = packet.get("hopStart", None)
        hop_limit = packet.get("hopLimit", None)
        hop_count = hop_start - hop_limit if hop_start and hop_limit else None

        reply = f"pong ({timestamp()}) RSSI: {rssi} SNR: {snr}"
        if hop_count is not None:
            reply += f" Hops: {hop_count}/{hop_start}"
        interface.sendText(reply, destinationId=packet["fromId"])

        console = f"Reply -> {sender}: {reply}"
        log_console(console, "green")
        log_web(console, "green")
#        send_discord(f"[{timestamp()}] {console}")
#    else:
#        log_console(f"Ignored message: '{msg}'", "blue")
#        log_web(f"Ignored message: '{msg}'", "blue")

# --- Connection handling ---
def connect_radio():
    backoff = 2
    while True:
        try:
            log_console("Attempting connection to radio...", "yellow")
            iface = meshtastic.tcp_interface.TCPInterface(hostname=DEVICE_IP)
            pub.subscribe(on_receive, "meshtastic.receive")
            log_console("Connected to Meshtastic radio", "green", True)
            return iface
        except Exception as e:
            log_console(f"Connection failed: {e}", "red")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

# --- Main ---
if __name__ == "__main__":
    interface = connect_radio()
    log_console("Starting web server...", "green", True)
    log_web("Starting web server...", "green", True)
    socketio.run(app, host="0.0.0.0", port=5000)
