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
            from logging_utils import log_console_and_discord, log_web
            log_console_and_discord(f"Cleaned up {old_count} old nodes (>{max_age_days} days)", "green")
            log_web(f"Cleaned up {old_count} old nodes (>{max_age_days} days)", "green")
        
        conn.close()
        return old_count
        
    except Exception as e:
        print(f"Error cleaning up old nodes: {e}")
        return 0


def log_nodedb_statistics():
    """Log current nodedb statistics"""
    stats = get_nodedb_statistics()
    if stats:
        from logging_utils import log_console_and_discord, log_web
        log_console_and_discord(f"NodeDB Stats: {stats['total_nodes']} total, {stats['complete_nodes']} complete ({stats['completion_rate']:.1f}%), {stats['recent_nodes']} recent", "cyan")
        log_web(f"NodeDB Stats: {stats['total_nodes']} total, {stats['complete_nodes']} complete ({stats['completion_rate']:.1f}%), {stats['recent_nodes']} recent", "cyan")


def download_nodedb(interface):
    """Download and store the current nodedb from the radio"""
    from logging_utils import log_console_and_discord, log_web
    
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
    from logging_utils import log_console_and_discord, log_web
    
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
        from logging_utils import log_console_and_discord, log_web
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
    from logging_utils import log_console_and_discord, log_web
    
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