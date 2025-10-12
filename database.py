"""Database module for Meshtastic PingBot."""

import sqlite3
import time
import threading
from config import DATABASE_PATH


def init_database():
    """Initialize the SQLite database for nodedb storage"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Create nodes table to store node information
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                node_num INTEGER,
                short_name TEXT,
                long_name TEXT,
                mac_addr TEXT,
                hw_model INTEGER,
                role INTEGER,
                public_key TEXT,
                last_heard INTEGER,
                snr REAL,
                rssi INTEGER,
                hop_count INTEGER,
                hops_away INTEGER,
                is_licensed BOOLEAN,
                is_favorite BOOLEAN,
                via_mqtt BOOLEAN,
                created_at INTEGER,
                updated_at INTEGER,
                temperature REAL,
                humidity REAL,
                voltage REAL,
                battery_level INTEGER,
                channel_utilization REAL,
                air_util_tx REAL,
                uptime_seconds INTEGER,
                latitude REAL,
                longitude REAL,
                altitude INTEGER,
                position_time INTEGER,
                position_location_source TEXT
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
        
        # Add new columns if they don't exist (for existing databases)
        try:
            # Check if new columns exist and add them if they don't
            cursor.execute("PRAGMA table_info(nodes)")
            columns = [column[1] for column in cursor.fetchall()]
            
            new_columns = [
                ('node_num', 'INTEGER'),
                ('public_key', 'TEXT'),
                ('hops_away', 'INTEGER'),
                ('is_favorite', 'BOOLEAN'),
                ('channel_utilization', 'REAL'),
                ('air_util_tx', 'REAL'),
                ('uptime_seconds', 'INTEGER'),
                ('position_time', 'INTEGER'),
                ('position_location_source', 'TEXT'),
                ('temperature', 'REAL'),
                ('humidity', 'REAL'),
                ('voltage', 'REAL'),
                ('battery_level', 'INTEGER'),
                ('latitude', 'REAL'),
                ('longitude', 'REAL'),
                ('altitude', 'INTEGER')
            ]
            
            for col_name, col_type in new_columns:
                if col_name not in columns:
                    cursor.execute(f'ALTER TABLE nodes ADD COLUMN {col_name} {col_type}')
                    print(f"[Database] Added column: {col_name}")
        except Exception as e:
            print(f"[Database] Error adding new columns: {e}")
        
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


def get_node_name_by_num(node_num):
    """Get the display name for a node by node number (converts to ID format first)"""
    # Node numbers in RouteDiscovery are integers, need to match against node_id in database
    # Node IDs in database are typically in format like "!12345678"
    try:
        # Try to find by matching the hex representation
        node_id_hex = f"!{node_num:08x}"
        return get_node_name(node_id_hex)
    except Exception as e:
        print(f"Database query error for node num {node_num}: {e}")
        return str(node_num)


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
            
            # Extract node number if available
            if hasattr(node_info, 'num') and node_info.num:
                update_data['node_num'] = node_info.num
            
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
                if hasattr(node_info.user, 'public_key') and node_info.user.public_key:
                    update_data['public_key'] = node_info.user.public_key
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
            if hasattr(node_info, 'hops_away') and node_info.hops_away is not None:
                update_data['hops_away'] = node_info.hops_away
            if hasattr(node_info, 'is_favorite') and node_info.is_favorite is not None:
                update_data['is_favorite'] = node_info.is_favorite
            
            # Extract device metrics
            if hasattr(node_info, 'device_metrics') and node_info.device_metrics:
                dm = node_info.device_metrics
                if hasattr(dm, 'battery_level') and dm.battery_level is not None:
                    update_data['battery_level'] = dm.battery_level
                if hasattr(dm, 'voltage') and dm.voltage is not None:
                    update_data['voltage'] = dm.voltage
                if hasattr(dm, 'channel_utilization') and dm.channel_utilization is not None:
                    update_data['channel_utilization'] = dm.channel_utilization
                if hasattr(dm, 'air_util_tx') and dm.air_util_tx is not None:
                    update_data['air_util_tx'] = dm.air_util_tx
                if hasattr(dm, 'uptime_seconds') and dm.uptime_seconds is not None:
                    update_data['uptime_seconds'] = dm.uptime_seconds
            
            # Extract position data
            if hasattr(node_info, 'position') and node_info.position:
                pos = node_info.position
                # Handle both integer (latitudeI) and float (latitude) formats
                if hasattr(pos, 'latitude_i') and pos.latitude_i:
                    update_data['latitude'] = pos.latitude_i / 1e7
                elif hasattr(pos, 'latitude') and pos.latitude is not None:
                    update_data['latitude'] = pos.latitude
                
                if hasattr(pos, 'longitude_i') and pos.longitude_i:
                    update_data['longitude'] = pos.longitude_i / 1e7
                elif hasattr(pos, 'longitude') and pos.longitude is not None:
                    update_data['longitude'] = pos.longitude
                
                if hasattr(pos, 'altitude') and pos.altitude is not None:
                    update_data['altitude'] = pos.altitude
                if hasattr(pos, 'time') and pos.time:
                    update_data['position_time'] = pos.time
                if hasattr(pos, 'location_source') and pos.location_source:
                    update_data['position_location_source'] = str(pos.location_source)
        else:
            # Debug: Log when node_info is completely missing
            if update_node_info.debug_count <= 5:
                print(f"[DEBUG] Node {node_id} has no node_info")
        
        # Extract info from packet
        if packet_info:
            # Update last_heard to current time when we receive a packet
            update_data['last_heard'] = current_time
            
            # Extract node number if available
            if 'num' in packet_info:
                update_data['node_num'] = packet_info['num']
            
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
                if 'publicKey' in user:
                    update_data['public_key'] = user['publicKey']
            
            # Extract hopsAway and isFavorite from top level
            if 'hopsAway' in packet_info:
                update_data['hops_away'] = packet_info['hopsAway']
            if 'isFavorite' in packet_info:
                update_data['is_favorite'] = packet_info['isFavorite']
            
            # Extract packet metadata (rssi, snr)
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
            
            # Extract telemetry data from packet
            if 'decoded' in packet_info:
                decoded = packet_info['decoded']
                
                # Extract telemetry data (device metrics and environment metrics)
                if 'telemetry' in decoded:
                    telemetry = decoded['telemetry']
                    
                    # Device metrics (battery, voltage, channel utilization, etc.)
                    if 'deviceMetrics' in telemetry:
                        device_metrics = telemetry['deviceMetrics']
                        if 'batteryLevel' in device_metrics:
                            update_data['battery_level'] = device_metrics['batteryLevel']
                        if 'voltage' in device_metrics:
                            update_data['voltage'] = device_metrics['voltage']
                        if 'channelUtilization' in device_metrics:
                            update_data['channel_utilization'] = device_metrics['channelUtilization']
                        if 'airUtilTx' in device_metrics:
                            update_data['air_util_tx'] = device_metrics['airUtilTx']
                        if 'uptimeSeconds' in device_metrics:
                            update_data['uptime_seconds'] = device_metrics['uptimeSeconds']
                    
                    # Environment metrics (temperature, humidity)
                    if 'environmentMetrics' in telemetry:
                        env_metrics = telemetry['environmentMetrics']
                        if 'temperature' in env_metrics:
                            update_data['temperature'] = env_metrics['temperature']
                        if 'relativeHumidity' in env_metrics:
                            update_data['humidity'] = env_metrics['relativeHumidity']
                
                # Extract position data (GPS coordinates, altitude)
                if 'position' in decoded:
                    position = decoded['position']
                    # Latitude and longitude are in degrees * 1e-7, need to convert
                    if 'latitudeI' in position:
                        update_data['latitude'] = position['latitudeI'] / 1e7
                    elif 'latitude' in position:
                        update_data['latitude'] = position['latitude']
                    
                    if 'longitudeI' in position:
                        update_data['longitude'] = position['longitudeI'] / 1e7
                    elif 'longitude' in position:
                        update_data['longitude'] = position['longitude']
                    
                    if 'altitude' in position:
                        update_data['altitude'] = position['altitude']
                    if 'time' in position:
                        update_data['position_time'] = position['time']
                    if 'locationSource' in position:
                        update_data['position_location_source'] = position['locationSource']
        
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
            from logging_utils import log_console_and_web, log_web
            log_console_and_web(f"Cleaned up {old_count} old nodes (>{max_age_days} days)", "green")
        
        conn.close()
        return old_count
        
    except Exception as e:
        print(f"Error cleaning up old nodes: {e}")
        return 0


def log_nodedb_statistics():
    """Log current nodedb statistics"""
    stats = get_nodedb_statistics()
    if stats:
        from logging_utils import log_console_and_web, log_web
        log_console_and_web(f"NodeDB Stats: {stats['total_nodes']} total, {stats['complete_nodes']} complete ({stats['completion_rate']:.1f}%), {stats['recent_nodes']} recent", "cyan")


def download_nodedb(interface):
    """Download and store the current nodedb from the radio"""
    from logging_utils import log_console_and_web, log_web
    
    if not interface:
        log_console_and_web("No interface provided for nodedb download", "red")
        return False
    
    try:
        log_console_and_web("Downloading nodedb from radio...", "cyan")
        
        # Debug: Check interface properties
        log_console_and_web(f"Interface type: {type(interface)}", "cyan")
        
        # Get node database from the radio using multiple methods
        nodes = None
        nodesByNum = None
        
        # Method 1: Use the nodes property (keyed by ID)
        if hasattr(interface, 'nodes') and interface.nodes:
            nodes = interface.nodes
            log_console_and_web(f"Found {len(nodes)} nodes via interface.nodes", "cyan")
        else:
            log_console_and_web("interface.nodes is empty or unavailable", "yellow")
        
        # Method 2: Use nodesByNum property (keyed by node number)
        if hasattr(interface, 'nodesByNum') and interface.nodesByNum:
            nodesByNum = interface.nodesByNum
            log_console_and_web(f"Found {len(nodesByNum)} nodes via interface.nodesByNum", "cyan")
        else:
            log_console_and_web("interface.nodesByNum is empty or unavailable", "yellow")
        
        node_count = 0
        
        # Process nodes from the nodes property first (keyed by ID)
        if nodes:
            log_console_and_web(f"Processing {len(nodes)} nodes from interface.nodes...", "cyan")
            
            for node_id, node_info in nodes.items():
                try:
                    # Debug: Log node structure for first few nodes
                    if node_count < 3:
                        log_console_and_web(f"Node {node_id} structure: {type(node_info)}", "cyan")
                        if hasattr(node_info, '__dict__'):
                            available_attrs = [attr for attr in dir(node_info) if not attr.startswith('_')]
                            log_console_and_web(f"Node {node_id} attributes: {available_attrs[:10]}", "cyan")
                    
                    if update_node_info(node_id, node_info=node_info):
                        node_count += 1
                except Exception as e:
                    log_console_and_web(f"Error processing node {node_id}: {e}", "yellow")
        
        # Process additional nodes from nodesByNum if they weren't already processed
        if nodesByNum:
            log_console_and_web(f"Processing additional nodes from interface.nodesByNum...", "cyan")
            
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
                    log_console_and_web(f"Error processing nodesByNum entry {node_num}: {e}", "yellow")
        
        # Log final results
        if node_count == 0:
            log_console_and_web("Warning: No nodes were processed from nodedb", "yellow")
            
            # Additional debugging: Try to access showNodes output for comparison
            try:
                if hasattr(interface, 'showNodes'):
                    nodes_info = interface.showNodes()
                    # Count lines to estimate node count (rough approximation)
                    lines = nodes_info.split('\n')
                    estimated_nodes = max(0, len(lines) - 3)  # Subtract header lines
                    log_console_and_web(f"showNodes() indicates approximately {estimated_nodes} nodes exist", "yellow")
            except Exception as e:
                log_console_and_web(f"Could not get showNodes info: {e}", "yellow")
        else:
            log_console_and_web(f"Successfully downloaded {node_count} nodes to database", "green")
            # Log statistics after successful download
            log_nodedb_statistics()
        
        return True
        
    except Exception as e:
        log_console_and_web(f"Failed to download nodedb: {e}", "red")
        import traceback
        log_console_and_web(f"Traceback: {traceback.format_exc()}", "red")
        return False


def request_nodedb_refresh(interface):
    """Request a fresh nodedb download from the radio"""
    from logging_utils import log_console_and_web, log_web
    
    if not interface:
        return False
    
    try:
        log_console_and_web("Requesting fresh nodedb from radio...", "cyan")
        
        # Clear existing nodes to force fresh download
        if hasattr(interface, 'nodes'):
            interface.nodes = {}
        if hasattr(interface, 'nodesByNum'):
            interface.nodesByNum = {}
        
        # Trigger a fresh config request which should include nodedb
        if hasattr(interface, '_startConfig'):
            interface._startConfig()
            log_console_and_web("Triggered fresh config request", "cyan")
            
            # Wait for config to complete
            time.sleep(2)  # Give it a moment to start
            
            if hasattr(interface, 'waitForConfig'):
                try:
                    success = interface.waitForConfig()
                    if success:
                        log_console_and_web("Config refresh completed successfully", "green")
                        return True
                    else:
                        log_console_and_web("Config refresh timed out", "yellow")
                except Exception as e:
                    log_console_and_web(f"Error waiting for config: {e}", "yellow")
        
        return False
        
    except Exception as e:
        log_console_and_web(f"Failed to request nodedb refresh: {e}", "red")
        return False


def enhanced_download_nodedb(interface, retry_on_failure=True):
    """Enhanced nodedb download with retry logic"""
    if not interface:
        return False
    
    # First attempt: Standard download
    success = download_nodedb(interface)
    
    if not success and retry_on_failure:
        from logging_utils import log_console_and_web, log_web
        log_console_and_web("Initial nodedb download failed, attempting refresh...", "yellow")
        
        # Try to request a fresh nodedb
        if request_nodedb_refresh(interface):
            # Retry download after refresh
            success = download_nodedb(interface)
    
    return success


def export_nodedb_to_json():
    """Export current nodedb to JSON format (similar to what meshtastic --info would provide)"""
    import json
    import sqlite3
    
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT node_id, node_num, short_name, long_name, mac_addr, hw_model, role,
                   public_key, last_heard, snr, rssi, hop_count, hops_away, is_licensed,
                   is_favorite, via_mqtt, created_at, updated_at, temperature, humidity,
                   voltage, battery_level, channel_utilization, air_util_tx, uptime_seconds,
                   latitude, longitude, altitude, position_time, position_location_source
            FROM nodes
            ORDER BY last_heard DESC
        ''')
        
        nodes = []
        for row in cursor.fetchall():
            node = {
                'num': row[1],
                'user': {
                    'id': row[0],
                    'shortName': row[2],
                    'longName': row[3],
                    'macaddr': row[4],
                    'hwModel': row[5],
                    'role': row[6],
                    'publicKey': row[7],
                    'isLicensed': row[13]
                },
                'lastHeard': row[8],
                'snr': row[9],
                'rssi': row[10],
                'hopCount': row[11],
                'hopsAway': row[12],
                'isFavorite': row[14],
                'viaMqtt': row[15],
                'createdAt': row[16],
                'updatedAt': row[17],
                'deviceMetrics': {
                    'batteryLevel': row[21],
                    'voltage': row[20],
                    'channelUtilization': row[22],
                    'airUtilTx': row[23],
                    'uptimeSeconds': row[24]
                },
                'position': {
                    'latitude': row[25],
                    'longitude': row[26],
                    'altitude': row[27],
                    'time': row[28],
                    'locationSource': row[29]
                },
                'telemetry': {
                    'temperature': row[18],
                    'humidity': row[19]
                }
            }
            nodes.append(node)
        
        conn.close()
        
        nodedb_json = {
            'nodes': nodes,
            'exportedAt': int(time.time()),
            'totalNodes': len(nodes)
        }
        
        return json.dumps(nodedb_json, indent=2)
        
    except Exception as e:
        print(f"Error exporting nodedb to JSON: {e}")
        return None


def import_nodedb_from_json(json_data):
    """Import nodedb from JSON data (from meshtastic --info or interface export)"""
    from logging_utils import log_console_and_web, log_web
    import json
    
    try:
        # Parse JSON if it's a string
        if isinstance(json_data, str):
            data = json.loads(json_data)
        else:
            data = json_data
        
        node_count = 0
        
        # Check if this is a meshtastic info output with nodes
        if 'nodes' in data:
            nodes = data['nodes']
            log_console_and_web(f"Found {len(nodes)} nodes in JSON data", "cyan")
            
            for node in nodes:
                try:
                    # Extract node ID
                    node_id = node.get('user', {}).get('id')
                    if not node_id:
                        continue
                    
                    # Create a wrapper object for the node data
                    class NodeInfoWrapper:
                        def __init__(self, data):
                            # Node number
                            self.num = data.get('num')
                            
                            # User data
                            self.user = type('obj', (object,), {})()
                            if 'user' in data:
                                user_data = data['user']
                                self.user.long_name = user_data.get('longName', '')
                                self.user.short_name = user_data.get('shortName', '')
                                self.user.macaddr = user_data.get('macaddr', '')
                                self.user.hw_model = user_data.get('hwModel', 0)
                                self.user.role = user_data.get('role', 0)
                                self.user.is_licensed = user_data.get('isLicensed', False)
                                self.user.public_key = user_data.get('publicKey', '')
                            
                            # Network metrics
                            self.last_heard = data.get('lastHeard', 0)
                            self.snr = data.get('snr')
                            self.rssi = data.get('rssi')
                            self.hops_away = data.get('hopsAway')
                            self.is_favorite = data.get('isFavorite')
                            
                            # Device metrics
                            if 'deviceMetrics' in data:
                                self.device_metrics = type('obj', (object,), {})()
                                dm = data['deviceMetrics']
                                self.device_metrics.battery_level = dm.get('batteryLevel')
                                self.device_metrics.voltage = dm.get('voltage')
                                self.device_metrics.channel_utilization = dm.get('channelUtilization')
                                self.device_metrics.air_util_tx = dm.get('airUtilTx')
                                self.device_metrics.uptime_seconds = dm.get('uptimeSeconds')
                            
                            # Position data
                            if 'position' in data:
                                self.position = type('obj', (object,), {})()
                                pos = data['position']
                                # Handle both integer and float formats
                                if 'latitudeI' in pos:
                                    self.position.latitude_i = pos['latitudeI']
                                    self.position.latitude = pos['latitudeI'] / 1e7
                                else:
                                    self.position.latitude = pos.get('latitude')
                                
                                if 'longitudeI' in pos:
                                    self.position.longitude_i = pos['longitudeI']
                                    self.position.longitude = pos['longitudeI'] / 1e7
                                else:
                                    self.position.longitude = pos.get('longitude')
                                
                                self.position.altitude = pos.get('altitude')
                                self.position.time = pos.get('time')
                                self.position.location_source = pos.get('locationSource')
                    
                    wrapped_info = NodeInfoWrapper(node)
                    
                    if update_node_info(node_id, node_info=wrapped_info):
                        node_count += 1
                        
                except Exception as e:
                    log_console_and_web(f"Error processing node from JSON: {e}", "yellow")
        
        if node_count > 0:
            log_console_and_web(f"Successfully imported {node_count} nodes from JSON", "green")
            log_nodedb_statistics()
            return True
        else:
            log_console_and_web("No nodes were imported from JSON", "yellow")
            return False
            
    except Exception as e:
        log_console_and_web(f"Error importing nodes from JSON: {e}", "yellow")
        return False


def import_nodedb_from_cli():
    """Import nodedb using meshtastic CLI command with JSON output"""
    from logging_utils import log_console_and_web, log_web
    import subprocess
    import json
    from config import CONNECTION_TYPE, DEVICE_IP, SERIAL_DEVICE
    
    try:
        log_console_and_web("Importing nodes from meshtastic CLI...", "cyan")
        
        # Build meshtastic command based on connection type
        cmd = ['meshtastic']
        if CONNECTION_TYPE == 'tcp':
            cmd.extend(['--host', DEVICE_IP])
        elif CONNECTION_TYPE == 'serial' and SERIAL_DEVICE:
            cmd.extend(['--port', SERIAL_DEVICE])
        
        # Use --export-config to get JSON output including nodedb
        # Note: This exports the full config, which includes node information
        cmd.append('--export-config')
        
        # Run the command with a timeout
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            log_console_and_web(f"meshtastic CLI command failed: {result.stderr}", "yellow")
            return False
        
        output = result.stdout
        
        if not output:
            log_console_and_web("No output from meshtastic CLI", "yellow")
            return False
        
        # Try to parse as JSON
        try:
            # The export-config outputs YAML, not JSON, so we need a different approach
            # Let's use the existing interface method instead
            log_console_and_web("Using interface-based node download instead of CLI", "cyan")
            return False
        except Exception as e:
            log_console_and_web(f"Could not parse CLI output: {e}", "yellow")
            return False
        
    except subprocess.TimeoutExpired:
        log_console_and_web("meshtastic CLI command timed out", "yellow")
        return False
    except FileNotFoundError:
        log_console_and_web("meshtastic CLI not found in PATH", "yellow")
        return False
    except Exception as e:
        log_console_and_web(f"Error importing nodes from CLI: {e}", "yellow")
        return False


def schedule_periodic_nodedb_refresh(interface, interval_hours=24):
    """Schedule periodic nodedb refresh to ensure we have the latest data"""
    import threading
    from logging_utils import log_console_and_web, log_web
    
    def periodic_refresh():
        while True:
            try:
                time.sleep(interval_hours * 3600)  # Convert hours to seconds
                if interface and hasattr(interface, 'isConnected') and interface.isConnected.is_set():
                    log_console_and_web(f"Starting periodic nodedb refresh (every {interval_hours}h)", "cyan")
                    enhanced_download_nodedb(interface)
                    cleanup_old_nodes(30)
            except Exception as e:
                log_console_and_web(f"Error in periodic nodedb refresh: {e}", "yellow")
    
    # Start the periodic refresh in a separate thread
    refresh_thread = threading.Thread(target=periodic_refresh, daemon=True)
    refresh_thread.start()
    log_console_and_web(f"Scheduled periodic nodedb refresh every {interval_hours} hours", "green")