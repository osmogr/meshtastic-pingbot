"""Logging utilities for Meshtastic PingBot."""

import datetime
import requests
from config import (
    RESET, BOLD, CYAN, GREEN, YELLOW, RED, MAGENTA, BLUE, WHITE,
    DISCORD_WEBHOOK_URL
)

# Global variables (to be set by main.py)
local_radio_name = ""
socketio = None


def timestamp():
    """Generate a timestamp string."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def send_discord(msg: str):
    """Send logs to Discord webhook"""
    if not DISCORD_WEBHOOK_URL:
        return
    
    try:
        payload = {"content": msg}
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to send Discord message: {e}")


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
    """Log message to web interface"""
    if socketio is None:
        return
    
    radio_part = f"[{local_radio_name}] " if local_radio_name else ""
    html_msg = f'<div class="log {color}{" bold" if bold else ""}">[{timestamp()}] {radio_part}{msg}</div>'
    socketio.emit("log_message", html_msg)


def set_local_radio_name(name):
    """Set the local radio name for logging"""
    global local_radio_name
    local_radio_name = name


def set_socketio(socketio_instance):
    """Set the SocketIO instance for web logging"""
    global socketio
    socketio = socketio_instance