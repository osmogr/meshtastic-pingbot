"""Traceroute functionality for Meshtastic PingBot."""

import queue
import time
import threading
from collections import defaultdict
from config import TRACEROUTE_RATE_LIMIT, MAX_QUEUE_PER_USER

# Traceroute system globals
last_traceroute_time = 0
TRACEROUTE_TIMEOUT = 15  # seconds to wait for traceroute response

# User-specific traceroute queues
traceroute_queues = defaultdict(list)  # user_id -> list of pending requests

# Traceroute processing 
traceroute_queue = queue.Queue()
traceroute_shutdown = threading.Event()
traceroute_thread = None
pending_traceroutes = {}  # Keep track of pending traceroute requests by user

# Message splitting
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
    from logging_utils import log_console_and_web, log_web
    import time
    
    # Import these dynamically to avoid circular imports
    try:
        from meshtastic_handler import get_connection_status, update_message_queue_count, handle_socket_error, cleanup_interface, connection_lock
    except ImportError:
        # Fallback for testing or standalone use
        def get_connection_status():
            return True, 0
        def update_message_queue_count(delta):
            pass
        def handle_socket_error():
            pass
        def cleanup_interface():
            pass
        import threading
        connection_lock = threading.Lock()
    
    is_connected, message_queue_count = get_connection_status()
    
    if not interface or not is_connected:
        log_console_and_web("Cannot send messages: not connected", "red")
        return False
    
    success_count = 0
    total_messages = len(messages)
    
    for i, message in enumerate(messages, 1):
        try:
            update_message_queue_count(1)
            interface.sendText(message, destinationId=destination_id)
            update_message_queue_count(-1)
            success_count += 1
            
            # Small delay between messages to avoid overwhelming the radio
            if i < total_messages:
                time.sleep(0.5)
                
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            update_message_queue_count(-1)
            log_console_and_web(f"Failed to send message {i}/{total_messages}: socket error (connection lost)", "red")
            handle_socket_error()
            # Trigger immediate cleanup in background
            with connection_lock:
                cleanup_interface()
            return False
        except Exception as e:
            update_message_queue_count(-1)
            log_console_and_web(f"Failed to send message {i}/{total_messages}: operation error", "red")
            # Don't mark as disconnected for non-socket errors, but still fail the send
            return False
    
    return success_count == total_messages


def send_messages_async(interface, messages, destination_id, sender_name, message_type="Reply"):
    """
    Send messages asynchronously in a separate thread to avoid blocking message reception.
    """
    from logging_utils import log_console_web_and_discord
    
    def send_task():
        try:
            success = send_multiple_messages(interface, messages, destination_id)
            
            if success:
                if len(messages) == 1:
                    console = f"{message_type} -> {sender_name}: {messages[0]}"
                else:
                    console = f"{message_type} -> {sender_name}: {len(messages)} message{'s' if len(messages) > 1 else ''}"
                log_console_web_and_discord(console, "green")
            else:
                console = f"Failed to send {message_type.lower()} -> {sender_name}"
                log_console_web_and_discord(console, "red")
        except Exception as e:
            console = f"Error sending {message_type.lower()} -> {sender_name}: {e}"
            log_console_web_and_discord(console, "red")
    
    # Start the sending task in a separate thread
    thread = threading.Thread(target=send_task, daemon=True)
    thread.start()
    return thread


def queue_traceroute(interface, destination_id, sender_name, sender_id):
    """
    Queue a traceroute request for a user, respecting per-user limits.
    """
    # Check user queue limit
    user_queue = traceroute_queues[sender_id]
    if len(user_queue) >= MAX_QUEUE_PER_USER:
        return False, f"Queue full (max {MAX_QUEUE_PER_USER} per user)"
    
    # Add to user queue
    request_data = {
        'interface': interface,
        'destination_id': destination_id,
        'sender_name': sender_name,
        'sender_id': sender_id,
        'target_id': destination_id  # For Meshtastic traceroute, we trace to the sender
    }
    user_queue.append(request_data)
    
    # Add to processing queue
    traceroute_queue.put(request_data)
    
    # Calculate position in overall queue
    queue_position = traceroute_queue.qsize()
    
    return True, f"Queued (position {queue_position}, max wait ~{queue_position * TRACEROUTE_RATE_LIMIT}s)"


def custom_traceroute_response_handler(packet, pending_request):
    """
    Custom handler for traceroute responses that formats and sends results properly.
    This bypasses the Meshtastic library's print() statements.
    """
    from logging_utils import log_console_and_web, log_web
    import datetime
    
    try:
        interface = pending_request['interface']
        destination_id = pending_request['destination_id']
        sender_name = pending_request['sender_name']
        
        # Parse the RouteDiscovery payload
        from meshtastic import mesh_pb2, portnums_pb2
        import google.protobuf.json_format
        
        decoded = packet.get("decoded", {})
        payload = decoded.get("payload", b"")
        
        if not payload:
            log_console_and_web(f"No payload in traceroute response for {sender_name}", "yellow")
            error_msg = "Traceroute completed but no route data available"
            reply_messages = split_message(error_msg)
            send_messages_async(interface, reply_messages, destination_id, sender_name, "Traceroute")
            return
        
        route_discovery = mesh_pb2.RouteDiscovery()
        route_discovery.ParseFromString(payload)
        route_dict = google.protobuf.json_format.MessageToDict(route_discovery)
        
        # Format the traceroute result
        result_lines = []
        result_lines.append(f"Traceroute to {sender_name}:")
        
        # Constants
        UNK_SNR = -128
        
        # Format route towards destination
        route_list = route_dict.get("route", [])
        snr_towards = route_dict.get("snrTowards", [])
        
        from_id = packet.get("from")
        to_id = packet.get("to")
        
        # Build the forward route
        log_console_and_web(f"Route traced towards destination:", "cyan")
        route_str = f"!{to_id:08x}"  # Start with destination (bot)
        
        len_towards = len(route_list)
        snr_towards_valid = len(snr_towards) == len_towards + 1
        
        if len_towards > 0:
            for idx, node_num in enumerate(route_list):
                node_id = f"!{node_num:08x}"
                snr_str = ""
                if snr_towards_valid and idx < len(snr_towards) and snr_towards[idx] != UNK_SNR:
                    snr_val = snr_towards[idx] / 4.0
                    snr_str = f" ({snr_val:.1f}dB)"
                route_str += f" --> {node_id}{snr_str}"
        
        # End with origin (the node that requested traceroute)
        final_snr_str = ""
        if snr_towards_valid and len(snr_towards) > 0 and snr_towards[-1] != UNK_SNR:
            snr_val = snr_towards[-1] / 4.0
            final_snr_str = f" ({snr_val:.1f}dB)"
        route_str += f" --> !{from_id:08x}{final_snr_str}"
        
        log_console_and_web(route_str, "green")
        result_lines.append(f"\nRoute traced towards destination:")
        result_lines.append(route_str)
        
        # Check for return route
        route_back = route_dict.get("routeBack", [])
        snr_back = route_dict.get("snrBack", [])
        hop_start = packet.get("hopStart")
        
        len_back = len(route_back)
        back_valid = hop_start is not None and len(snr_back) == len_back + 1
        
        if back_valid:
            log_console_and_web(f"Route traced back to us:", "cyan")
            back_route_str = f"!{from_id:08x}"  # Start with origin
            
            if len_back > 0:
                for idx, node_num in enumerate(route_back):
                    node_id = f"!{node_num:08x}"
                    snr_str = ""
                    if idx < len(snr_back) and snr_back[idx] != UNK_SNR:
                        snr_val = snr_back[idx] / 4.0
                        snr_str = f" ({snr_val:.1f}dB)"
                    back_route_str += f" --> {node_id}{snr_str}"
            
            # End with destination (us/bot)
            final_back_snr_str = ""
            if len(snr_back) > 0 and snr_back[-1] != UNK_SNR:
                snr_val = snr_back[-1] / 4.0
                final_back_snr_str = f" ({snr_val:.1f}dB)"
            back_route_str += f" --> !{to_id:08x}{final_back_snr_str}"
            
            log_console_and_web(back_route_str, "green")
            result_lines.append(f"\nRoute traced back to us:")
            result_lines.append(back_route_str)
        
        # Add hop count
        hop_count = len_towards
        if hop_count == 0:
            result_lines.append("\nDirect connection (0 hops)")
        else:
            result_lines.append(f"\nTotal hops: {hop_count}")
        
        # Add timestamp
        current_timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        result_lines.append(f"Completed at: {current_timestamp}")
        
        result_msg = "\n".join(result_lines)
        
        # Send the result back to the user
        reply_messages = split_message(result_msg)
        send_messages_async(interface, reply_messages, destination_id, sender_name, "Traceroute")
        
        log_console_and_web(f"Traceroute completed for {sender_name}", "green")
        
    except Exception as e:
        log_console_and_web(f"Error in custom traceroute handler: {e}", "red")
        # Send error message to user
        error_msg = f"Traceroute completed but error formatting results: {str(e)[:50]}"
        reply_messages = split_message(error_msg)
        send_messages_async(interface, reply_messages, destination_id, sender_name, "Traceroute")


def traceroute_worker():
    """
    Worker thread that processes traceroute requests with rate limiting.
    """
    from logging_utils import log_console_and_web, log_web
    global last_traceroute_time
    
    while not traceroute_shutdown.is_set():
        try:
            # Wait for a request (blocking with timeout)
            request_data = traceroute_queue.get(timeout=1.0)
            if request_data is None:  # Shutdown signal
                break
            
            interface = request_data['interface']
            destination_id = request_data['destination_id']
            sender_name = request_data['sender_name']
            sender_id = request_data['sender_id']
            target_id = request_data['target_id']
            
            # Remove from user queue
            user_queue = traceroute_queues[sender_id]
            if request_data in user_queue:
                user_queue.remove(request_data)
            
            # Check if we need to wait for rate limiting
            current_time = time.time()
            time_since_last = current_time - last_traceroute_time
            
            if time_since_last < TRACEROUTE_RATE_LIMIT:
                wait_time = TRACEROUTE_RATE_LIMIT - time_since_last
                log_console_and_web(f"Traceroute rate limit: waiting {wait_time:.1f}s for {sender_name}", "yellow")
                time.sleep(wait_time)
            
            # Update last traceroute time
            last_traceroute_time = time.time()
            
            # Run the Meshtastic traceroute
            log_console_and_web(f"Running Meshtastic traceroute for {sender_name}...", "cyan")
            
            # Notify the user that traceroute is starting
            start_msg = "Starting traceroute..."
            start_messages = split_message(start_msg)
            send_messages_async(interface, start_messages, destination_id, sender_name, "Traceroute Start")
            
            try:
                # Store the pending request so we can match the response
                # Store all request data for the custom handler
                pending_traceroutes[sender_id] = {
                    'interface': interface,
                    'destination_id': destination_id,
                    'sender_name': sender_name,
                    'target_node_id': target_id,  # This is the node we're tracing to
                    'timestamp': time.time()
                }
                
                log_console_and_web(f"Sending traceroute to {target_id} for {sender_name}", "cyan")
                
                # Send the traceroute request using custom method that bypasses the default print() handler
                # We'll use sendData directly with our custom callback
                
                try:
                    from meshtastic import mesh_pb2, portnums_pb2
                    
                    # Create RouteDiscovery message
                    route_discovery = mesh_pb2.RouteDiscovery()
                    
                    # Define our custom response handler closure
                    def on_custom_traceroute_response(packet):
                        """Custom callback that captures the response and formats it properly"""
                        try:
                            if sender_id in pending_traceroutes:
                                pending_request = pending_traceroutes[sender_id]
                                custom_traceroute_response_handler(packet, pending_request)
                                # Remove from pending after handling
                                if sender_id in pending_traceroutes:
                                    del pending_traceroutes[sender_id]
                        except Exception as e:
                            log_console_and_web(f"Error in traceroute callback: {e}", "red")
                    
                    # Send the traceroute using sendData with our custom callback
                    interface.sendData(
                        route_discovery,
                        destinationId=target_id,
                        portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
                        wantResponse=True,
                        onResponse=on_custom_traceroute_response,
                        channelIndex=0,
                        hopLimit=10,
                    )
                    
                    # Wait for response with timeout
                    log_console_and_web(f"Waiting {TRACEROUTE_TIMEOUT}s for traceroute response from {sender_name}", "cyan")
                    
                    # Custom wait implementation
                    start_time = time.time()
                    while sender_id in pending_traceroutes and (time.time() - start_time) < TRACEROUTE_TIMEOUT:
                        time.sleep(0.5)
                    
                    # Check if the traceroute was completed (removed from pending)
                    if sender_id not in pending_traceroutes:
                        # Success - response was handled by our custom handler
                        log_console_and_web(f"Traceroute completed for {sender_name}", "green")
                    else:
                        # Timed out - clean up and send timeout message
                        log_console_and_web(f"Traceroute timed out for {sender_name} - no response received", "yellow")
                        
                        del pending_traceroutes[sender_id]
                        error_msg = "Traceroute timed out - no response received. The node may be offline or out of range."
                        reply_messages = split_message(error_msg)
                        send_messages_async(interface, reply_messages, destination_id, sender_name, "Traceroute")
                    
                except Exception as timeout_error:
                    # Traceroute timed out or failed
                    log_console_and_web(f"Traceroute error for {sender_name}: {str(timeout_error)[:100]}", "red")
                    
                    if sender_id in pending_traceroutes:
                        del pending_traceroutes[sender_id]
                    
                    error_msg = f"Traceroute failed: {str(timeout_error)[:50]}"
                    reply_messages = split_message(error_msg)
                    send_messages_async(interface, reply_messages, destination_id, sender_name, "Traceroute")
                
            except Exception as e:
                # Clean up pending request on error
                log_console_and_web(f"Traceroute exception for {sender_name}: {str(e)[:100]}", "red")
                
                if sender_id in pending_traceroutes:
                    del pending_traceroutes[sender_id]
                
                error_msg = f"Traceroute failed: {str(e)[:100]}"
                reply_messages = split_message(error_msg)
                send_messages_async(interface, reply_messages, destination_id, sender_name, "Traceroute")
            
            # Mark task as done
            traceroute_queue.task_done()
            
        except queue.Empty:
            continue  # Timeout, check shutdown flag
        except Exception as e:
            log_console_and_web(f"Traceroute worker error: {e}", "red")


def start_traceroute_worker():
    """
    Start the traceroute worker thread.
    """
    from logging_utils import log_console_and_web, log_web
    global traceroute_thread
    if traceroute_thread is None or not traceroute_thread.is_alive():
        traceroute_thread = threading.Thread(target=traceroute_worker, daemon=True, name="TracerouteWorker")
        traceroute_thread.start()
        log_console_and_web("Meshtastic traceroute worker started", "green")


def stop_traceroute_worker():
    """Stop the traceroute worker thread."""
    global traceroute_shutdown
    traceroute_shutdown.set()
    if traceroute_queue:
        traceroute_queue.put(None)  # Signal shutdown