# Traceroute Rate Limiting Implementation

## Overview
The traceroute module implements a robust queuing and rate-limiting system to comply with Meshtastic firmware's constraint of one traceroute every 30 seconds.

## Problem Statement
The Meshtastic firmware has a hard limit of allowing one traceroute request every 30 seconds. Without proper rate limiting, rapid traceroute requests would cause firmware rejections and timeouts.

## Solution Architecture

### Components

1. **Request Queue** (`traceroute_queue`)
   - Thread-safe FIFO queue using Python's `queue.Queue()`
   - Holds all pending traceroute requests
   - Processed sequentially by worker thread

2. **Per-User Queue Tracking** (`traceroute_queues`)
   - Dictionary mapping `user_id` to list of their pending requests
   - Enforces MAX_QUEUE_PER_USER limit (default: 2 per user)
   - Prevents any single user from monopolizing the queue

3. **Rate Limiting Tracker** (`last_traceroute_time`)
   - Global timestamp of the last traceroute sent
   - Used to calculate time elapsed since last send
   - Ensures exactly TRACEROUTE_RATE_LIMIT (30) seconds between sends

4. **Worker Thread** (`traceroute_worker`)
   - Background daemon thread
   - Continuously processes requests from the queue
   - Enforces rate limiting before each send
   - Started automatically on bot startup

## Request Flow

```
User sends "traceroute" command
    ↓
queue_traceroute() called
    ↓
Check per-user queue limit
    ↓
Add to user queue + global queue
    ↓
Return queue position to user
    ↓
Worker thread dequeues request
    ↓
Check time since last traceroute
    ↓
Wait if needed (< 30 seconds)
    ↓
Send traceroute request
    ↓
Wait for response (15s timeout)
    ↓
Format and send results
    ↓
Process next request in queue
```

## Rate Limiting Logic

```python
# Check if we need to wait for rate limiting
current_time = time.time()
time_since_last = current_time - last_traceroute_time

if time_since_last < TRACEROUTE_RATE_LIMIT:
    wait_time = TRACEROUTE_RATE_LIMIT - time_since_last
    time.sleep(wait_time)

# Update last traceroute time
last_traceroute_time = time.time()

# Send traceroute...
```

This ensures exactly 30 seconds elapse between successive traceroute sends, regardless of:
- How many requests are queued
- How quickly requests arrive
- Whether previous traceroutes succeeded or failed

## Configuration

### Constants (config.py)
```python
TRACEROUTE_RATE_LIMIT = 30  # seconds between traceroutes globally
MAX_QUEUE_PER_USER = 2      # Maximum queued traceroutes per user
```

### Module Constants (traceroute.py)
```python
TRACEROUTE_TIMEOUT = 15  # seconds to wait for traceroute response
MAX_MESSAGE_LENGTH = 200 # Meshtastic practical message limit
```

## User Experience

### Successful Queue
```
User: "traceroute"
Bot: "Traceroute queued: Queued (position 1, max wait ~30s)"
[Wait if needed for rate limit]
Bot: "Starting traceroute..."
[Send traceroute, wait for response]
Bot: [Traceroute results with hop details]
```

### Queue Full
```
User: "traceroute"
Bot: "Traceroute failed: Queue full (max 2 per user)"
```

### Multiple Requests
```
User1: "traceroute"  @ T+0s
Bot: "Queued (position 1, max wait ~30s)"

User2: "traceroute"  @ T+5s
Bot: "Queued (position 2, max wait ~60s)"

T+0s:  Send User1's traceroute
T+30s: Send User2's traceroute (30s after User1)
```

## Key Features

### 1. Global Rate Limiting
- Single global timer for all users
- Firmware-compliant 30-second spacing
- Prevents firmware rejections

### 2. Per-User Queue Limits
- Each user can queue MAX_QUEUE_PER_USER requests
- Prevents queue monopolization
- Fair access for all users

### 3. FIFO Processing
- First-come, first-served request processing
- Predictable wait times
- Queue position feedback to users

### 4. Robust Error Handling
- Graceful handling of timeouts
- Exception recovery
- User notification of errors

### 5. Thread Safety
- Thread-safe Queue for request handling
- Global variable with proper locking
- No race conditions

## Testing

### Unit Tests
See `/tmp/test_traceroute_rate_limit.py` for:
- Queue limit enforcement
- Initial request timing
- Basic queuing functionality

### Integration Tests
See `/tmp/test_traceroute_timing.py` for:
- Actual rate limiting timing verification
- Multiple concurrent requests
- Queue processing order

### Test Results
All tests pass with exact 30-second (or configured) spacing between traceroute sends.

## Edge Cases Handled

1. **Bot Restart**: `last_traceroute_time = 0` ensures first request is sent immediately
2. **Queue Empty**: Worker thread waits efficiently without busy-waiting
3. **Request Timeout**: Cleans up pending request and processes next in queue
4. **Send Failure**: Error reported to user, queue continues processing
5. **User Disconnect**: Request completed normally, response sent when possible

## Performance Characteristics

- **Memory**: O(n) where n = total queued requests
- **CPU**: Minimal (worker sleeps when waiting)
- **Latency**: 
  - First request: ~0-1 seconds
  - Nth request: ~(N-1) * 30 seconds
- **Throughput**: 1 traceroute per 30 seconds (firmware limit)

## Future Improvements

Potential enhancements (not currently needed):
1. Persistent queue across bot restarts
2. Priority queue for admin users
3. Queue expiration (auto-remove old requests)
4. Metrics tracking (queue depth, wait times)
5. Dynamic rate limit adjustment
6. Multiple firmware device support

## Conclusion

The implementation successfully addresses the Meshtastic firmware limitation through:
- ✅ Queuing system for request management
- ✅ Rate limiting to respect 30-second firmware constraint
- ✅ Per-user limits for fairness
- ✅ Robust error handling
- ✅ Clear user feedback

The system has been tested and verified to enforce exact 30-second spacing between traceroute sends, preventing firmware rejections and ensuring reliable operation.
