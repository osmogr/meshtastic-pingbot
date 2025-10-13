#!/usr/bin/env python3
"""End-to-end demonstration of scheduled messages feature."""

import sys
import os
import datetime
from zoneinfo import ZoneInfo

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def demonstrate_feature():
    """Demonstrate the scheduled messages feature."""
    print("=" * 70)
    print("Scheduled Messages Feature Demonstration")
    print("=" * 70)
    
    # Import configuration
    from config import (
        LATITUDE, LONGITUDE, TIMEZONE,
        ENABLE_SCHEDULED_GREETINGS,
        GOOD_MORNING_OFFSET_HOURS,
        GOOD_EVENING_OFFSET_MINUTES
    )
    
    print("\n1. Configuration")
    print("-" * 70)
    print(f"   Feature enabled: {ENABLE_SCHEDULED_GREETINGS}")
    print(f"   Location: {LATITUDE}, {LONGITUDE}")
    print(f"   Timezone: {TIMEZONE}")
    print(f"   Morning greeting: {GOOD_MORNING_OFFSET_HOURS} hour(s) after sunrise")
    print(f"   Evening greeting: {GOOD_EVENING_OFFSET_MINUTES} minute(s) after sunset")
    
    # Calculate greeting times
    from scheduled_messages import calculate_greeting_times
    
    print("\n2. Sunrise/Sunset Calculation")
    print("-" * 70)
    
    morning_time, evening_time = calculate_greeting_times()
    
    if not morning_time or not evening_time:
        print("   ✗ Failed to calculate greeting times")
        return False
    
    # Get current time
    tz = ZoneInfo(TIMEZONE)
    now = datetime.datetime.now(tz)
    
    print(f"   Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"   Good Morning scheduled at: {morning_time.strftime('%H:%M:%S')}")
    print(f"   Good Evening scheduled at: {evening_time.strftime('%H:%M:%S')}")
    
    # Show time until next greeting
    print("\n3. Next Greeting Status")
    print("-" * 70)
    
    if now < morning_time:
        time_until = morning_time - now
        hours = int(time_until.total_seconds() // 3600)
        minutes = int((time_until.total_seconds() % 3600) // 60)
        print(f"   Next greeting: Good Morning")
        print(f"   Time until greeting: {hours}h {minutes}m")
    elif now < evening_time:
        time_until = evening_time - now
        hours = int(time_until.total_seconds() // 3600)
        minutes = int((time_until.total_seconds() % 3600) // 60)
        print(f"   Next greeting: Good Evening")
        print(f"   Time until greeting: {hours}h {minutes}m")
        print(f"   (Good Morning already sent today)")
    else:
        print(f"   All greetings sent for today")
        print(f"   Next greeting: Good Morning tomorrow at {morning_time.strftime('%H:%M')}")
    
    # Demonstrate message format
    print("\n4. Message Format")
    print("-" * 70)
    print("   Messages that will be broadcast:")
    print("   • 'Good Morning' - sent to all nodes on the mesh")
    print("   • 'Good Evening' - sent to all nodes on the mesh")
    
    # Show how to customize
    print("\n5. Customization")
    print("-" * 70)
    print("   You can customize the feature using environment variables:")
    print("   ")
    print("   # Set your location")
    print("   export LATITUDE=\"40.7128\"")
    print("   export LONGITUDE=\"-74.0060\"")
    print("   export TIMEZONE=\"America/New_York\"")
    print("   ")
    print("   # Disable scheduled greetings if desired")
    print("   export ENABLE_SCHEDULED_GREETINGS=\"false\"")
    
    print("\n" + "=" * 70)
    print("Feature demonstration complete!")
    print("=" * 70)
    
    return True


def main():
    """Run demonstration."""
    try:
        success = demonstrate_feature()
        return 0 if success else 1
    except Exception as e:
        print(f"\nError during demonstration: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
