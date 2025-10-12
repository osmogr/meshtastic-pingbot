# NodeDB Import/Export Feature

This document describes the nodedb JSON import/export functionality that allows you to download and manage node information.

## Overview

The bot now supports importing and exporting node information in JSON format, which is similar to what you might get from `meshtastic --info` JSON output. This enables:

1. **Periodic Node Updates**: Automatically downloads node information from the connected radio every 12 hours
2. **JSON Export**: Export current nodedb to JSON format via API endpoint
3. **JSON Import**: Import nodes from JSON data (useful for bulk imports, migrations, or offline node lists)
4. **Integration Ready**: Easy integration with external systems through REST API

## How It Works

### Automatic Periodic Download (Every 12 Hours)

When the bot connects to a Meshtastic radio:
1. It immediately downloads all nodes from `interface.nodes` and `interface.nodesByNum`
2. Schedules a background thread that refreshes the nodedb every 12 hours
3. Each refresh downloads updated node information from the radio
4. Old nodes (>30 days since last update) are automatically cleaned up

### JSON Structure

The JSON format used for import/export follows this structure:

```json
{
  "nodes": [
    {
      "user": {
        "id": "!12345678",
        "shortName": "NODE1",
        "longName": "My Node 1",
        "macaddr": "aa:bb:cc:dd:ee:ff",
        "hwModel": 1,
        "role": 0,
        "isLicensed": false
      },
      "lastHeard": 1234567890,
      "snr": 5.5,
      "rssi": -80,
      "hopCount": 2,
      "viaMqtt": false,
      "createdAt": 1234567890,
      "updatedAt": 1234567890,
      "telemetry": {
        "temperature": 25.5,
        "humidity": 60.0,
        "voltage": 4.2,
        "batteryLevel": 85
      },
      "position": {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "altitude": 100
      }
    }
  ],
  "exportedAt": 1234567890,
  "totalNodes": 1
}
```

## API Endpoints

### Export NodeDB as JSON

**Endpoint**: `GET /nodes/export?format=json`

**Description**: Exports all nodes in the database to JSON format

**Response**: JSON file download

**Example**:
```bash
curl -O http://localhost:5000/nodes/export?format=json
```

### Export NodeDB as CSV (default)

**Endpoint**: `GET /nodes/export`

**Description**: Exports all nodes in the database to CSV format

**Response**: CSV file download

### Import Nodes from JSON

**Endpoint**: `POST /nodedb/import`

**Description**: Imports nodes from JSON data

**Request Body**: JSON data in the format described above

**Example**:
```bash
curl -X POST http://localhost:5000/nodedb/import \
  -H "Content-Type: application/json" \
  -d @nodes.json
```

**Response**:
```json
{
  "message": "NodeDB import completed successfully"
}
```

### Manually Trigger NodeDB Refresh

**Endpoint**: `POST /nodedb/refresh`

**Description**: Manually triggers a nodedb download from the connected radio

**Response**:
```json
{
  "message": "NodeDB refresh completed successfully"
}
```

## Python API

### Export Function

```python
from database import export_nodedb_to_json

# Export nodedb to JSON string
json_data = export_nodedb_to_json()

# Save to file
with open('nodes.json', 'w') as f:
    f.write(json_data)
```

### Import Function

```python
from database import import_nodedb_from_json
import json

# Load from file
with open('nodes.json', 'r') as f:
    json_data = json.load(f)

# Import nodes
success = import_nodedb_from_json(json_data)
```

## Use Cases

### 1. Backup and Restore

Export your nodedb periodically as a backup:
```bash
curl -O http://localhost:5000/nodes/export?format=json
```

Restore from backup:
```bash
curl -X POST http://localhost:5000/nodedb/import \
  -H "Content-Type: application/json" \
  -d @backup.json
```

### 2. Migration Between Instances

Export nodes from one bot instance:
```bash
curl http://instance1:5000/nodes/export?format=json > nodes.json
```

Import to another instance:
```bash
curl -X POST http://instance2:5000/nodedb/import \
  -H "Content-Type: application/json" \
  -d @nodes.json
```

### 3. Offline Node Lists

You can manually create or edit JSON files with node information and import them, useful for:
- Pre-populating a new bot with known nodes
- Adding nodes from external sources
- Bulk updating node information

### 4. Integration with External Systems

The JSON format makes it easy to integrate with:
- Monitoring systems
- Mapping applications
- Node tracking dashboards
- Analytics platforms

## Configuration

The periodic refresh interval is set to **12 hours** by default. This is configured in `meshtastic_handler.py` when the radio connects:

```python
schedule_periodic_nodedb_refresh(interface, 12)  # 12 hours
```

## Troubleshooting

### Import Fails

- Ensure JSON structure matches the expected format
- Check that node IDs are in the correct format (e.g., "!12345678")
- Verify all required fields are present in the user object

### Export Returns Empty

- Check if the database has any nodes: `GET /nodedb/stats`
- Ensure the bot has connected to a radio at least once
- Check logs for any database errors

### Periodic Refresh Not Working

- Verify radio is connected: `GET /health`
- Check logs for refresh messages
- Ensure the background thread started successfully

## Testing

A test script is provided to verify the functionality:

```bash
python3 test_nodedb_import.py
```

This will:
1. Initialize the database
2. Export nodedb to JSON
3. Import test nodes from JSON
4. Verify import success
5. Display statistics
