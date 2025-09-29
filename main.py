#!/usr/bin/env python3
"""
Meshtastic Pingbot - A simple ping-pong bot for Meshtastic mesh networks.

This bot responds to ping, hello, test messages with connection information
including RSSI, SNR, and hop count. It also supports traceroute functionality
and maintains a SQLite database of node information.
"""

import sys
import datetime
from flask import Flask
from flask_socketio import SocketIO

# Import our modular components
from config import MAX_LOG_LINES
from database import init_database, enhanced_download_nodedb
from logging_utils import log_console, log_web, set_socketio
from traceroute import start_traceroute_worker, stop_traceroute_worker
from meshtastic_handler import (
    connect_radio, setup_exception_handlers, stop_connection,
    get_connection_status
)
from web_routes import setup_routes


def format_timestamp(timestamp):
    """Format Unix timestamp for display"""
    if not timestamp:
        return 'Never'
    try:
        return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return 'Invalid'


def main():
    """Main application entry point."""
    # Setup Flask app and SocketIO
    app = Flask(__name__)
    socketio = SocketIO(app, async_mode="threading")
    
    # Setup template filters
    @app.template_filter('formatTimestamp')
    def format_timestamp_filter(timestamp):
        return format_timestamp(timestamp)
    
    # Initialize logging with SocketIO instance
    set_socketio(socketio)
    
    # Setup web routes with callback functions
    def is_connected_func():
        return get_connection_status()[0]
    
    def message_queue_count_func():
        return get_connection_status()[1]
    
    def enhanced_download_nodedb_func():
        """Get the interface and call enhanced_download_nodedb"""
        try:
            from meshtastic_handler import interface
            if interface:
                return enhanced_download_nodedb(interface)
        except:
            pass
        return False
    
    setup_routes(app, is_connected_func, message_queue_count_func, enhanced_download_nodedb_func)
    
    # Setup exception handlers for better error handling
    setup_exception_handlers()
    
    try:
        # Initialize database
        if not init_database():
            print("Failed to initialize database, exiting...")
            sys.exit(1)
        
        # Start traceroute worker
        start_traceroute_worker()
        
        # Connect to radio and start monitoring
        interface = connect_radio()
        
        # Start web server
        log_console("Starting web server...", "green", True)
        log_web("Starting web server...", "green", True)
        socketio.run(app, host="0.0.0.0", port=5000)
        
    except KeyboardInterrupt:
        log_console("Shutting down...", "yellow")
        stop_traceroute_worker()
        stop_connection()
    except Exception as e:
        log_console(f"Fatal error: {e}", "red")
        stop_traceroute_worker()
        stop_connection()
    finally:
        # Clean shutdown
        stop_traceroute_worker()
        stop_connection()


if __name__ == "__main__":
    main()