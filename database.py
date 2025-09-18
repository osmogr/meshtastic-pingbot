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