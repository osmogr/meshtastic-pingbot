#!/usr/bin/env python3
"""Test script for nodedb JSON import/export functionality."""

import sys
import json
import time

# Add the current directory to path
sys.path.insert(0, '.')

from database import init_database, export_nodedb_to_json, import_nodedb_from_json, get_nodedb_statistics

def test_json_export_import():
    """Test exporting and importing nodedb in JSON format"""
    print("Testing nodedb JSON import/export functionality...")
    
    # Initialize database
    print("\n1. Initializing database...")
    if not init_database():
        print("❌ Failed to initialize database")
        return False
    print("✓ Database initialized")
    
    # Export nodedb to JSON
    print("\n2. Exporting nodedb to JSON...")
    json_data = export_nodedb_to_json()
    if not json_data:
        print("❌ Failed to export nodedb")
        return False
    
    # Parse and validate JSON structure
    try:
        data = json.loads(json_data)
        print(f"✓ Exported {len(data.get('nodes', []))} nodes")
        print(f"✓ JSON structure: {list(data.keys())}")
        
        # Display sample node if available
        if data.get('nodes'):
            sample_node = data['nodes'][0]
            print(f"✓ Sample node ID: {sample_node.get('user', {}).get('id', 'N/A')}")
            print(f"✓ Sample node name: {sample_node.get('user', {}).get('longName', 'N/A')}")
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return False
    
    # Test import functionality (dry run - import the same data)
    print("\n3. Testing JSON import...")
    
    # Create test data
    test_data = {
        "nodes": [
            {
                "user": {
                    "id": "!test0001",
                    "longName": "Test Node 1",
                    "shortName": "TST1",
                    "hwModel": 1,
                    "role": 0,
                    "isLicensed": False
                },
                "lastHeard": int(time.time()),
                "snr": 5.5,
                "rssi": -80
            },
            {
                "user": {
                    "id": "!test0002",
                    "longName": "Test Node 2",
                    "shortName": "TST2",
                    "hwModel": 2,
                    "role": 1,
                    "isLicensed": True
                },
                "lastHeard": int(time.time()),
                "snr": 8.2,
                "rssi": -75
            }
        ],
        "exportedAt": int(time.time()),
        "totalNodes": 2
    }
    
    success = import_nodedb_from_json(test_data)
    if not success:
        print("❌ Failed to import test data")
        return False
    print("✓ Test data imported successfully")
    
    # Get statistics
    print("\n4. Checking nodedb statistics...")
    stats = get_nodedb_statistics()
    if stats:
        print(f"✓ Total nodes: {stats['total_nodes']}")
        print(f"✓ Complete nodes: {stats['complete_nodes']}")
        print(f"✓ Recent nodes: {stats['recent_nodes']}")
        print(f"✓ Completion rate: {stats['completion_rate']:.1f}%")
    else:
        print("❌ Failed to get statistics")
        return False
    
    print("\n✅ All tests passed!")
    return True

if __name__ == "__main__":
    try:
        success = test_json_export_import()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
