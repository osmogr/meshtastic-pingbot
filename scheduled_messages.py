"""Scheduled messages module for Meshtastic PingBot.

This module handles scheduled messages based on sunrise and sunset times.
It sends:
- "Good Morning" at 1 hour past sunrise
- "Good Evening" at 30 minutes after sunset
"""

import threading
import time
import datetime
from zoneinfo import ZoneInfo
from astral import LocationInfo
from astral.sun import sun

from config import (
    LATITUDE, LONGITUDE, TIMEZONE,
    ENABLE_SCHEDULED_GREETINGS,
    GOOD_MORNING_OFFSET_HOURS,
    GOOD_EVENING_OFFSET_MINUTES
)
from logging_utils import log_console_and_web
from traceroute import split_message, send_messages_async

# Scheduler globals
scheduler_thread = None
scheduler_shutdown = threading.Event()


def calculate_greeting_times():
    """Calculate the times for Good Morning and Good Evening messages.
    
    Returns:
        tuple: (morning_time, evening_time) as datetime objects, or (None, None) if calculation fails
    """
    try:
        # Create location info
        location = LocationInfo(
            name="Bot Location",
            region="",
            timezone=TIMEZONE,
            latitude=LATITUDE,
            longitude=LONGITUDE
        )
        
        # Get today's date in the specified timezone
        tz = ZoneInfo(TIMEZONE)
        today = datetime.datetime.now(tz).date()
        
        # Calculate sun times for today
        s = sun(location.observer, date=today, tzinfo=tz)
        sunrise = s['sunrise']
        sunset = s['sunset']
        
        # Calculate greeting times
        morning_time = sunrise + datetime.timedelta(hours=GOOD_MORNING_OFFSET_HOURS)
        evening_time = sunset + datetime.timedelta(minutes=GOOD_EVENING_OFFSET_MINUTES)
        
        log_console_and_web(
            f"Scheduled greetings calculated: Morning at {morning_time.strftime('%H:%M')}, "
            f"Evening at {evening_time.strftime('%H:%M')}",
            "cyan"
        )
        
        return morning_time, evening_time
        
    except Exception as e:
        log_console_and_web(f"Error calculating greeting times: {e}", "red")
        return None, None


def send_greeting_message(interface, message):
    """Send a greeting message to the mesh network.
    
    Args:
        interface: Meshtastic interface object
        message: The message to send
    """
    try:
        if not interface:
            log_console_and_web("Cannot send greeting: interface not available", "yellow")
            return
        
        # Import here to avoid circular imports
        from meshtastic_handler import get_connection_status
        
        is_connected, _ = get_connection_status()
        if not is_connected:
            log_console_and_web("Cannot send greeting: not connected", "yellow")
            return
        
        # Split message if needed and send
        messages = split_message(message)
        # Send to broadcast (destinationId=None or ^all)
        send_messages_async(interface, messages, "^all", "Broadcast", "Scheduled Greeting")
        
        log_console_and_web(f"Sent scheduled message: {message}", "green", True)
        
    except Exception as e:
        log_console_and_web(f"Error sending greeting message: {e}", "red")


def scheduler_worker(interface):
    """Worker thread that handles scheduled greetings.
    
    Args:
        interface: Meshtastic interface object
    """
    log_console_and_web("Scheduled greetings worker started", "green")
    
    # Track which greetings we've sent today
    last_morning_date = None
    last_evening_date = None
    morning_sent = False
    evening_sent = False
    
    while not scheduler_shutdown.is_set():
        try:
            # Get current time in the configured timezone
            tz = ZoneInfo(TIMEZONE)
            now = datetime.datetime.now(tz)
            today = now.date()
            
            # Reset daily flags if it's a new day
            if last_morning_date != today:
                morning_sent = False
                last_morning_date = today
            
            if last_evening_date != today:
                evening_sent = False
                last_evening_date = today
            
            # Calculate greeting times for today if we haven't sent them
            if not morning_sent or not evening_sent:
                morning_time, evening_time = calculate_greeting_times()
                
                if morning_time and evening_time:
                    # Check if it's time for Good Morning
                    if not morning_sent and now >= morning_time:
                        # Check if we haven't passed too far (e.g., within 5 minutes)
                        if (now - morning_time).total_seconds() < 300:
                            send_greeting_message(interface, "Good Morning")
                        morning_sent = True
                    
                    # Check if it's time for Good Evening
                    if not evening_sent and now >= evening_time:
                        # Check if we haven't passed too far (e.g., within 5 minutes)
                        if (now - evening_time).total_seconds() < 300:
                            send_greeting_message(interface, "Good Evening")
                        evening_sent = True
            
            # Sleep for 1 minute before checking again
            scheduler_shutdown.wait(60)
            
        except Exception as e:
            log_console_and_web(f"Error in scheduled greetings worker: {e}", "red")
            scheduler_shutdown.wait(60)
    
    log_console_and_web("Scheduled greetings worker stopped", "yellow")


def start_scheduler(interface):
    """Start the scheduled greetings worker thread.
    
    Args:
        interface: Meshtastic interface object
    """
    global scheduler_thread
    
    if not ENABLE_SCHEDULED_GREETINGS:
        log_console_and_web("Scheduled greetings disabled in configuration", "yellow")
        return
    
    if scheduler_thread and scheduler_thread.is_alive():
        log_console_and_web("Scheduled greetings worker already running", "yellow")
        return
    
    scheduler_shutdown.clear()
    scheduler_thread = threading.Thread(
        target=scheduler_worker,
        args=(interface,),
        daemon=True,
        name="ScheduledGreetings"
    )
    scheduler_thread.start()
    
    log_console_and_web(
        f"Scheduled greetings enabled: Morning at sunrise+{GOOD_MORNING_OFFSET_HOURS}h, "
        f"Evening at sunset+{GOOD_EVENING_OFFSET_MINUTES}m",
        "green",
        True
    )


def stop_scheduler():
    """Stop the scheduled greetings worker thread."""
    global scheduler_thread
    
    if scheduler_thread and scheduler_thread.is_alive():
        log_console_and_web("Stopping scheduled greetings worker...", "yellow")
        scheduler_shutdown.set()
        scheduler_thread.join(timeout=5)
        scheduler_thread = None
