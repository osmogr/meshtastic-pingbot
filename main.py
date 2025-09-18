import meshtastic
import meshtastic.tcp_interface
import datetime
import time
import requests
import threading
import os
import sys
import sqlite3
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

# --- Database configuration ---
DATABASE_PATH = os.environ.get("DATABASE_PATH", "nodedb.sqlite")

# --- Discord webhook ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# --- Flask / SocketIO ---
app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading")
MAX_LOG_LINES = 100

# Add template filters
@app.template_filter('formatTimestamp')
def format_timestamp(timestamp):
    """Format Unix timestamp for display"""
    if not timestamp:
        return 'Never'
    try:
        return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return 'Invalid'

# --- Connection and health tracking ---
is_connected = False
message_queue_count = 0
interface = None
local_radio_name = ""  # Local radio name (owner name or long name)

# --- Database functions ---
def init_database():
    """Initialize the SQLite database for nodedb storage"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Create nodes table to store node information
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                short_name TEXT,
                long_name TEXT,
                mac_addr TEXT,
                hw_model INTEGER,
                role INTEGER,
                last_heard INTEGER,
                snr REAL,
                rssi INTEGER,
                hop_count INTEGER,
                is_licensed BOOLEAN,
                via_mqtt BOOLEAN,
                created_at INTEGER,
                updated_at INTEGER
            )
        ''')
        
        # Create an index on last_heard for efficient queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_nodes_last_heard ON nodes(last_heard)
        ''')
        
        # Create an index on updated_at for efficient queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_nodes_updated_at ON nodes(updated_at)
        ''')
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Database initialization error: {e}")
        return False

def get_node_name(node_id):
    """Get the display name for a node (long name preferred, fallback to short name, then node ID)"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT long_name, short_name FROM nodes WHERE node_id = ?
        ''', (node_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            long_name, short_name = result
            if long_name and long_name.strip():
                return long_name.strip()
            elif short_name and short_name.strip():
                return short_name.strip()
        
        return node_id
    except Exception as e:
        print(f"Database query error for node {node_id}: {e}")
        return node_id

def update_node_info(node_id, node_info=None, packet_info=None):
    """Update node information in the database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        current_time = int(time.time())
        
        # Prepare data for update
        update_data = {
            'updated_at': current_time
        }
        
        # Debug: Count nodes being processed for first few
        if not hasattr(update_node_info, 'debug_count'):
            update_node_info.debug_count = 0
        update_node_info.debug_count += 1
        
        # Extract info from node_info (from nodedb)
        if node_info:
            # Debug logging for first few nodes
            if update_node_info.debug_count <= 5:
                try:
                    attrs = [attr for attr in dir(node_info) if not attr.startswith('_')]
                    print(f"[DEBUG] Node {node_id} has attributes: {attrs}")
                except:
                    pass
            
            if hasattr(node_info, 'user') and node_info.user:
                # Use correct protobuf field names (snake_case)
                if hasattr(node_info.user, 'long_name') and node_info.user.long_name:
                    update_data['long_name'] = node_info.user.long_name
                if hasattr(node_info.user, 'short_name') and node_info.user.short_name:
                    update_data['short_name'] = node_info.user.short_name
                if hasattr(node_info.user, 'macaddr') and node_info.user.macaddr:
                    update_data['mac_addr'] = node_info.user.macaddr
                if hasattr(node_info.user, 'hw_model'):
                    update_data['hw_model'] = node_info.user.hw_model
                if hasattr(node_info.user, 'role'):
                    update_data['role'] = node_info.user.role
                if hasattr(node_info.user, 'is_licensed'):
                    update_data['is_licensed'] = node_info.user.is_licensed
            else:
                # Debug: Log when user data is missing
                if update_node_info.debug_count <= 5:
                    print(f"[DEBUG] Node {node_id} missing user data")
            
            # Use correct protobuf field names (snake_case)
            if hasattr(node_info, 'last_heard') and node_info.last_heard:
                update_data['last_heard'] = node_info.last_heard
            if hasattr(node_info, 'snr') and node_info.snr is not None:
                update_data['snr'] = node_info.snr
            if hasattr(node_info, 'rssi') and node_info.rssi is not None:
                update_data['rssi'] = node_info.rssi
            if hasattr(node_info, 'device_metrics') and node_info.device_metrics:
                # Extract additional metrics if available
                pass
        else:
            # Debug: Log when node_info is completely missing
            if update_node_info.debug_count <= 5:
                print(f"[DEBUG] Node {node_id} has no node_info")
        
        # Extract info from packet
        if packet_info:
            if 'decoded' in packet_info and 'user' in packet_info['decoded']:
                user = packet_info['decoded']['user']
                if 'longName' in user:
                    update_data['long_name'] = user['longName']
                if 'shortName' in user:
                    update_data['short_name'] = user['shortName']
                if 'macaddr' in user:
                    update_data['mac_addr'] = user['macaddr']
                if 'hwModel' in user:
                    update_data['hw_model'] = user['hwModel']
                if 'role' in user:
                    update_data['role'] = user['role']
                if 'isLicensed' in user:
                    update_data['is_licensed'] = user['isLicensed']
            
            # Extract packet metadata
            if 'rxMetadata' in packet_info and packet_info['rxMetadata']:
                metadata = packet_info['rxMetadata'][0]
                if 'rssi' in metadata:
                    update_data['rssi'] = metadata['rssi']
                if 'snr' in metadata:
                    update_data['snr'] = metadata['snr']
            elif 'rxRssi' in packet_info:
                update_data['rssi'] = packet_info['rxRssi']
                if 'rxSnr' in packet_info:
                    update_data['snr'] = packet_info['rxSnr']
            
            if 'hopStart' in packet_info and 'hopLimit' in packet_info:
                hop_start = packet_info.get('hopStart')
                hop_limit = packet_info.get('hopLimit')
                if hop_start and hop_limit:
                    update_data['hop_count'] = hop_start - hop_limit
            
            if 'viaMqtt' in packet_info:
                update_data['via_mqtt'] = packet_info['viaMqtt']
        
        # Check if node exists
        cursor.execute('SELECT node_id FROM nodes WHERE node_id = ?', (node_id,))
        exists = cursor.fetchone()
        
        if exists:
            # Update existing node
            if update_data:
                set_clause = ', '.join([f"{key} = ?" for key in update_data.keys()])
                query = f"UPDATE nodes SET {set_clause} WHERE node_id = ?"
                values = list(update_data.values()) + [node_id]
                cursor.execute(query, values)
        else:
            # Insert new node
            update_data['node_id'] = node_id
            update_data['created_at'] = current_time
            
            columns = ', '.join(update_data.keys())
            placeholders = ', '.join(['?' for _ in update_data])
            query = f"INSERT INTO nodes ({columns}) VALUES ({placeholders})"
            cursor.execute(query, list(update_data.values()))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Database update error for node {node_id}: {e}")
        return False

def download_nodedb(interface):
    """Download and store the current nodedb from the radio"""
    if not interface:
        log_console_and_discord("No interface provided for nodedb download", "red")
        log_web("No interface provided for nodedb download", "red")
        return False
    
    try:
        log_console_and_discord("Downloading nodedb from radio...", "cyan")
        log_web("Downloading nodedb from radio...", "cyan")
        
        # Debug: Check interface properties
        log_console_and_discord(f"Interface type: {type(interface)}", "cyan")
        log_web(f"Interface type: {type(interface)}", "cyan")
        
        # Get node database from the radio using multiple methods
        nodes = None
        nodesByNum = None
        
        # Method 1: Use the nodes property (keyed by ID)
        if hasattr(interface, 'nodes') and interface.nodes:
            nodes = interface.nodes
            log_console_and_discord(f"Found {len(nodes)} nodes via interface.nodes", "cyan")
            log_web(f"Found {len(nodes)} nodes via interface.nodes", "cyan")
        else:
            log_console_and_discord("interface.nodes is empty or unavailable", "yellow")
            log_web("interface.nodes is empty or unavailable", "yellow")
        
        # Method 2: Use nodesByNum property (keyed by node number)
        if hasattr(interface, 'nodesByNum') and interface.nodesByNum:
            nodesByNum = interface.nodesByNum
            log_console_and_discord(f"Found {len(nodesByNum)} nodes via interface.nodesByNum", "cyan")
            log_web(f"Found {len(nodesByNum)} nodes via interface.nodesByNum", "cyan")
        else:
            log_console_and_discord("interface.nodesByNum is empty or unavailable", "yellow")
            log_web("interface.nodesByNum is empty or unavailable", "yellow")
        
        node_count = 0
        
        # Process nodes from the nodes property first (keyed by ID)
        if nodes:
            log_console_and_discord(f"Processing {len(nodes)} nodes from interface.nodes...", "cyan")
            log_web(f"Processing {len(nodes)} nodes from interface.nodes...", "cyan")
            
            for node_id, node_info in nodes.items():
                try:
                    # Debug: Log node structure for first few nodes
                    if node_count < 3:
                        log_console_and_discord(f"Node {node_id} structure: {type(node_info)}", "cyan")
                        log_web(f"Node {node_id} structure: {type(node_info)}", "cyan")
                        if hasattr(node_info, '__dict__'):
                            available_attrs = [attr for attr in dir(node_info) if not attr.startswith('_')]
                            log_console_and_discord(f"Node {node_id} attributes: {available_attrs[:10]}", "cyan")
                            log_web(f"Node {node_id} attributes: {available_attrs[:10]}", "cyan")
                    
                    if update_node_info(node_id, node_info=node_info):
                        node_count += 1
                except Exception as e:
                    log_console_and_discord(f"Error processing node {node_id}: {e}", "yellow")
                    log_web(f"Error processing node {node_id}: {e}", "yellow")
        
        # Process additional nodes from nodesByNum if they weren't already processed
        if nodesByNum:
            log_console_and_discord(f"Processing additional nodes from interface.nodesByNum...", "cyan")
            log_web(f"Processing additional nodes from interface.nodesByNum...", "cyan")
            
            for node_num, node_info in nodesByNum.items():
                try:
                    # Convert node number to ID format if needed
                    if isinstance(node_info, dict) and 'user' in node_info and 'id' in node_info['user']:
                        node_id = node_info['user']['id']
                    else:
                        node_id = f"!{node_num:08x}"
                    
                    # Check if we already processed this node
                    if nodes and node_id in nodes:
                        continue
                    
                    # Convert dict format to object-like format for consistency
                    class NodeInfoWrapper:
                        def __init__(self, data):
                            if isinstance(data, dict):
                                # Handle dictionary format
                                for key, value in data.items():
                                    if key == 'user' and isinstance(value, dict):
                                        # Convert user dict to object with normalized field names
                                        user_obj = type('obj', (object,), {})()
                                        for uk, uv in value.items():
                                            # Normalize camelCase to snake_case for consistency
                                            if uk == 'longName':
                                                setattr(user_obj, 'long_name', uv)
                                            elif uk == 'shortName':
                                                setattr(user_obj, 'short_name', uv)
                                            elif uk == 'hwModel':
                                                setattr(user_obj, 'hw_model', uv)
                                            elif uk == 'isLicensed':
                                                setattr(user_obj, 'is_licensed', uv)
                                            else:
                                                setattr(user_obj, uk, uv)
                                        setattr(self, key, user_obj)
                                    elif key == 'lastHeard':
                                        # Normalize camelCase to snake_case
                                        setattr(self, 'last_heard', value)
                                    elif key == 'deviceMetrics':
                                        # Normalize camelCase to snake_case
                                        setattr(self, 'device_metrics', value)
                                    else:
                                        setattr(self, key, value)
                            else:
                                # Assume it's already an object
                                self.__dict__.update(data.__dict__ if hasattr(data, '__dict__') else {})
                    
                    wrapped_info = NodeInfoWrapper(node_info)
                    
                    if update_node_info(node_id, node_info=wrapped_info):
                        node_count += 1
                        
                except Exception as e:
                    log_console_and_discord(f"Error processing nodesByNum entry {node_num}: {e}", "yellow")
                    log_web(f"Error processing nodesByNum entry {node_num}: {e}", "yellow")
        
        # Log final results
        if node_count == 0:
            log_console_and_discord("Warning: No nodes were processed from nodedb", "yellow")
            log_web("Warning: No nodes were processed from nodedb", "yellow")
            
            # Additional debugging: Try to access showNodes output for comparison
            try:
                if hasattr(interface, 'showNodes'):
                    nodes_info = interface.showNodes()
                    # Count lines to estimate node count (rough approximation)
                    lines = nodes_info.split('\n')
                    estimated_nodes = max(0, len(lines) - 3)  # Subtract header lines
                    log_console_and_discord(f"showNodes() indicates approximately {estimated_nodes} nodes exist", "yellow")
                    log_web(f"showNodes() indicates approximately {estimated_nodes} nodes exist", "yellow")
            except Exception as e:
                log_console_and_discord(f"Could not get showNodes info: {e}", "yellow")
                log_web(f"Could not get showNodes info: {e}", "yellow")
        else:
            log_console_and_discord(f"Successfully downloaded {node_count} nodes to database", "green")
            log_web(f"Successfully downloaded {node_count} nodes to database", "green")
            # Log statistics after successful download
            log_nodedb_statistics()
        
        return True
        
    except Exception as e:
        log_console_and_discord(f"Failed to download nodedb: {e}", "red")
        log_web(f"Failed to download nodedb: {e}", "red")
        import traceback
        log_console_and_discord(f"Traceback: {traceback.format_exc()}", "red")
        log_web(f"Traceback: {traceback.format_exc()}", "red")
        return False

def request_nodedb_refresh(interface):
    """Request a fresh nodedb download from the radio"""
    if not interface:
        return False
    
    try:
        log_console_and_discord("Requesting fresh nodedb from radio...", "cyan")
        log_web("Requesting fresh nodedb from radio...", "cyan")
        
        # Clear existing nodes to force fresh download
        if hasattr(interface, 'nodes'):
            interface.nodes = {}
        if hasattr(interface, 'nodesByNum'):
            interface.nodesByNum = {}
        
        # Trigger a fresh config request which should include nodedb
        if hasattr(interface, '_startConfig'):
            interface._startConfig()
            log_console_and_discord("Triggered fresh config request", "cyan")
            log_web("Triggered fresh config request", "cyan")
            
            # Wait for config to complete
            import time
            time.sleep(2)  # Give it a moment to start
            
            if hasattr(interface, 'waitForConfig'):
                try:
                    success = interface.waitForConfig()
                    if success:
                        log_console_and_discord("Config refresh completed successfully", "green")
                        log_web("Config refresh completed successfully", "green")
                        return True
                    else:
                        log_console_and_discord("Config refresh timed out", "yellow")
                        log_web("Config refresh timed out", "yellow")
                except Exception as e:
                    log_console_and_discord(f"Error waiting for config: {e}", "yellow")
                    log_web(f"Error waiting for config: {e}", "yellow")
        
        return False
        
    except Exception as e:
        log_console_and_discord(f"Failed to request nodedb refresh: {e}", "red")
        log_web(f"Failed to request nodedb refresh: {e}", "red")
        return False

def enhanced_download_nodedb(interface, retry_on_failure=True):
    """Enhanced nodedb download with retry logic"""
    if not interface:
        return False
    
    # First attempt: Standard download
    success = download_nodedb(interface)
    
    if not success and retry_on_failure:
        log_console_and_discord("Initial nodedb download failed, attempting refresh...", "yellow")
        log_web("Initial nodedb download failed, attempting refresh...", "yellow")
        
        # Try to request a fresh nodedb
        if request_nodedb_refresh(interface):
            # Retry download after refresh
            success = download_nodedb(interface)
    
    return success

def schedule_periodic_nodedb_refresh(interface, interval_hours=24):
    """Schedule periodic nodedb refresh to ensure we have the latest data"""
    import threading
    import time
    
    def periodic_refresh():
        while True:
            try:
                time.sleep(interval_hours * 3600)  # Convert hours to seconds
                if interface and hasattr(interface, 'isConnected') and interface.isConnected.is_set():
                    log_console_and_discord(f"Starting periodic nodedb refresh (every {interval_hours}h)", "cyan")
                    log_web(f"Starting periodic nodedb refresh (every {interval_hours}h)", "cyan")
                    enhanced_download_nodedb(interface)
                    cleanup_old_nodes(30)
            except Exception as e:
                log_console_and_discord(f"Error in periodic nodedb refresh: {e}", "yellow")
                log_web(f"Error in periodic nodedb refresh: {e}", "yellow")
    
    # Start the periodic refresh in a separate thread
    refresh_thread = threading.Thread(target=periodic_refresh, daemon=True)
    refresh_thread.start()
    log_console_and_discord(f"Scheduled periodic nodedb refresh every {interval_hours} hours", "green")
    log_web(f"Scheduled periodic nodedb refresh every {interval_hours} hours", "green")

def get_nodedb_statistics():
    """Get statistics about the current nodedb"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Total nodes
        cursor.execute('SELECT COUNT(*) FROM nodes')
        total_nodes = cursor.fetchone()[0]
        
        # Nodes with complete information
        cursor.execute('''
            SELECT COUNT(*) FROM nodes 
            WHERE long_name IS NOT NULL AND long_name != ""
            AND short_name IS NOT NULL AND short_name != ""
        ''')
        complete_nodes = cursor.fetchone()[0]
        
        # Recent nodes (last 24 hours)
        cutoff_time = int(time.time()) - (24 * 60 * 60)
        cursor.execute('SELECT COUNT(*) FROM nodes WHERE updated_at > ?', (cutoff_time,))
        recent_nodes = cursor.fetchone()[0]
        
        # Nodes with location data
        cursor.execute('SELECT COUNT(*) FROM nodes WHERE last_heard IS NOT NULL')
        nodes_with_location = cursor.fetchone()[0]
        
        conn.close()
        
        stats = {
            'total_nodes': total_nodes,
            'complete_nodes': complete_nodes,
            'recent_nodes': recent_nodes,
            'nodes_with_location': nodes_with_location,
            'completion_rate': (complete_nodes / total_nodes * 100) if total_nodes > 0 else 0
        }
        
        return stats
        
    except Exception as e:
        print(f"Error getting nodedb statistics: {e}")
        return None

def log_nodedb_statistics():
    """Log current nodedb statistics"""
    stats = get_nodedb_statistics()
    if stats:
        log_console_and_discord(f"NodeDB Stats: {stats['total_nodes']} total, {stats['complete_nodes']} complete ({stats['completion_rate']:.1f}%), {stats['recent_nodes']} recent", "cyan")
        log_web(f"NodeDB Stats: {stats['total_nodes']} total, {stats['complete_nodes']} complete ({stats['completion_rate']:.1f}%), {stats['recent_nodes']} recent", "cyan")

def cleanup_old_nodes(max_age_days=30):
    """Remove nodes that haven't been seen for more than max_age_days"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cutoff_time = int(time.time()) - (max_age_days * 24 * 60 * 60)
        
        # Count nodes to be removed
        cursor.execute('''
            SELECT COUNT(*) FROM nodes 
            WHERE updated_at < ? OR updated_at IS NULL
        ''', (cutoff_time,))
        
        old_count = cursor.fetchone()[0]
        
        if old_count > 0:
            # Remove old nodes
            cursor.execute('''
                DELETE FROM nodes 
                WHERE updated_at < ? OR updated_at IS NULL
            ''', (cutoff_time,))
            
            conn.commit()
            log_console_and_discord(f"Cleaned up {old_count} old nodes from database", "yellow")
            log_web(f"Cleaned up {old_count} old nodes from database", "yellow")
        
        conn.close()
        return True
    except Exception as e:
        log_console_and_discord(f"Database cleanup error: {e}", "red")
        log_web(f"Database cleanup error: {e}", "red")
        return False

HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Meshtastic Ping-Pong Logs</title>
  <style>
    body { font-family: monospace; background: #1e1e1e; color: #eee; margin: 0; padding: 0; }
    .navbar { background: #2a2a2a; padding: 10px; border-bottom: 1px solid #444; }
    .navbar a { color: #00ff00; text-decoration: none; margin-right: 20px; padding: 5px 10px; }
    .navbar a:hover { background: #333; border-radius: 3px; }
    .navbar a.active { background: #444; border-radius: 3px; }
    h2 { margin: 10px; color: #00ff00; }
    #logs { height: 85vh; overflow-y: scroll; padding: 10px; box-sizing: border-box; background: #1e1e1e; }
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
  <div class="navbar">
    <a href="/" class="active">Live Logs</a>
    <a href="/nodes">Node Database</a>
    <a href="/health">Health</a>
  </div>
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

HEALTH_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Meshtastic Pingbot - Health Status</title>
  <style>
    body { font-family: monospace; background: #1e1e1e; color: #eee; margin: 0; padding: 0; }
    .navbar { background: #2a2a2a; padding: 10px; border-bottom: 1px solid #444; }
    .navbar a { color: #00ff00; text-decoration: none; margin-right: 20px; padding: 5px 10px; }
    .navbar a:hover { background: #333; border-radius: 3px; }
    .navbar a.active { background: #444; border-radius: 3px; }
    .container { padding: 20px; }
    h2 { margin: 0 0 20px 0; color: #00ff00; }
    .status-card { background: #2a2a2a; border-radius: 8px; padding: 20px; margin-bottom: 20px; border-left: 4px solid #555; }
    .status-connected { border-left-color: #00ff00; }
    .status-disconnected { border-left-color: #ff5555; }
    .status-header { font-size: 1.2em; font-weight: bold; margin-bottom: 10px; }
    .status-value { font-size: 1.5em; margin: 10px 0; }
    .connected { color: #00ff00; }
    .disconnected { color: #ff5555; }
    .metric { margin: 10px 0; }
    .metric-label { color: #888; display: inline-block; width: 120px; }
    .metric-value { color: #00ffff; font-weight: bold; }
    .refresh-btn { background: #333; border: 1px solid #555; color: #eee; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-top: 20px; }
    .refresh-btn:hover { background: #444; }
    .timestamp { color: #888; font-size: 0.9em; margin-top: 15px; }
  </style>
</head>
<body>
  <div class="navbar">
    <a href="/">Live Logs</a>
    <a href="/nodes">Node Database</a>
    <a href="/health" class="active">Health</a>
  </div>
  <div class="container">
    <h2>Health Status</h2>
    
    <div class="status-card {{ 'status-connected' if connected else 'status-disconnected' }}">
      <div class="status-header">Connection Status</div>
      <div class="status-value {{ 'connected' if connected else 'disconnected' }}">
        {{ 'CONNECTED' if connected else 'DISCONNECTED' }}
      </div>
      <div class="metric">
        <span class="metric-label">Radio Link:</span>
        <span class="metric-value">{{ 'Active' if connected else 'Inactive' }}</span>
      </div>
    </div>
    
    <div class="status-card">
      <div class="status-header">Message Queue</div>
      <div class="metric">
        <span class="metric-label">Queued Messages:</span>
        <span class="metric-value">{{ queued }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">Queue Status:</span>
        <span class="metric-value">{{ 'Normal' if queued < 10 else 'High' if queued < 50 else 'Critical' }}</span>
      </div>
    </div>
    
    <button class="refresh-btn" onclick="window.location.reload()">Refresh Status</button>
    
    <div class="timestamp">
      Last updated: <span id="timestamp"></span>
    </div>
  </div>
  
  <script>
    document.getElementById('timestamp').textContent = new Date().toLocaleString();
    
    // Auto-refresh every 30 seconds
    setTimeout(function() {
      window.location.reload();
    }, 30000);
  </script>
</body>
</html>
"""

NODES_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Meshtastic Node Database</title>
  <style>
    body { font-family: monospace; background: #1e1e1e; color: #eee; margin: 0; padding: 0; }
    .navbar { background: #2a2a2a; padding: 10px; border-bottom: 1px solid #444; }
    .navbar a { color: #00ff00; text-decoration: none; margin-right: 20px; padding: 5px 10px; }
    .navbar a:hover { background: #333; border-radius: 3px; }
    .navbar a.active { background: #444; border-radius: 3px; }
    .container { padding: 20px; }
    h2 { color: #00ff00; margin-bottom: 20px; }
    
    .controls { background: #2a2a2a; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
    .controls input, .controls select { 
      background: #333; color: #eee; border: 1px solid #555; padding: 5px; margin-right: 10px; 
      border-radius: 3px; font-family: monospace;
    }
    .controls button { 
      background: #444; color: #eee; border: 1px solid #666; padding: 5px 10px; 
      border-radius: 3px; cursor: pointer; font-family: monospace;
    }
    .controls button:hover { background: #555; }
    
    .stats { color: #888; margin-bottom: 10px; }
    
    table { width: 100%; border-collapse: collapse; background: #2a2a2a; border-radius: 5px; overflow: hidden; }
    th, td { padding: 8px 12px; border-bottom: 1px solid #444; text-align: left; }
    th { background: #333; color: #00ff00; font-weight: bold; cursor: pointer; user-select: none; }
    th:hover { background: #444; }
    th.sortable::after { content: ' ↕'; opacity: 0.5; }
    th.sort-asc::after { content: ' ↑'; opacity: 1; color: #00ff00; }
    th.sort-desc::after { content: ' ↓'; opacity: 1; color: #00ff00; }
    
    tbody tr:hover { background: #333; }
    .node-id { color: #00ffff; font-weight: bold; }
    .name { color: #ffff00; }
    .rssi-good { color: #00ff00; }
    .rssi-ok { color: #ffff00; }
    .rssi-poor { color: #ff5555; }
    .snr-good { color: #00ff00; }
    .snr-ok { color: #ffff00; }
    .snr-poor { color: #ff5555; }
    .timestamp { color: #888; font-size: 0.9em; }
    .boolean-true { color: #00ff00; }
    .boolean-false { color: #ff5555; }
    
    .pagination { margin-top: 20px; text-align: center; }
    .pagination a, .pagination span { 
      display: inline-block; padding: 5px 10px; margin: 0 2px; 
      background: #333; color: #eee; text-decoration: none; border-radius: 3px;
    }
    .pagination a:hover { background: #444; }
    .pagination .current { background: #00ff00; color: #000; }
    
    .loading { text-align: center; color: #888; padding: 20px; }
    .error { color: #ff5555; padding: 10px; background: #332; border-radius: 3px; margin-bottom: 20px; }
  </style>
</head>
<body>
  <div class="navbar">
    <a href="/">Live Logs</a>
    <a href="/nodes" class="active">Node Database</a>
    <a href="/health">Health</a>
  </div>
  
  <div class="container">
    <h2>Node Database Browser</h2>
    
    <div class="controls">
      <input type="text" id="searchInput" placeholder="Search nodes..." value="{{ search }}" />
      <select id="perPageSelect">
        <option value="25" {% if per_page == 25 %}selected{% endif %}>25 per page</option>
        <option value="50" {% if per_page == 50 %}selected{% endif %}>50 per page</option>
        <option value="100" {% if per_page == 100 %}selected{% endif %}>100 per page</option>
      </select>
      <button onclick="refreshData()">Refresh</button>
      <button onclick="exportData()">Export CSV</button>
    </div>
    
    <div class="stats">
      Total nodes: {{ total_count }} | Page {{ page }} of {{ total_pages }}
    </div>
    
    <div id="error-message"></div>
    <div id="loading" class="loading" style="display: none;">Loading...</div>
    
    <table id="nodesTable">
      <thead>
        <tr>
          <th class="sortable" data-column="node_id">Node ID</th>
          <th class="sortable" data-column="long_name">Long Name</th>
          <th class="sortable" data-column="short_name">Short Name</th>
          <th class="sortable" data-column="rssi">RSSI</th>
          <th class="sortable" data-column="snr">SNR</th>
          <th class="sortable" data-column="hop_count">Hops</th>
          <th class="sortable" data-column="last_heard">Last Heard</th>
          <th class="sortable" data-column="updated_at">Updated</th>
          <th>Via MQTT</th>
          <th>Licensed</th>
        </tr>
      </thead>
      <tbody id="nodesTableBody">
        {% for node in nodes %}
        <tr>
          <td class="node-id">{{ node.node_id }}</td>
          <td class="name">{{ node.long_name or '-' }}</td>
          <td class="name">{{ node.short_name or '-' }}</td>
          <td class="{% if node.rssi and node.rssi|int > -70 %}rssi-good{% elif node.rssi and node.rssi|int > -85 %}rssi-ok{% else %}rssi-poor{% endif %}">
            {{ node.rssi or 'N/A' }}
          </td>
          <td class="{% if node.snr and node.snr|float > 10 %}snr-good{% elif node.snr and node.snr|float >= 0 %}snr-ok{% else %}snr-poor{% endif %}">
            {{ "%.1f"|format(node.snr) if node.snr else 'N/A' }}
          </td>
          <td>{{ node.hop_count or 'N/A' }}</td>
          <td class="timestamp">{{ node.last_heard|formatTimestamp }}</td>
          <td class="timestamp">{{ node.updated_at|formatTimestamp }}</td>
          <td class="{% if node.via_mqtt %}boolean-true{% else %}boolean-false{% endif %}">
            {{ 'Yes' if node.via_mqtt else 'No' }}
          </td>
          <td class="{% if node.is_licensed %}boolean-true{% else %}boolean-false{% endif %}">
            {{ 'Yes' if node.is_licensed else 'No' }}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    
    <div class="pagination">
      {% if page > 1 %}
        <a href="#" onclick="changePage(1)">First</a>
        <a href="#" onclick="changePage({{ page - 1 }})">Previous</a>
      {% endif %}
      
      {% for p in range([1, page - 2]|max, [total_pages + 1, page + 3]|min) %}
        {% if p == page %}
          <span class="current">{{ p }}</span>
        {% else %}
          <a href="#" onclick="changePage({{ p }})">{{ p }}</a>
        {% endif %}
      {% endfor %}
      
      {% if page < total_pages %}
        <a href="#" onclick="changePage({{ page + 1 }})">Next</a>
        <a href="#" onclick="changePage({{ total_pages }})">Last</a>
      {% endif %}
    </div>
  </div>

  <script>
    let currentSort = '{{ sort_by }}';
    let currentOrder = '{{ sort_order }}';
    let currentPage = {{ page }};
    let currentSearch = '{{ search }}';
    let currentPerPage = {{ per_page }};
    
    function formatTimestamp(timestamp) {
      if (!timestamp) return 'Never';
      return new Date(timestamp * 1000).toLocaleString();
    }
    
    function updateSortHeaders() {
      document.querySelectorAll('th.sortable').forEach(th => {
        th.className = 'sortable';
        if (th.dataset.column === currentSort) {
          th.classList.add('sort-' + currentOrder);
        }
      });
    }
    
    function sortTable(column) {
      if (currentSort === column) {
        currentOrder = currentOrder === 'asc' ? 'desc' : 'asc';
      } else {
        currentSort = column;
        currentOrder = 'desc';
      }
      currentPage = 1;
      loadData();
    }
    
    function changePage(page) {
      currentPage = page;
      loadData();
    }
    
    function refreshData() {
      currentSearch = document.getElementById('searchInput').value;
      currentPerPage = parseInt(document.getElementById('perPageSelect').value);
      currentPage = 1;
      loadData();
    }
    
    function loadData() {
      document.getElementById('loading').style.display = 'block';
      document.getElementById('error-message').innerHTML = '';
      
      const params = new URLSearchParams({
        sort: currentSort,
        order: currentOrder,
        page: currentPage,
        per_page: currentPerPage,
        search: currentSearch
      });
      
      fetch('/nodes?' + params.toString(), {
        headers: { 'Accept': 'application/json' }
      })
      .then(response => response.json())
      .then(data => {
        if (data.error) {
          throw new Error(data.error);
        }
        updateTable(data);
        updatePagination(data);
        updateStats(data);
        updateSortHeaders();
      })
      .catch(error => {
        document.getElementById('error-message').innerHTML = 
          '<div class="error">Error loading data: ' + error.message + '</div>';
      })
      .finally(() => {
        document.getElementById('loading').style.display = 'none';
      });
    }
    
    function updateTable(data) {
      const tbody = document.getElementById('nodesTableBody');
      tbody.innerHTML = '';
      
      data.nodes.forEach(node => {
        const row = document.createElement('tr');
        
        const rssiClass = node.rssi && node.rssi > -70 ? 'rssi-good' : 
                         node.rssi && node.rssi > -85 ? 'rssi-ok' : 'rssi-poor';
        const snrClass = node.snr && node.snr > 10 ? 'snr-good' : 
                        node.snr && node.snr >= 0 ? 'snr-ok' : 'snr-poor';
        
        row.innerHTML = `
          <td class="node-id">${node.node_id}</td>
          <td class="name">${node.long_name || '-'}</td>
          <td class="name">${node.short_name || '-'}</td>
          <td class="${rssiClass}">${node.rssi || 'N/A'}</td>
          <td class="${snrClass}">${node.snr ? node.snr.toFixed(1) : 'N/A'}</td>
          <td>${node.hop_count || 'N/A'}</td>
          <td class="timestamp">${formatTimestamp(node.last_heard)}</td>
          <td class="timestamp">${formatTimestamp(node.updated_at)}</td>
          <td class="${node.via_mqtt ? 'boolean-true' : 'boolean-false'}">${node.via_mqtt ? 'Yes' : 'No'}</td>
          <td class="${node.is_licensed ? 'boolean-true' : 'boolean-false'}">${node.is_licensed ? 'Yes' : 'No'}</td>
        `;
        
        tbody.appendChild(row);
      });
    }
    
    function updatePagination(data) {
      // Update pagination dynamically (simplified for now)
      currentPage = data.page;
    }
    
    function updateStats(data) {
      document.querySelector('.stats').textContent = 
        `Total nodes: ${data.total_count} | Page ${data.page} of ${data.total_pages}`;
    }
    
    function exportData() {
      const params = new URLSearchParams({
        sort: currentSort,
        order: currentOrder,
        search: currentSearch,
        export: 'csv'
      });
      
      window.open('/nodes/export?' + params.toString());
    }
    
    // Initialize
    document.addEventListener('DOMContentLoaded', function() {
      updateSortHeaders();
      
      // Add click handlers for sortable headers
      document.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => sortTable(th.dataset.column));
      });
      
      // Add enter key handler for search
      document.getElementById('searchInput').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
          refreshData();
        }
      });
      
      // Auto-refresh every 30 seconds
      setInterval(loadData, 30000);
    });
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, max_lines=MAX_LOG_LINES)

@app.route("/nodes")
def nodes():
    """Database browser for nodes"""
    from flask import request, jsonify
    
    # Get query parameters for filtering and sorting
    sort_by = request.args.get('sort', 'updated_at')
    sort_order = request.args.get('order', 'desc')
    search = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    
    # Validate sort parameters
    valid_columns = ['node_id', 'long_name', 'short_name', 'rssi', 'snr', 'hop_count', 'last_heard', 'updated_at']
    if sort_by not in valid_columns:
        sort_by = 'updated_at'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'
    
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Build query with search filter
        base_query = '''
            SELECT node_id, long_name, short_name, mac_addr, hw_model, role, 
                   last_heard, snr, rssi, hop_count, is_licensed, via_mqtt, 
                   created_at, updated_at
            FROM nodes
        '''
        
        where_clause = ""
        params = []
        
        if search:
            where_clause = """
                WHERE (node_id LIKE ? OR long_name LIKE ? OR short_name LIKE ?)
            """
            search_param = f"%{search}%"
            params = [search_param, search_param, search_param]
        
        # Add sorting
        order_clause = f" ORDER BY {sort_by} {sort_order.upper()}"
        
        # Count total records
        count_query = f"SELECT COUNT(*) FROM nodes{where_clause}"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]
        
        # Add pagination
        limit_clause = f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"
        
        # Execute main query
        full_query = base_query + where_clause + order_clause + limit_clause
        cursor.execute(full_query, params)
        
        nodes_data = []
        for row in cursor.fetchall():
            node_data = {
                'node_id': row[0],
                'long_name': row[1],
                'short_name': row[2],
                'mac_addr': row[3],
                'hw_model': row[4],
                'role': row[5],
                'last_heard': row[6],
                'snr': row[7],
                'rssi': row[8],
                'hop_count': row[9],
                'is_licensed': row[10],
                'via_mqtt': row[11],
                'created_at': row[12],
                'updated_at': row[13]
            }
            nodes_data.append(node_data)
        
        conn.close()
        
        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page
        
        # If this is an AJAX request, return JSON
        if request.headers.get('Accept') == 'application/json':
            return jsonify({
                'nodes': nodes_data,
                'total_count': total_count,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages,
                'sort_by': sort_by,
                'sort_order': sort_order,
                'search': search
            })
        
        # Otherwise return HTML template
        return render_template_string(NODES_TEMPLATE, 
                                    nodes=nodes_data,
                                    total_count=total_count,
                                    page=page,
                                    per_page=per_page,
                                    total_pages=total_pages,
                                    sort_by=sort_by,
                                    sort_order=sort_order,
                                    search=search)
    
    except Exception as e:
        if request.headers.get('Accept') == 'application/json':
            return jsonify({'error': str(e)}), 500
        return f"Database error: {e}", 500

@app.route("/nodes/export")
def export_nodes():
    """Export nodes data as CSV"""
    from flask import Response
    import csv
    import io
    
    # Get query parameters
    sort_by = request.args.get('sort', 'updated_at')
    sort_order = request.args.get('order', 'desc')
    search = request.args.get('search', '')
    
    # Validate sort parameters
    valid_columns = ['node_id', 'long_name', 'short_name', 'rssi', 'snr', 'hop_count', 'last_heard', 'updated_at']
    if sort_by not in valid_columns:
        sort_by = 'updated_at'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'
    
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Build query with search filter
        base_query = '''
            SELECT node_id, long_name, short_name, mac_addr, hw_model, role, 
                   last_heard, snr, rssi, hop_count, is_licensed, via_mqtt, 
                   created_at, updated_at
            FROM nodes
        '''
        
        where_clause = ""
        params = []
        
        if search:
            where_clause = """
                WHERE (node_id LIKE ? OR long_name LIKE ? OR short_name LIKE ?)
            """
            search_param = f"%{search}%"
            params = [search_param, search_param, search_param]
        
        # Add sorting
        order_clause = f" ORDER BY {sort_by} {sort_order.upper()}"
        
        # Execute query
        full_query = base_query + where_clause + order_clause
        cursor.execute(full_query, params)
        
        # Create CSV output
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Node ID', 'Long Name', 'Short Name', 'MAC Address', 'Hardware Model', 'Role',
            'Last Heard', 'SNR', 'RSSI', 'Hop Count', 'Licensed', 'Via MQTT',
            'Created At', 'Updated At'
        ])
        
        # Write data
        for row in cursor.fetchall():
            # Convert timestamps to readable format
            processed_row = list(row)
            for i in [6, 12, 13]:  # last_heard, created_at, updated_at
                if processed_row[i]:
                    processed_row[i] = datetime.datetime.fromtimestamp(processed_row[i]).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    processed_row[i] = ''
            
            # Convert boolean values
            processed_row[10] = 'Yes' if processed_row[10] else 'No'  # is_licensed
            processed_row[11] = 'Yes' if processed_row[11] else 'No'  # via_mqtt
            
            writer.writerow(processed_row)
        
        conn.close()
        
        # Create response
        csv_data = output.getvalue()
        output.close()
        
        response = Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=meshtastic_nodes_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'}
        )
        
        return response
        
    except Exception as e:
        return f"Export error: {e}", 500

@app.route("/health")
def health():
    """Health check endpoint"""
    from flask import jsonify, request, render_template_string
    
    health_data = {
        "connected": is_connected,
        "queued": message_queue_count
    }
    
    # If this is an API request (Accept: application/json), return JSON
    if request.headers.get('Accept') == 'application/json':
        # Add security headers for JSON response
        response = jsonify(health_data)
        response.headers['Content-Type'] = 'application/json'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response
    
    # Otherwise return HTML template for web interface
    return render_template_string(HEALTH_TEMPLATE, 
                                connected=health_data["connected"],
                                queued=health_data["queued"])

@app.route("/nodedb/stats")
def nodedb_stats():
    """NodeDB statistics endpoint"""
    from flask import jsonify, request
    
    stats = get_nodedb_statistics()
    if not stats:
        stats = {
            'total_nodes': 0,
            'complete_nodes': 0,
            'recent_nodes': 0,
            'nodes_with_location': 0,
            'completion_rate': 0
        }
    
    # Add connection status
    stats['connected'] = is_connected
    
    # If this is an API request, return JSON
    if request.headers.get('Accept') == 'application/json':
        response = jsonify(stats)
        response.headers['Content-Type'] = 'application/json'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response
    
    # Return simple text format for browser
    return f"""NodeDB Statistics:
Total Nodes: {stats['total_nodes']}
Complete Nodes: {stats['complete_nodes']} ({stats['completion_rate']:.1f}%)
Recent Nodes (24h): {stats['recent_nodes']}
Nodes with Location: {stats['nodes_with_location']}
Connected: {stats['connected']}"""

@app.route("/nodedb/refresh", methods=['POST'])
def nodedb_refresh():
    """Manually trigger nodedb refresh"""
    from flask import jsonify, request
    
    if not is_connected or not interface:
        error_msg = "Radio not connected"
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"success": False, "error": error_msg}), 400
        return f"Error: {error_msg}", 400
    
    try:
        # Trigger enhanced nodedb download
        success = enhanced_download_nodedb(interface)
        
        if success:
            # Get updated stats
            stats = get_nodedb_statistics()
            
            result = {
                "success": True,
                "message": "NodeDB refresh completed successfully",
                "stats": stats
            }
            
            if request.headers.get('Accept') == 'application/json':
                response = jsonify(result)
                response.headers['Content-Type'] = 'application/json'
                return response
            
            return f"Success: NodeDB refresh completed. Found {stats['total_nodes'] if stats else 0} nodes."
        else:
            error_msg = "NodeDB refresh failed"
            if request.headers.get('Accept') == 'application/json':
                return jsonify({"success": False, "error": error_msg}), 500
            return f"Error: {error_msg}", 500
            
    except Exception as e:
        error_msg = f"NodeDB refresh error: {e}"
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"success": False, "error": error_msg}), 500
        return f"Error: {error_msg}", 500

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
    """Get sender name, preferring database lookup over packet data"""
    sender_id = packet.get("fromId", "Unknown")
    
    # First try to get name from database
    db_name = get_node_name(sender_id)
    if db_name != sender_id:  # Database returned a name, not just the ID
        return db_name
    
    # Fallback to packet data if not in database
    if "decoded" in packet and "user" in packet["decoded"]:
        user = packet["decoded"]["user"]
        name = user.get("longName") or user.get("shortName")
        if name:
            # Update database with this new info
            update_node_info(sender_id, packet_info=packet)
            return name
    
    return sender_id

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

def send_messages_async(interface, messages, destination_id, sender_name, message_type="Reply"):
    """
    Send messages asynchronously in a separate thread to avoid blocking message reception.
    """
    def send_task():
        try:
            success = send_multiple_messages(interface, messages, destination_id)
            
            if success:
                if len(messages) == 1:
                    console = f"{message_type} -> {sender_name}: {messages[0]}"
                else:
                    console = f"{message_type} -> {sender_name}: {len(messages)} message{'s' if len(messages) > 1 else ''}"
                log_console_and_discord(console, "green")
                log_web(console, "green")
            else:
                console = f"Failed to send {message_type.lower()} -> {sender_name}"
                log_console_and_discord(console, "red")
                log_web(console, "red")
        except Exception as e:
            console = f"Error sending {message_type.lower()} -> {sender_name}: {e}"
            log_console_and_discord(console, "red")
            log_web(console, "red")
    
    # Start the sending task in a separate thread
    thread = threading.Thread(target=send_task, daemon=True)
    thread.start()
    return thread

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
    
    if not packet:
        return
    
    # Handle different packet types
    packet_type = packet.get("decoded", {}).get("portnum")
    
    # Update database for NODEINFO_APP packets
    if packet_type == meshtastic.portnums_pb2.NODEINFO_APP:
        sender_id = packet.get("fromId")
        if sender_id:
            update_node_info(sender_id, packet_info=packet)
            sender_name = get_node_name(sender_id)
            log_console_and_discord(f"Updated node info for {sender_name} ({sender_id})", "blue")
            log_web(f"Updated node info for {sender_name} ({sender_id})", "blue")
        return
    
    # Update database for NEIGHBORINFO_APP packets
    if packet_type == meshtastic.portnums_pb2.NEIGHBORINFO_APP:
        sender_id = packet.get("fromId")
        if sender_id:
            update_node_info(sender_id, packet_info=packet)
            sender_name = get_node_name(sender_id)
            log_console_and_discord(f"Updated neighbor info for {sender_name} ({sender_id})", "blue")
            log_web(f"Updated neighbor info for {sender_name} ({sender_id})", "blue")
        return
    
    # Handle text messages (existing functionality)
    if "decoded" not in packet or "text" not in packet["decoded"]:
        return
    
    # Basic input validation
    try:
        msg = packet["decoded"]["text"].strip().lower()
        if len(msg) > 200:  # Reasonable limit for Meshtastic messages
            return
        
        sender = get_sender_name(packet)
        sender_id = packet.get("fromId", sender)
        message_origin = get_message_origin(packet)
        
        # Update database with any user info from this packet
        if sender_id:
            update_node_info(sender_id, packet_info=packet)
        
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
            
            # Send reply asynchronously to avoid blocking message reception
            send_messages_async(interface, reply_messages, packet["fromId"], sender, "DM Help/About")
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
            
            # Send reply asynchronously to avoid blocking message reception
            send_messages_async(interface, reply_messages, packet["fromId"], sender, "Reply")
            
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
                        
                        # Download nodedb after successful connection
                        try:
                            enhanced_download_nodedb(interface)
                            # Clean up old nodes (older than 30 days)
                            cleanup_old_nodes(30)
                            # Schedule periodic nodedb refresh (every 6 hours)
                            schedule_periodic_nodedb_refresh(interface, 6)
                        except Exception as e:
                            log_console_and_discord(f"Failed to download nodedb: {e}", "yellow")
                            log_web(f"Failed to download nodedb: {e}", "yellow")
                        
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
        # Initialize database
        if not init_database():
            print("Failed to initialize database, exiting...")
            sys.exit(1)
        
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
