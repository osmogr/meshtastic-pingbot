# meshtastic-pingbot
Meshtastic Pingbot

## Features

This pingbot automatically responds to "ping", "hello", and "test" messages with connection information including RSSI, SNR, and hop count.

### SQLite Database Integration

The bot now maintains a SQLite database (`nodedb.sqlite`) to store information about all nodes in the mesh network:

- **Enhanced nodedb download**: Downloads the complete node database using multiple data sources for maximum coverage
- **Dual-source processing**: Extracts nodes from both `interface.nodes` (by ID) and `interface.nodesByNum` (by number)
- **Comprehensive data extraction**: Captures all available node information including names, hardware, role, licensing, and network metrics
- **Automatic retry & refresh**: Retries failed downloads and periodically refreshes every 6 hours
- **Real-time statistics**: Monitors database health with completion rates and data quality metrics
- **Real-time updates**: Listens for `NODEINFO_APP` and `NEIGHBORINFO_APP` packets to keep node information current
- **Smart name resolution**: Uses stored long/short names from the database instead of displaying raw radio IDs
- **Automatic cleanup**: Removes nodes that haven't been seen for 30+ days to keep the database clean
- **Advanced debugging**: Detailed logging helps diagnose nodedb download issues

### Commands

**Triggers (work in channels and DMs):**
- `ping`, `hello`, `test` - Responds with connection info (RSSI, SNR, hop count)
- `ping N` - Responds N times (where N is 1-5) with connection info (Same message repeated N times)
- `traceroute` - Performs Meshtastic network path trace (rate limited: 30s globally, max 2 queued per user)

**DM-Only Commands:**
- `help`, `/help` - Shows available triggers and commands
- `about`, `/about` - Shows information about the bot

### Recent Improvements

- **Enhanced NodeDB Download**: Comprehensive node data extraction from multiple sources with retry logic
- **Dual Source Node Processing**: Extracts nodes from both `interface.nodes` and `interface.nodesByNum` for maximum coverage
- **Periodic NodeDB Refresh**: Automatic refresh every 6 hours to catch new nodes and updates
- **Advanced Debugging**: Detailed logging of node data structures and extraction process
- **Database Statistics**: Real-time monitoring of node database health and completion rates
- **Robust Error Handling**: Individual node failures don't stop entire nodedb download
- **SQLite Node Database**: Stores and manages node information with automatic updates from radio packets
- **Enhanced Name Display**: Shows friendly node names (long/short names) instead of radio IDs in all logs and messages
- **Separated Logging Functions**: Console and Discord logging are now separate functions (`log_console()`, `log_discord()`, `log_console_and_discord()`)
- **Serial and TCP Connection Support**: Connect via TCP network or serial USB connection with automatic device detection
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

### Connection Settings
- `CONNECTION_TYPE`: Connection type - "tcp" or "serial" (default: "tcp")

### TCP Connection (when CONNECTION_TYPE="tcp")
- `DEVICE_IP`: IP address of Meshtastic device (default: "192.168.1.50")
- `DEVICE_PORT`: TCP port (default: 4403)

### Serial Connection (when CONNECTION_TYPE="serial")
- `SERIAL_DEVICE`: Serial device path, e.g., "/dev/ttyUSB0" on Linux or "COM3" on Windows (default: None - auto-detect)

### Other Settings 
- `DATABASE_PATH`: Path to SQLite database file (default: "nodedb.sqlite")
- `DISCORD_WEBHOOK_URL`: Discord webhook URL for notifications (optional)

## API Endpoints
- `GET /`: Web interface showing live logs
- `GET /health`: Health check returning `{"connected": true/false, "queued": N}`
- `GET /nodes`: Node database browser with search and pagination
- `GET /nodes/export`: Export node database as CSV
- `GET /nodedb/stats`: NodeDB statistics and health metrics
- `POST /nodedb/refresh`: Manually trigger nodedb refresh (requires radio connection)

## Usage

### Basic TCP Usage (default)
```bash
git clone https://github.com/osmogr/meshtastic-pingbot
cd meshtastic-pingbot
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
python main.py
```

### Serial Connection Usage
```bash
# With specific serial device
export CONNECTION_TYPE=serial
export SERIAL_DEVICE=/dev/ttyUSB0  # Linux/Mac example
# export SERIAL_DEVICE=COM3        # Windows example
python main.py

# Or with auto-detection (will find first available Meshtastic device)
export CONNECTION_TYPE=serial
python main.py
```

The web interface will be available at http://localhost:5000
