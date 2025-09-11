# meshtastic-pingbot
Meshtastic Pingbot

## Features

This pingbot automatically responds to "ping", "hello", and "test" messages with connection information including RSSI, SNR, and hop count.

### Recent Improvements

- **Separated Logging Functions**: Console and Discord logging are now separate functions (`log_console()`, `log_discord()`, `log_console_and_discord()`)
- **TCP Reconnection**: Automatic reconnection with exponential backoff when connection is lost
- **Health Endpoint**: `/health` endpoint returns JSON with connection status and message queue count
- **Security Enhancements**: Input validation, security headers, and improved error handling
- **Environment Configuration**: Configure via environment variables

## Configuration

Set these environment variables:

- `MESHTASTIC_IP`: IP address of Meshtastic device (default: "192.168.1.50")
- `MESHTASTIC_PORT`: TCP port (default: 4403) 
- `DISCORD_WEBHOOK_URL`: Discord webhook URL for notifications (optional)

## API Endpoints

- `GET /`: Web interface showing live logs
- `GET /health`: Health check returning `{"connected": true/false, "queued": N}`

## Usage

```bash
python3 main.py
```

The web interface will be available at http://localhost:5000
