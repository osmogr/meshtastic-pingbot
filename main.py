import meshtastic
import meshtastic.tcp_interface
import datetime
import time
import requests
import threading
import os
import sys
from pubsub import pub
from flask import Flask, render_template_string, request
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
DEVICE_IP = os.environ.get("MESHTASTIC_IP", "192.168.1.50")
DEVICE_PORT = int(os.environ.get("MESHTASTIC_PORT", "4403"))

# --- Discord webhook ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# --- Flask / SocketIO ---
app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading")
MAX_LOG_LINES = 100

# --- Connection and health tracking ---
is_connected = False
message_queue_count = 0
interface = None
local_radio_name = ""  # Local radio name (owner name or long name)

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

@app.route("/health")
def health():
    """Health check endpoint"""
    from flask import jsonify
    
    # Add security headers
    response = jsonify({
        "connected": is_connected,
        "queued": message_queue_count
    })
    response.headers['Content-Type'] = 'application/json'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

@app.after_request
def add_security_headers(response):
    """Add basic security headers"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# --- Utilities ---
def timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_local_radio_name(interface):
    """Get the local radio name (owner name or long name)"""
    try:
        if not interface:
            return ""
        
        # Try to get owner name first (preferred)
        try:
            my_user = interface.getMyUser()
            if my_user and hasattr(my_user, 'longName') and my_user.longName:
                return my_user.longName
        except Exception:
            pass
        
        # Try to get long name from node info
        try:
            my_node_info = interface.getMyNodeInfo()
            if my_node_info and hasattr(my_node_info, 'user') and my_node_info.user:
                if hasattr(my_node_info.user, 'longName') and my_node_info.user.longName:
                    return my_node_info.user.longName
        except Exception:
            pass
        
        # Try getLongName method directly
        try:
            long_name = interface.getLongName()
            if long_name:
                return long_name
        except Exception:
            pass
        
        return ""
    except Exception:
        return ""

def send_discord(msg: str):
    """Send logs to Discord webhook"""
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        # Basic input validation
        if len(msg) > 2000:  # Discord message limit
            msg = msg[:1997] + "..."
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
    except Exception as e:
        # Don't log the full error to avoid leaking sensitive information
        print(f"Discord webhook error: Connection failed")

def log_console(msg, color="white", bold=False):
    """Log message to console only"""
    colors = {
        "cyan": CYAN, "green": GREEN, "yellow": YELLOW,
        "red": RED, "magenta": MAGENTA, "blue": BLUE, "white": WHITE,
    }
    c = colors.get(color, WHITE)
    style = BOLD if bold else ""
    radio_part = f"[{local_radio_name}] " if local_radio_name else ""
    line = f"{style}{c}[{timestamp()}] {radio_part}{RESET}{msg}"
    print(line)

def log_discord(msg):
    """Log message to Discord only"""
    radio_part = f"[{local_radio_name}] " if local_radio_name else ""
    send_discord(f"[{timestamp()}] {radio_part}{msg}")

def log_console_and_discord(msg, color="white", bold=False):
    """Log message to both console and Discord"""
    log_console(msg, color, bold)
    log_discord(msg)

def log_web(msg, color="white", bold=False):
    radio_part = f"[{local_radio_name}] " if local_radio_name else ""
    html_msg = f'<div class="log {color}{" bold" if bold else ""}">[{timestamp()}] {radio_part}{msg}</div>'
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

def get_message_origin(packet):
    """Determine if message is from channel or direct message"""
    to_id = packet.get("toId", "")
    
    # Check if it's a broadcast/channel message
    if (to_id == meshtastic.BROADCAST_ADDR or 
        to_id == meshtastic.BROADCAST_NUM or
        str(to_id) == str(meshtastic.BROADCAST_NUM)):
        return "Channel"
    else:
        return "DM"

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

# --- Message splitting ---
MAX_MESSAGE_LENGTH = 200  # Meshtastic practical message limit

def split_message(text, max_length=MAX_MESSAGE_LENGTH):
    """
    Split a message into multiple parts, each under the maximum length.
    Try to break at natural boundaries (sentences, then words) to maximize readability.
    """
    if len(text) <= max_length:
        return [text]
    
    messages = []
    remaining = text.strip()
    
    while remaining:
        if len(remaining) <= max_length:
            messages.append(remaining)
            break
        
        # Find the best split point within max_length
        split_point = max_length
        
        # Try to split at sentence boundaries first (. ! ?)
        for i in range(max_length - 1, max_length // 2, -1):
            if remaining[i] in '.!?':
                # Check if there's space after the punctuation
                if i + 1 < len(remaining) and remaining[i + 1] == ' ':
                    split_point = i + 1
                    break
        
        # If no sentence boundary found, try to split at word boundaries
        if split_point == max_length:
            for i in range(max_length - 1, max_length // 2, -1):
                if remaining[i] == ' ':
                    split_point = i
                    break
        
        # If no good split point found, just split at max_length
        if split_point == max_length and len(remaining) > max_length:
            # Find last space before max_length to avoid breaking words
            for i in range(max_length - 1, 0, -1):
                if remaining[i] == ' ':
                    split_point = i
                    break
        
        # Extract the message part and add to list
        message_part = remaining[:split_point].rstrip()
        if message_part:
            messages.append(message_part)
        
        # Update remaining text
        remaining = remaining[split_point:].lstrip()
    
    return messages

def send_multiple_messages(interface, messages, destination_id):
    """
    Send multiple messages in sequence with proper error handling.
    Returns True if all messages were sent successfully, False otherwise.
    """
    global message_queue_count, is_connected
    
    if not interface or not is_connected:
        log_console_and_discord("Cannot send messages: not connected", "red")
        log_web("Cannot send messages: not connected", "red")
        return False
    
    success_count = 0
    total_messages = len(messages)
    
    for i, message in enumerate(messages, 1):
        try:
            message_queue_count += 1
            interface.sendText(message, destinationId=destination_id)
            message_queue_count -= 1
            success_count += 1
            
            # Small delay between messages to avoid overwhelming the radio
            if i < total_messages:
                time.sleep(0.5)
                
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            message_queue_count -= 1
            log_console_and_discord(f"Failed to send message {i}/{total_messages}: socket error (connection lost)", "red")
            log_web(f"Failed to send message {i}/{total_messages}: socket error (connection lost)", "red")
            handle_socket_error()
            # Trigger immediate cleanup in background
            with connection_lock:
                cleanup_interface()
            return False
        except Exception as e:
            message_queue_count -= 1
            log_console_and_discord(f"Failed to send message {i}/{total_messages}: operation error", "red")
            log_web(f"Failed to send message {i}/{total_messages}: operation error", "red")
            # Don't mark as disconnected for non-socket errors, but still fail the send
            return False
    
    return success_count == total_messages

# --- Packet handler ---
TRIGGERS = ["ping", "hello", "test"]
DM_COMMANDS = ["help", "/help", "about", "/about"]

def get_help_response():
    """Generate help response for DM help commands (optimized for message splitting)"""
    return (
        f"Meshtastic Pingbot Help:\n\n"
        f"I respond to these triggers in channels and DMs: {', '.join(TRIGGERS)}\n\n"
        f"DM-only commands: help, /help - Show this help message. "
        f"about, /about - Show information about this bot.\n\n"
        f"When you send a trigger, I'll respond with connection info including RSSI, SNR, and hop count."
    )

def get_about_response():
    """Generate about response for DM about commands (optimized for message splitting)"""
    return (
        f"Meshtastic Pingbot v1.0\n\n"
        f"I'm a simple ping-pong bot that helps test Meshtastic network connectivity. "
        f"Send me '{', '.join(TRIGGERS)}' and I'll respond with your connection quality metrics. "
        f"Features: RSSI and SNR reporting, Hop count tracking, Rate limiting (15s cooldown), "
        f"Channel and DM support. Built for the Meshtastic mesh networking community."
    )

def on_receive(packet=None, interface=None, **kwargs):
    global message_queue_count, is_connected
    
    if not packet or "decoded" not in packet or "text" not in packet["decoded"]:
        return
    
    # Basic input validation
    try:
        msg = packet["decoded"]["text"].strip().lower()
        if len(msg) > 200:  # Reasonable limit for Meshtastic messages
            return
        
        sender = get_sender_name(packet)
        sender_id = packet.get("fromId", sender)
        message_origin = get_message_origin(packet)
        
        # Sanitize sender name for logging
        if sender and len(sender) > 50:
            sender = sender[:47] + "..."

        log_console_and_discord(f"Incoming from {sender} via {message_origin}: '{msg}'", "cyan", True)
        log_web(f"Incoming from {sender} via {message_origin}: '{msg}'", "cyan", True)

        # Handle DM-only commands (help and about)
        if message_origin == "DM" and msg in DM_COMMANDS:
            now = time.time()
            if sender_id in last_reply_time and (now - last_reply_time[sender_id]) < REPLY_COOLDOWN:
                log_console_and_discord(f"Rate-limited reply to {sender}", "yellow")
                log_web(f"Rate-limited reply to {sender}", "yellow")
                return

            last_reply_time[sender_id] = now
            
            # Generate appropriate response based on command
            if msg in ["help", "/help"]:
                reply = get_help_response()
            elif msg in ["about", "/about"]:
                reply = get_about_response()
            
            # Split the reply into multiple messages if needed
            reply_messages = split_message(reply)
            
            # Send reply with connection error handling
            success = send_multiple_messages(interface, reply_messages, packet["fromId"])
            
            if success:
                console = f"DM Help/About -> {sender}: {msg} command ({len(reply_messages)} message{'s' if len(reply_messages) > 1 else ''})"
                log_console_and_discord(console, "green")
                log_web(console, "green")
            else:
                console = f"Failed to send DM Help/About -> {sender}: {msg} command"
                log_console_and_discord(console, "red")
                log_web(console, "red")
            return

        # Handle existing triggers (ping, hello, test) - work in both channels and DMs
        if msg in TRIGGERS:
            now = time.time()
            if sender_id in last_reply_time and (now - last_reply_time[sender_id]) < REPLY_COOLDOWN:
                log_console_and_discord(f"Rate-limited reply to {sender}", "yellow")
                log_web(f"Rate-limited reply to {sender}", "yellow")
                return

            last_reply_time[sender_id] = now
            rssi, snr = extract_rssi_snr(packet)
            hop_start = packet.get("hopStart", None)
            hop_limit = packet.get("hopLimit", None)
            hop_count = hop_start - hop_limit if hop_start and hop_limit else None

            reply = f"pong ({timestamp()}) RSSI: {rssi} SNR: {snr}"
            if hop_count is not None:
                reply += f" Hops: {hop_count}/{hop_start}"
            
            # Split the reply into multiple messages if needed (though ping responses are usually short)
            reply_messages = split_message(reply)
            
            # Send reply with connection error handling
            success = send_multiple_messages(interface, reply_messages, packet["fromId"])
            
            if success:
                console = f"Reply -> {sender}: {reply}"
                log_console_and_discord(console, "green")
                log_web(console, "green")
            else:
                console = f"Failed to send reply -> {sender}"
                log_console_and_discord(console, "red")
                log_web(console, "red")
            
    except Exception as e:
        # Log error without exposing sensitive details
        log_console_and_discord("Error processing incoming message", "red")
        log_web("Error processing incoming message", "red")

# --- Connection handling ---
connection_lock = threading.Lock()
reconnect_thread = None
shutdown_event = threading.Event()

# Track socket errors to detect heartbeat failures
socket_error_count = 0
socket_error_lock = threading.Lock()

def handle_socket_error():
    """Handle socket errors detected from any source"""
    global is_connected, socket_error_count
    
    with socket_error_lock:
        socket_error_count += 1
        if socket_error_count >= 1:  # Immediate response to socket errors
            if is_connected:
                log_console_and_discord("Socket error detected - marking connection as failed", "red")
                log_web("Socket error detected - marking connection as failed", "red")
                is_connected = False
                # Reset counter after marking disconnected
                socket_error_count = 0

def cleanup_interface():
    """Safely cleanup the interface connection"""
    global interface
    if interface:
        try:
            # First try to gracefully disconnect
            if hasattr(interface, '_sendDisconnect'):
                interface._sendDisconnect()
        except:
            # Ignore errors during disconnect
            pass
        
        try:
            # Then close the connection
            interface.close()
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Expected when connection is already broken
            pass
        except Exception:
            # Ignore other errors during cleanup
            pass
        finally:
            interface = None

def monitor_connection():
    """Monitor connection and reconnect if needed"""
    global is_connected, interface, reconnect_thread, local_radio_name
    
    backoff = 2
    max_backoff = 60
    
    while not shutdown_event.is_set():
        try:
            if not is_connected:
                log_console_and_discord("Attempting connection to radio...", "yellow")
                log_web("Attempting connection to radio...", "yellow")
                
                with connection_lock:
                    cleanup_interface()
                    
                    try:
                        interface = meshtastic.tcp_interface.TCPInterface(hostname=DEVICE_IP)
                        pub.subscribe(on_receive, "meshtastic.receive")
                        is_connected = True
                        backoff = 2  # Reset backoff on successful connection
                        
                        # Reset socket error count on successful connection
                        with socket_error_lock:
                            socket_error_count = 0
                        
                        # Get the local radio name after successful connection
                        try:
                            # Wait a moment for the interface to be fully ready
                            time.sleep(2)
                            local_radio_name = get_local_radio_name(interface)
                            if local_radio_name:
                                log_console_and_discord(f"Retrieved local radio name: {local_radio_name}", "cyan")
                                log_web(f"Retrieved local radio name: {local_radio_name}", "cyan")
                            else:
                                log_console_and_discord("Could not retrieve local radio name", "yellow")
                                log_web("Could not retrieve local radio name", "yellow")
                        except Exception as e:
                            log_console_and_discord("Failed to retrieve local radio name", "yellow")
                            log_web("Failed to retrieve local radio name", "yellow")
                            local_radio_name = ""
                        
                        log_console_and_discord("Connected to Meshtastic radio", "green", True)
                        log_web("Connected to Meshtastic radio", "green", True)
                        
                    except (BrokenPipeError, ConnectionResetError, OSError) as e:
                        log_console_and_discord("Connection failed: socket error during interface creation", "red")
                        log_web("Connection failed: socket error during interface creation", "red")
                        cleanup_interface()
                        raise
                    except Exception as e:
                        log_console_and_discord("Connection failed: unable to create interface", "red")
                        log_web("Connection failed: unable to create interface", "red")
                        cleanup_interface()
                        raise
                
            # Enhanced connection health check
            # This helps detect broken pipes and connection issues early
            connection_healthy = False
            try:
                if interface and is_connected:
                    # Try multiple lightweight operations to test connection health
                    interface.getMyNodeInfo()
                    # Small delay to allow any background thread errors to surface
                    time.sleep(1)
                    # If we get here without exception, connection seems healthy
                    connection_healthy = True
                    
            except (BrokenPipeError, ConnectionResetError, OSError):
                log_console_and_discord("Connection health check failed: socket error detected", "red")
                log_web("Connection health check failed: socket error detected", "red")
                handle_socket_error()
                with connection_lock:
                    cleanup_interface()
                continue
            except Exception as e:
                # For other exceptions, don't immediately fail the connection
                # but log the issue
                log_console_and_discord("Connection health check warning: operation failed", "yellow")
                log_web("Connection health check warning: operation failed", "yellow")
                connection_healthy = True  # Don't fail on non-socket errors
            
            if connection_healthy:
                time.sleep(10)  # Check more frequently to catch issues sooner
            
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            log_console_and_discord("Connection failed: socket error (radio disconnected)", "red")
            log_web("Connection failed: socket error (radio disconnected)", "red")
            handle_socket_error()
            
            with connection_lock:
                cleanup_interface()
            
            if not shutdown_event.is_set():
                log_console_and_discord(f"Retrying in {backoff} seconds...", "yellow")
                log_web(f"Retrying in {backoff} seconds...", "yellow")
                shutdown_event.wait(backoff)
                backoff = min(backoff * 2, max_backoff)
        except Exception as e:
            is_connected = False
            # Don't expose detailed error information
            log_console_and_discord("Connection failed: unable to connect to radio", "red")
            log_web("Connection failed: unable to connect to radio", "red")
            
            with connection_lock:
                cleanup_interface()
            
            if not shutdown_event.is_set():
                log_console_and_discord(f"Retrying in {backoff} seconds...", "yellow")
                log_web(f"Retrying in {backoff} seconds...", "yellow")
                shutdown_event.wait(backoff)
                backoff = min(backoff * 2, max_backoff)

def start_connection_monitor():
    """Start the connection monitoring thread"""
    global reconnect_thread
    if reconnect_thread is None or not reconnect_thread.is_alive():
        reconnect_thread = threading.Thread(target=monitor_connection, daemon=True)
        reconnect_thread.start()

def connect_radio():
    """Initialize radio connection with monitoring"""
    start_connection_monitor()
    
    # Wait for initial connection
    timeout = 60  # 60 seconds timeout for initial connection
    start_time = time.time()
    while not is_connected and (time.time() - start_time) < timeout:
        time.sleep(1)
    
    if not is_connected:
        log_console_and_discord("Failed to establish initial connection within timeout", "red")
        raise ConnectionError("Failed to connect to radio")
    
    return interface

# Override default exception handler to catch background thread errors
original_excepthook = sys.excepthook

def custom_excepthook(exc_type, exc_value, exc_traceback):
    """Custom exception handler to catch main thread socket errors"""
    if issubclass(exc_type, (BrokenPipeError, ConnectionResetError, OSError)):
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Main thread socket error detected: {exc_type.__name__}")
        try:
            handle_socket_error()
        except NameError:
            original_excepthook(exc_type, exc_value, exc_traceback)
    else:
        original_excepthook(exc_type, exc_value, exc_traceback)

def custom_threading_excepthook(args):
    """Custom exception handler for background thread socket errors"""
    if issubclass(args.exc_type, (BrokenPipeError, ConnectionResetError, OSError)):
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Background thread socket error detected: {args.exc_type.__name__}")
        try:
            handle_socket_error()
        except NameError:
            # If handle_socket_error is not yet defined, just print the error
            print(f"Socket error in thread {args.thread.name}: {args.exc_value}")

sys.excepthook = custom_excepthook
# Set threading excepthook if available (Python 3.8+)
if hasattr(threading, 'excepthook'):
    threading.excepthook = custom_threading_excepthook

# --- Main ---
if __name__ == "__main__":
    try:
        interface = connect_radio()
        log_console("Starting web server...", "green", True)
        log_web("Starting web server...", "green", True)
        socketio.run(app, host="0.0.0.0", port=5000)
    except KeyboardInterrupt:
        log_console("Shutting down...", "yellow")
        shutdown_event.set()
    except Exception as e:
        log_console(f"Fatal error: {e}", "red")
        shutdown_event.set()
    finally:
        # Clean shutdown
        cleanup_interface()
