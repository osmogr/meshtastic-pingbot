# meshtastic-pingbot
Meshtastic Pingbot

## Features

This pingbot automatically responds to "ping", "hello", and "test" messages with connection information including RSSI, SNR, and hop count.

### SQLite Database Integration

The bot now maintains a SQLite database (`nodedb.sqlite`) to store information about all nodes in the mesh network:

- **Automatic nodedb download**: When the radio connects, the bot downloads the complete node database
- **Real-time updates**: Listens for `NODEINFO_APP` and `NEIGHBORINFO_APP` packets to keep node information current
- **Smart name resolution**: Uses stored long/short names from the database instead of displaying raw radio IDs
- **Automatic cleanup**: Removes nodes that haven't been seen for 30+ days to keep the database clean

### Commands

**Triggers (work in channels and DMs):**
- `ping`, `hello`, `test` - Responds with connection info (RSSI, SNR, hop count)

**DM-Only Commands:**
- `help`, `/help` - Shows available triggers and commands
- `about`, `/about` - Shows information about the bot

### Recent Improvements

- **SQLite Node Database**: Stores and manages node information with automatic updates from radio packets
- **Enhanced Name Display**: Shows friendly node names (long/short names) instead of radio IDs in all logs and messages
- **Separated Logging Functions**: Console and Discord logging are now separate functions (`log_console()`, `log_discord()`, `log_console_and_discord()`)
- **TCP Reconnection**: Automatic reconnection with exponential backoff when connection is lost
- **Health Endpoint**: `/health` endpoint returns JSON with connection status and message queue count
- **Security Enhancements**: Input validation, security headers, and improved error handling
- **Environment Configuration**: Configure via environment variables

## Install
- Clone the repo
- python3 -m venv .venv
- source venv/bin/activate
- pip3 install -r requirements.txt
 
## Configuration
Set these environment variables:
- `DEVICE_IP`: IP address of Meshtastic device (default: "192.168.1.50")
- `DEVICE_PORT`: TCP port (default: 4403) 
- `DATABASE_PATH`: Path to SQLite database file (default: "nodedb.sqlite")
- `DISCORD_WEBHOOK_URL`: Discord webhook URL for notifications (optional)

## API Endpoints
- `GET /`: Web interface showing live logs
- `GET /health`: Health check returning `{"connected": true/false, "queued": N}`

## Usage
```bash
git clone https://github.com/osmogr/meshtastic-pingbot
cd meshtastic-pingbot
python3 -m venv .venv
source venv/bin/activate
pip3 install -r requirements.txt
python main.py
```

The web interface will be available at http://localhost:5000
