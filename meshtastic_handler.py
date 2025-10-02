"""Meshtastic handler module for connection management and packet processing."""

import meshtastic
import meshtastic.tcp_interface
import meshtastic.serial_interface
import datetime
import time
import threading
import sys
from pubsub import pub
from config import CONNECTION_TYPE, DEVICE_IP, SERIAL_DEVICE, REPLY_COOLDOWN, TRIGGERS, DM_COMMANDS
from database import update_node_info, get_node_name
from logging_utils import log_console_and_web, log_console_web_and_discord, log_web, timestamp, set_local_radio_name
from traceroute import (split_message, send_messages_async, queue_traceroute, 
                       pending_traceroutes)

# Connection and health tracking globals
is_connected = False
message_queue_count = 0
interface = None
local_radio_name = ""

# Connection handling
connection_lock = threading.Lock()
reconnect_thread = None
shutdown_event = threading.Event()

# Track socket errors to detect heartbeat failures
socket_error_count = 0
socket_error_lock = threading.Lock()

# Rate limiting
last_reply_time = {}


def get_connection_status():
    """Get current connection status and message queue count."""
    return is_connected, message_queue_count


def update_message_queue_count(delta):
    """Update the message queue count safely."""
    global message_queue_count
    message_queue_count += delta


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


def extract_rssi_snr(packet):
    """Extract RSSI and SNR from packet."""
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


def get_help_response():
    """Generate help response for DM help commands (optimized for message splitting)"""
    return (
        f"Meshtastic Pingbot Help:\n\n"
        f"Basic triggers (channels and DMs): {', '.join(TRIGGERS)}\n\n"

        f"Commands:\n"
        f"• ping/hello/test - Connection info (RSSI, SNR, hop count)\n"
        f"• ping N - Send N responses (N=1-5)\n"
        f"• traceroute - Network path trace with hop details\n"
        f"  (30s rate limit, max 2 queued per user)\n\n"

        f"DM-only commands: help, /help - Show this help message. "
        f"about, /about - Show information about this bot."
    )


def get_about_response():
    """Generate about response for DM about commands (optimized for message splitting)"""
    return (
        f"Meshtastic Pingbot v1.0\n\n"
        f"I'm a simple ping-pong bot that helps test Meshtastic network connectivity. "
        f"Send me '{', '.join(TRIGGERS)}' and I'll respond with your connection quality metrics. "
        f"Use 'ping N' (N=1-5) for multiple responses. "
        f"Features: RSSI and SNR reporting, Hop count tracking, Rate limiting (15s cooldown), "
        f"Channel and DM support. Built for the Meshtastic mesh networking community."
    )


def handle_traceroute_response_packet(packet, interface):
    """Handle traceroute response packets"""
    try:
        # The traceroute response comes from the destination node
        from_id = packet.get("fromId")
        
        log_console_and_web(f"Received potential traceroute response from {from_id}", "cyan")
        
        # Check if this is a response to any of our pending traceroutes
        # We need to match based on the destination we sent to, not the sender
        matching_request = None
        matching_sender_id = None
        
        for sender_id, pending_request in list(pending_traceroutes.items()):
            # The target_id in the request is where we sent the traceroute to
            # and from_id should match that
            target_node_id = pending_request.get('target_node_id')
            if target_node_id and target_node_id == from_id:
                matching_request = pending_request
                matching_sender_id = sender_id
                log_console_and_web(f"Matched traceroute response from {from_id} to pending request for {pending_request['sender_name']}", "green")
                break
        
        if not matching_request:
            # Not a response to our traceroute request
            log_console_and_web(f"No matching traceroute request for response from {from_id}", "yellow")
            return
            
        destination_id = matching_request['destination_id']
        sender_name = matching_request['sender_name']
        
        # Remove from pending requests
        del pending_traceroutes[matching_sender_id]
        
        # Extract information from the packet
        decoded = packet.get("decoded", {})
        packet_type = decoded.get("portnum")
        
        log_console_and_web(f"Processing traceroute response (portnum: {packet_type}) for {sender_name}", "cyan")
        
        # Format the traceroute result
        result_lines = []
        result_lines.append(f"Traceroute to {sender_name}:")
        
        # Parse RouteDiscovery payload for TRACEROUTE_APP packets
        if packet_type == meshtastic.portnums_pb2.TRACEROUTE_APP:
            try:
                from meshtastic import mesh_pb2
                import google.protobuf.json_format
                
                payload = decoded.get("payload", b"")
                if payload:
                    route_discovery = mesh_pb2.RouteDiscovery()
                    route_discovery.ParseFromString(payload)
                    route_dict = google.protobuf.json_format.MessageToDict(route_discovery)
                    
                    log_console_and_web(f"Parsed RouteDiscovery data: {len(route_dict.get('route', []))} hops", "cyan")
                    
                    # Format the route towards destination
                    route_list = route_dict.get("route", [])
                    snr_towards = route_dict.get("snrTowards", [])
                    
                    if route_list or snr_towards:
                        result_lines.append("\nRoute traced:")
                        
                        # Build route string with node IDs
                        route_str_parts = []
                        
                        # Start with us (the bot)
                        route_str_parts.append("Bot")
                        
                        # Add intermediate hops
                        UNK_SNR = -128
                        for idx, node_num in enumerate(route_list):
                            # Try to get node name from database
                            from database import get_node_name_by_num
                            node_name = None
                            try:
                                node_name = get_node_name_by_num(node_num)
                            except:
                                pass
                            
                            if not node_name or node_name == str(node_num):
                                node_name = f"!{node_num:08x}"
                            
                            # Add SNR if available
                            snr_str = ""
                            if idx < len(snr_towards) and snr_towards[idx] != UNK_SNR:
                                snr_val = snr_towards[idx] / 4.0
                                snr_str = f" ({snr_val:.1f}dB)"
                            
                            route_str_parts.append(f"{node_name}{snr_str}")
                        
                        # End with destination
                        if snr_towards:
                            last_snr_idx = len(snr_towards) - 1
                            if last_snr_idx >= 0 and snr_towards[last_snr_idx] != UNK_SNR:
                                snr_val = snr_towards[last_snr_idx] / 4.0
                                result_lines.append(" -> ".join(route_str_parts) + f" -> {sender_name} ({snr_val:.1f}dB)")
                            else:
                                result_lines.append(" -> ".join(route_str_parts) + f" -> {sender_name}")
                        else:
                            result_lines.append(" -> ".join(route_str_parts) + f" -> {sender_name}")
                        
                        # Add hop count
                        hop_count = len(route_list)
                        if hop_count == 0:
                            result_lines.append("Direct connection (0 hops)")
                        else:
                            result_lines.append(f"Total hops: {hop_count}")
                        
                        # Check for return route
                        route_back = route_dict.get("routeBack", [])
                        snr_back = route_dict.get("snrBack", [])
                        if route_back or snr_back:
                            result_lines.append("\nReturn route:")
                            back_parts = [sender_name]
                            
                            for idx, node_num in enumerate(route_back):
                                from database import get_node_name_by_num
                                node_name = None
                                try:
                                    node_name = get_node_name_by_num(node_num)
                                except:
                                    pass
                                
                                if not node_name or node_name == str(node_num):
                                    node_name = f"!{node_num:08x}"
                                
                                snr_str = ""
                                if idx < len(snr_back) and snr_back[idx] != UNK_SNR:
                                    snr_val = snr_back[idx] / 4.0
                                    snr_str = f" ({snr_val:.1f}dB)"
                                
                                back_parts.append(f"{node_name}{snr_str}")
                            
                            back_parts.append("Bot")
                            result_lines.append(" -> ".join(back_parts))
                    else:
                        result_lines.append("Direct connection (0 hops)")
                else:
                    log_console_and_web(f"No payload in traceroute response for {sender_name}", "yellow")
                    result_lines.append("No route data in response")
                    
            except Exception as parse_error:
                log_console_and_web(f"Error parsing traceroute data for {sender_name}: {parse_error}", "red")
                result_lines.append("Traceroute completed (parse error)")
        
        # Add basic packet info for any response type
        hop_start = packet.get("hopStart", 0)
        hop_limit = packet.get("hopLimit", 0)
        hops_away = max(0, hop_start - hop_limit)
        if hops_away > 0:
            result_lines.append(f"\nPacket hops: {hops_away}")
        
        # Add signal quality if available
        rssi = packet.get("rxRssi")
        snr = packet.get("rxSnr")
        if rssi is not None or snr is not None:
            signal_parts = []
            if rssi is not None:
                signal_parts.append(f"RSSI: {rssi}dBm")
            if snr is not None:
                signal_parts.append(f"SNR: {snr:.2f}dB")
            result_lines.append(", ".join(signal_parts))
            
        # Add timestamp
        current_timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        result_lines.append(f"\nCompleted at: {current_timestamp}")
            
        result_msg = "\n".join(result_lines)
        
        # Log the result to console
        log_console_and_web(f"Traceroute completed for {sender_name}", "green")
        log_web(f"Traceroute completed for {sender_name}", "green")
        
        # Send the result back to the user
        reply_messages = split_message(result_msg)
        send_messages_async(interface, reply_messages, destination_id, sender_name, "Traceroute")
        
    except Exception as e:
        log_console_and_web(f"Error handling traceroute response: {e}", "red")
        log_web(f"Error handling traceroute response: {e}", "red")


def on_receive(packet=None, interface=None, **kwargs):
    """Handle incoming packets from the Meshtastic interface."""
    global message_queue_count, is_connected
    
    if not packet:
        return
    
    # Handle different packet types
    packet_type = packet.get("decoded", {}).get("portnum")
    
    # NOTE: Traceroute responses are now handled by custom callback in traceroute.py
    # The old handler is kept here but will not be triggered since we use a custom onResponse callback
    # if packet_type in [meshtastic.portnums_pb2.ROUTING_APP, meshtastic.portnums_pb2.TRACEROUTE_APP]:
    #     sender_id = packet.get("fromId")
    #     if sender_id and sender_id in pending_traceroutes:
    #         handle_traceroute_response_packet(packet, interface)
    #     return
    
    # Update database for NODEINFO_APP packets
    if packet_type == meshtastic.portnums_pb2.NODEINFO_APP:
        sender_id = packet.get("fromId")
        if sender_id:
            update_node_info(sender_id, packet_info=packet)
            sender_name = get_node_name(sender_id)
            log_console_and_web(f"Updated node info for {sender_name} ({sender_id})", "blue")
            log_web(f"Updated node info for {sender_name} ({sender_id})", "blue")
        return
    
    # Update database for NEIGHBORINFO_APP packets
    if packet_type == meshtastic.portnums_pb2.NEIGHBORINFO_APP:
        sender_id = packet.get("fromId")
        if sender_id:
            update_node_info(sender_id, packet_info=packet)
            sender_name = get_node_name(sender_id)
            log_console_and_web(f"Updated neighbor info for {sender_name} ({sender_id})", "blue")
            log_web(f"Updated neighbor info for {sender_name} ({sender_id})", "blue")
        return
    
    # Update database for TELEMETRY_APP packets
    if packet_type == meshtastic.portnums_pb2.TELEMETRY_APP:
        sender_id = packet.get("fromId")
        if sender_id:
            update_node_info(sender_id, packet_info=packet)
            sender_name = get_node_name(sender_id)
            log_console_and_web(f"Updated telemetry for {sender_name} ({sender_id})", "blue")
            log_web(f"Updated telemetry for {sender_name} ({sender_id})", "blue")
        return
    
    # Update database for POSITION_APP packets
    if packet_type == meshtastic.portnums_pb2.POSITION_APP:
        sender_id = packet.get("fromId")
        if sender_id:
            update_node_info(sender_id, packet_info=packet)
            sender_name = get_node_name(sender_id)
            log_console_and_web(f"Updated position for {sender_name} ({sender_id})", "blue")
            log_web(f"Updated position for {sender_name} ({sender_id})", "blue")
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

        log_console_web_and_discord(f"Incoming from {sender} via {message_origin}: '{msg}'", "cyan", True)
        log_web(f"Incoming from {sender} via {message_origin}: '{msg}'", "cyan", True)

        # Handle DM-only commands (help and about)
        if message_origin == "DM" and msg in DM_COMMANDS:
            now = time.time()
            if sender_id in last_reply_time and (now - last_reply_time[sender_id]) < REPLY_COOLDOWN:
                log_console_and_web(f"Rate-limited reply to {sender}", "yellow")
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

        # Handle traceroute command separately (special rate limiting)
        if msg == "traceroute":
            # Check regular rate limit first
            now = time.time()
            if sender_id in last_reply_time and (now - last_reply_time[sender_id]) < REPLY_COOLDOWN:
                log_console_and_web(f"Rate-limited reply to {sender}", "yellow")
                return

            last_reply_time[sender_id] = now
            
            # Queue the traceroute request
            success, message = queue_traceroute(interface, packet["fromId"], sender, sender_id)
            
            if success:
                reply = f"Traceroute queued: {message}"
                log_console_and_web(f"Traceroute queued for {sender}: {message}", "cyan")
            else:
                reply = f"Traceroute failed: {message}"
                log_console_and_web(f"Traceroute failed for {sender}: {message}", "yellow")
            
            reply_messages = split_message(reply)
            send_messages_async(interface, reply_messages, packet["fromId"], sender, "Traceroute Queue")
            return

        # Handle existing triggers (ping, hello, test) - work in both channels and DMs
        ping_count = 1
        if msg in TRIGGERS or (msg.startswith("ping ") and len(msg.split()) == 2):
            # Check for "ping N" format
            if msg.startswith("ping ") and len(msg.split()) == 2:
                try:
                    ping_count = int(msg.split()[1])
                    if ping_count < 1 or ping_count > 5:
                        ping_count = 1  # Default to 1 if out of range
                except ValueError:
                    ping_count = 1  # Default to 1 if not a valid number
            elif msg not in TRIGGERS:
                return  # Not a valid trigger
                
            now = time.time()
            if sender_id in last_reply_time and (now - last_reply_time[sender_id]) < REPLY_COOLDOWN:
                log_console_and_web(f"Rate-limited reply to {sender}", "yellow")
                return

            last_reply_time[sender_id] = now
            rssi, snr = extract_rssi_snr(packet)
            hop_start = packet.get("hopStart", None)
            hop_limit = packet.get("hopLimit", None)
            hop_count = hop_start - hop_limit if hop_start and hop_limit else None

            # Generate multiple pong responses based on ping_count
            reply_messages = []
            for i in range(ping_count):
                reply = f"pong ({timestamp()}) RSSI: {rssi} SNR: {snr}"
                if hop_count is not None:
                    reply += f" Hops: {hop_count}/{hop_start}"
                
                # Split each reply into multiple messages if needed
                split_replies = split_message(reply)
                reply_messages.extend(split_replies)
            
            # Send replies asynchronously to avoid blocking message reception
            send_messages_async(interface, reply_messages, packet["fromId"], sender, "Reply")
            
    except Exception as e:
        # Log error without exposing sensitive details
        log_console_and_web("Error processing incoming message", "red")


def handle_socket_error():
    """Handle socket errors detected from any source"""
    global is_connected, socket_error_count
    
    with socket_error_lock:
        socket_error_count += 1
        if socket_error_count >= 1:  # Immediate response to socket errors
            if is_connected:
                log_console_and_web("Socket error detected - marking connection as failed", "red")
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
                log_console_and_web("Attempting connection to radio...", "yellow")
                log_web("Attempting connection to radio...", "yellow")
                
                with connection_lock:
                    cleanup_interface()
                    
                    try:
                        # Create interface based on connection type
                        if CONNECTION_TYPE == "serial":
                            if SERIAL_DEVICE:
                                log_console_and_web(f"Connecting via serial to {SERIAL_DEVICE}...", "yellow")
                                log_web(f"Connecting via serial to {SERIAL_DEVICE}...", "yellow")
                                interface = meshtastic.serial_interface.SerialInterface(devPath=SERIAL_DEVICE)
                            else:
                                log_console_and_web("Connecting via serial (auto-detect)...", "yellow")
                                log_web("Connecting via serial (auto-detect)...", "yellow")
                                interface = meshtastic.serial_interface.SerialInterface()
                        else:  # tcp
                            log_console_and_web(f"Connecting via TCP to {DEVICE_IP}...", "yellow")
                            log_web(f"Connecting via TCP to {DEVICE_IP}...", "yellow")
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
                            set_local_radio_name(local_radio_name)
                            if local_radio_name:
                                log_console_and_web(f"Retrieved local radio name: {local_radio_name}", "cyan")
                                log_web(f"Retrieved local radio name: {local_radio_name}", "cyan")
                            else:
                                log_console_and_web("Could not retrieve local radio name", "yellow")
                                log_web("Could not retrieve local radio name", "yellow")
                        except Exception as e:
                            log_console_and_web("Failed to retrieve local radio name", "yellow")
                            log_web("Failed to retrieve local radio name", "yellow")
                            local_radio_name = ""
                        
                        # Download nodedb after successful connection
                        try:
                            from database import cleanup_old_nodes
                            # Import these functions dynamically to avoid circular imports
                            try:
                                from database import enhanced_download_nodedb, schedule_periodic_nodedb_refresh
                            except ImportError:
                                # These functions need to be implemented in database module
                                def enhanced_download_nodedb(interface):
                                    log_console_and_web("NodeDB download placeholder - not implemented", "yellow")
                                    return True
                                def schedule_periodic_nodedb_refresh(interface, hours):
                                    log_console_and_web("NodeDB refresh scheduling placeholder - not implemented", "yellow")
                            
                            enhanced_download_nodedb(interface)
                            # Clean up old nodes (older than 30 days)
                            cleanup_old_nodes(30)
                            # Schedule periodic nodedb refresh (every 6 hours)
                            schedule_periodic_nodedb_refresh(interface, 6)
                        except Exception as e:
                            log_console_and_web(f"Failed to download nodedb: {e}", "yellow")
                            log_web(f"Failed to download nodedb: {e}", "yellow")
                        
                        log_console_and_web("Connected to Meshtastic radio", "green", True)
                        log_web("Connected to Meshtastic radio", "green", True)
                        
                    except (BrokenPipeError, ConnectionResetError, OSError) as e:
                        log_console_and_web("Connection failed: socket error during interface creation", "red")
                        log_web("Connection failed: socket error during interface creation", "red")
                        cleanup_interface()
                        raise
                    except Exception as e:
                        log_console_and_web("Connection failed: unable to create interface", "red")
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
                log_console_and_web("Connection health check failed: socket error detected", "red")
                log_web("Connection health check failed: socket error detected", "red")
                handle_socket_error()
                with connection_lock:
                    cleanup_interface()
                continue
            except Exception as e:
                # For other exceptions, don't immediately fail the connection
                # but log the issue
                log_console_and_web("Connection health check warning: operation failed", "yellow")
                log_web("Connection health check warning: operation failed", "yellow")
                connection_healthy = True  # Don't fail on non-socket errors
            
            if connection_healthy:
                time.sleep(10)  # Check more frequently to catch issues sooner
            
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            log_console_and_web("Connection failed: socket error (radio disconnected)", "red")
            handle_socket_error()
            
            with connection_lock:
                cleanup_interface()
            
            if not shutdown_event.is_set():
                log_console_and_web(f"Retrying in {backoff} seconds...", "yellow")
                shutdown_event.wait(backoff)
                backoff = min(backoff * 2, max_backoff)
        except Exception as e:
            is_connected = False
            # Don't expose detailed error information
            log_console_and_web("Connection failed: unable to connect to radio", "red")
            
            with connection_lock:
                cleanup_interface()
            
            if not shutdown_event.is_set():
                log_console_and_web(f"Retrying in {backoff} seconds...", "yellow")
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
        log_console_and_web("Failed to establish initial connection within timeout", "red")
        raise ConnectionError("Failed to connect to radio")
    
    return interface


def enhanced_download_nodedb(interface, retry_on_failure=True):
    """Enhanced nodedb download with retry logic - placeholder for now"""
    # This function will be implemented by importing from database or other module
    pass


def schedule_periodic_nodedb_refresh(interface, interval_hours=24):
    """Schedule periodic nodedb refresh - placeholder for now"""
    # This function will be implemented by importing from database or other module
    pass


def setup_exception_handlers():
    """Setup custom exception handlers for socket error detection"""
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


def stop_connection():
    """Stop the connection gracefully"""
    global shutdown_event
    shutdown_event.set()
    cleanup_interface()