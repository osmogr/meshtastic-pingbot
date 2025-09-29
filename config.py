"""Configuration module for Meshtastic PingBot."""

import os

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
# Connection type: "tcp" or "serial"
CONNECTION_TYPE = os.environ.get("CONNECTION_TYPE", "tcp").lower()

# TCP connection settings
DEVICE_IP = os.environ.get("MESHTASTIC_IP", "192.168.1.50")
DEVICE_PORT = int(os.environ.get("MESHTASTIC_PORT", "4403"))

# Serial connection settings
SERIAL_DEVICE = os.environ.get("SERIAL_DEVICE", None)  # e.g., "/dev/ttyUSB0" on Linux or "COM3" on Windows

# --- Database configuration ---
DATABASE_PATH = os.environ.get("DATABASE_PATH", "nodedb.sqlite")

# --- Discord webhook ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# --- Flask / SocketIO ---
MAX_LOG_LINES = 100

# --- Rate limiting ---
REPLY_COOLDOWN = 15  # seconds

# --- Traceroute system ---
TRACEROUTE_RATE_LIMIT = 30  # seconds between traceroutes globally
MAX_QUEUE_PER_USER = 2  # Maximum queued traceroutes per user

# --- Triggers and commands ---
TRIGGERS = ["ping", "hello", "test", "traceroute"]
DM_COMMANDS = ["help", "/help", "about", "/about"]