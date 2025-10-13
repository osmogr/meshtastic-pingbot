#!/usr/bin/env python3
"""Test script for scheduled_messages module."""

import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_import():
    """Test that the module can be imported."""
    try:
        import scheduled_messages
        print("✓ scheduled_messages module imported successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to import scheduled_messages: {e}")
        return False


def test_calculate_greeting_times():
    """Test the greeting time calculation."""
    try:
        from scheduled_messages import calculate_greeting_times
        
        morning_time, evening_time = calculate_greeting_times()
        
        if morning_time and evening_time:
            print(f"✓ Greeting times calculated successfully")
            print(f"  Morning: {morning_time.strftime('%H:%M:%S')}")
            print(f"  Evening: {evening_time.strftime('%H:%M:%S')}")
            return True
        else:
            print("✗ Failed to calculate greeting times (returned None)")
            return False
            
    except Exception as e:
        print(f"✗ Error calculating greeting times: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config():
    """Test configuration values."""
    try:
        from config import (
            LATITUDE, LONGITUDE, TIMEZONE,
            ENABLE_SCHEDULED_GREETINGS,
            GOOD_MORNING_OFFSET_HOURS,
            GOOD_EVENING_OFFSET_MINUTES
        )
        
        print("✓ Configuration loaded successfully")
        print(f"  Location: {LATITUDE}, {LONGITUDE}")
        print(f"  Timezone: {TIMEZONE}")
        print(f"  Enabled: {ENABLE_SCHEDULED_GREETINGS}")
        print(f"  Morning offset: {GOOD_MORNING_OFFSET_HOURS}h")
        print(f"  Evening offset: {GOOD_EVENING_OFFSET_MINUTES}m")
        return True
        
    except Exception as e:
        print(f"✗ Error loading configuration: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Scheduled Messages Module")
    print("=" * 60)
    
    results = []
    
    print("\n1. Testing configuration...")
    results.append(test_config())
    
    print("\n2. Testing module import...")
    results.append(test_import())
    
    print("\n3. Testing greeting time calculation...")
    results.append(test_calculate_greeting_times())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
