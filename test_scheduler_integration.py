#!/usr/bin/env python3
"""Integration test for scheduled messages - simulates scheduler behavior."""

import sys
import os
import datetime
from zoneinfo import ZoneInfo

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_scheduler_logic():
    """Test the scheduler logic with various scenarios."""
    from scheduled_messages import calculate_greeting_times
    from config import TIMEZONE, GOOD_MORNING_OFFSET_HOURS, GOOD_EVENING_OFFSET_MINUTES
    
    print("\n" + "=" * 60)
    print("Testing Scheduler Logic")
    print("=" * 60)
    
    # Get current time in the configured timezone
    tz = ZoneInfo(TIMEZONE)
    now = datetime.datetime.now(tz)
    
    print(f"\nCurrent time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Calculate greeting times
    morning_time, evening_time = calculate_greeting_times()
    
    if not morning_time or not evening_time:
        print("✗ Failed to calculate greeting times")
        return False
    
    print(f"\nCalculated greeting times for today:")
    print(f"  Good Morning: {morning_time.strftime('%H:%M:%S')}")
    print(f"  Good Evening: {evening_time.strftime('%H:%M:%S')}")
    
    # Test various time scenarios
    print("\nTesting scheduling scenarios:")
    
    # Scenario 1: Before morning greeting
    test_time = morning_time - datetime.timedelta(minutes=5)
    morning_passed = test_time >= morning_time
    evening_passed = test_time >= evening_time
    print(f"\n  Scenario 1: 5 minutes before morning greeting")
    print(f"    Time: {test_time.strftime('%H:%M:%S')}")
    print(f"    Should send morning: {morning_passed} (expected: False)")
    print(f"    Should send evening: {evening_passed} (expected: False)")
    
    # Scenario 2: After morning greeting, before evening greeting
    test_time = morning_time + datetime.timedelta(minutes=5)
    morning_passed = test_time >= morning_time
    evening_passed = test_time >= evening_time
    print(f"\n  Scenario 2: 5 minutes after morning greeting")
    print(f"    Time: {test_time.strftime('%H:%M:%S')}")
    print(f"    Should send morning: {morning_passed} (expected: True)")
    print(f"    Should send evening: {evening_passed} (expected: False)")
    
    # Scenario 3: After evening greeting
    test_time = evening_time + datetime.timedelta(minutes=5)
    morning_passed = test_time >= morning_time
    evening_passed = test_time >= evening_time
    print(f"\n  Scenario 3: 5 minutes after evening greeting")
    print(f"    Time: {test_time.strftime('%H:%M:%S')}")
    print(f"    Should send morning: {morning_passed} (expected: True)")
    print(f"    Should send evening: {evening_passed} (expected: True)")
    
    # Check configuration
    print(f"\nConfiguration:")
    print(f"  Morning offset: +{GOOD_MORNING_OFFSET_HOURS} hours after sunrise")
    print(f"  Evening offset: +{GOOD_EVENING_OFFSET_MINUTES} minutes after sunset")
    
    return True


def test_message_sending_mock():
    """Test that message sending can be called (with mock interface)."""
    print("\n" + "=" * 60)
    print("Testing Message Sending (Mock)")
    print("=" * 60)
    
    try:
        from scheduled_messages import send_greeting_message
        
        # Create a mock interface
        class MockInterface:
            def sendText(self, message, destinationId=None):
                print(f"  [MOCK] Would send: '{message}' to {destinationId}")
        
        mock_interface = MockInterface()
        
        print("\nTesting greeting message send (mock):")
        send_greeting_message(mock_interface, "Good Morning")
        send_greeting_message(mock_interface, "Good Evening")
        
        print("\n✓ Message sending logic works")
        return True
        
    except Exception as e:
        print(f"\n✗ Error testing message sending: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("Scheduled Messages Integration Tests")
    print("=" * 60)
    
    results = []
    
    results.append(test_scheduler_logic())
    results.append(test_message_sending_mock())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} integration tests passed")
    print("=" * 60)
    
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
