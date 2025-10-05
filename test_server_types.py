#!/usr/bin/env python3
"""Manual integration test (excluded from automated pytest run).

Renamed semantics: This file is executed as a script and not structured with
pytest fixtures. To avoid collection errors (missing fixtures), we add a
pytest skip marker for automated runs. Execute manually via:

    python test_server_types.py

"""

import pytest
pytest.skip("Skipping manual integration script test_server_types.py during automated test run", allow_module_level=True)

import subprocess
import sys
import time
import requests
import json
from pathlib import Path

def test_server_creation(server_type, version, name):
    """Test creating a specific server type"""
    print(f"\n=== Testing {server_type} {version} Server Creation ===")
    
    # Create server via API
    server_data = {
        "name": name,
        "server_type": server_type,
        "version": version,
        "min_ram": 1,
        "max_ram": 2
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/servers",
            json=server_data,
            timeout=60
        )
        
        if response.status_code == 200:
            server_info = response.json()
            print(f"✅ {server_type} server created successfully")
            print(f"   Container ID: {server_info.get('container_id', 'N/A')}")
            print(f"   Status: {server_info.get('status', 'N/A')}")
            return server_info
        else:
            print(f"❌ Failed to create {server_type} server")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Exception creating {server_type} server: {e}")
        return None

def test_server_status(container_id):
    """Test server status and logs"""
    print(f"\n=== Testing Server Status for {container_id} ===")
    
    try:
        # Get server info
        response = requests.get(f"http://localhost:8000/servers/{container_id}/info")
        if response.status_code == 200:
            info = response.json()
            print(f"✅ Server info retrieved")
            print(f"   Status: {info.get('status', 'N/A')}")
            print(f"   Java Version: {info.get('java_version', 'N/A')}")
            print(f"   Java Binary: {info.get('java_bin', 'N/A')}")
        else:
            print(f"❌ Failed to get server info: {response.status_code}")
        
        # Get server logs
        response = requests.get(f"http://localhost:8000/servers/{container_id}/logs")
        if response.status_code == 200:
            logs = response.text
            print(f"✅ Server logs retrieved ({len(logs)} characters)")
            # Show last few lines
            last_lines = logs.split('\n')[-10:]
            print("   Last 10 log lines:")
            for line in last_lines:
                if line.strip():
                    print(f"   > {line}")
        else:
            print(f"❌ Failed to get server logs: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Exception getting server status: {e}")

def test_java_version_selection(container_id):
    """Test Java version selection"""
    print(f"\n=== Testing Java Version Selection for {container_id} ===")
    
    try:
        # Get available Java versions
        response = requests.get(f"http://localhost:8000/servers/{container_id}/java-versions")
        if response.status_code == 200:
            versions = response.json()
            print(f"✅ Available Java versions: {len(versions)} found")
            for version in versions:
                print(f"   - {version['version']}: {version['description']}")
        else:
            print(f"❌ Failed to get Java versions: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Exception testing Java version selection: {e}")

def cleanup_server(container_id):
    """Clean up test server"""
    print(f"\n=== Cleaning up server {container_id} ===")
    
    try:
        # Stop server
        response = requests.post(f"http://localhost:8000/servers/{container_id}/stop")
        if response.status_code == 200:
            print(f"✅ Server stopped")
        else:
            print(f"❌ Failed to stop server: {response.status_code}")
        
        # Delete server
        response = requests.delete(f"http://localhost:8000/servers/{container_id}")
        if response.status_code == 200:
            print(f"✅ Server deleted")
        else:
            print(f"❌ Failed to delete server: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Exception during cleanup: {e}")

def main():
    print("🚀 Testing NeoForge and Fabric Server Creation")
    
    # Test cases
    test_cases = [
        ("neoforge", "1.20.1", "test-neoforge"),
        ("fabric", "1.20.1", "test-fabric"),
    ]
    
    created_servers = []
    
    for server_type, version, name in test_cases:
        # Create server
        server_info = test_server_creation(server_type, version, name)
        if server_info:
            container_id = server_info.get('container_id')
            if container_id:
                created_servers.append(container_id)
                
                # Wait a bit for server to start
                print(f"   Waiting 10 seconds for server to start...")
                time.sleep(10)
                
                # Test server status
                test_server_status(container_id)
                
                # Test Java version selection
                test_java_version_selection(container_id)
    
    # Clean up
    print(f"\n=== Cleanup ===")
    for container_id in created_servers:
        cleanup_server(container_id)
    
    print(f"\n✅ Testing completed!")

if __name__ == "__main__":
    main()
