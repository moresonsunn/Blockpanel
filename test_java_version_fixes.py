#!/usr/bin/env python3
"""
Test script to verify Java version selection fixes
"""

import subprocess
import sys
import time
import requests
import json
from pathlib import Path

def test_java_version_selection_logic():
    """Test the Java version selection logic for different server types and versions"""
    print("=== Testing Java Version Selection Logic ===")
    
    test_cases = [
        ("fabric", "1.21.8", "21"),  # Should use Java 21
        ("fabric", "1.20.1", "21"),  # Should use Java 21
        ("fabric", "1.19.4", "21"),  # Should use Java 21
        ("fabric", "1.18.2", "8"),   # Should use Java 8
        ("fabric", "1.16.5", "8"),   # Should use Java 8
        ("neoforge", "1.20.1", "17"), # Should use Java 17
        ("neoforge", "1.16.5", "8"),  # Should use Java 8
        ("paper", "1.21.1", "21"),    # Should use Java 21
        ("paper", "1.17.1", "17"),    # Should use Java 17
        ("paper", "1.16.5", "8"),     # Should use Java 8
    ]
    
    for server_type, version, expected_java in test_cases:
        print(f"Testing {server_type} {version} -> Expected Java {expected_java}")
        
        # Create a test server
        server_data = {
            "name": f"test-{server_type}-{version.replace('.', '-')}",
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
                container_id = server_info.get('container_id')
                
                if container_id:
                    # Wait a bit for server to start
                    time.sleep(5)
                    
                    # Get server info to check Java version
                    info_response = requests.get(f"http://localhost:8000/servers/{container_id}/info")
                    if info_response.status_code == 200:
                        info = info_response.json()
                        actual_java = info.get('java_version', 'unknown')
                        
                        if actual_java == expected_java:
                            print(f"  ✅ Correct: Java {actual_java}")
                        else:
                            print(f"  ❌ Wrong: Expected Java {expected_java}, got Java {actual_java}")
                    
                    # Clean up
                    requests.post(f"http://localhost:8000/servers/{container_id}/stop")
                    requests.delete(f"http://localhost:8000/servers/{container_id}")
                else:
                    print(f"  ❌ No container ID returned")
            else:
                print(f"  ❌ Failed to create server: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Exception: {e}")

def test_java_version_api():
    """Test the Java version API endpoints"""
    print("\n=== Testing Java Version API ===")
    
    # Create a test server
    server_data = {
        "name": "test-java-api",
        "server_type": "paper",
        "version": "1.20.1",
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
            container_id = server_info.get('container_id')
            
            if container_id:
                # Wait for server to start
                time.sleep(5)
                
                # Test getting available Java versions
                print("Testing GET /servers/{id}/java-versions")
                versions_response = requests.get(f"http://localhost:8000/servers/{container_id}/java-versions")
                if versions_response.status_code == 200:
                    versions_data = versions_response.json()
                    print(f"  ✅ Available versions: {len(versions_data.get('available_versions', []))}")
                    print(f"  ✅ Current version: {versions_data.get('current_version')}")
                else:
                    print(f"  ❌ Failed to get versions: {versions_response.status_code}")
                
                # Test setting Java version
                print("Testing POST /servers/{id}/java-version")
                set_response = requests.post(
                    f"http://localhost:8000/servers/{container_id}/java-version",
                    json={"java_version": "8"},
                    headers={"Content-Type": "application/json"}
                )
                if set_response.status_code == 200:
                    set_data = set_response.json()
                    print(f"  ✅ Java version set to: {set_data.get('java_version')}")
                else:
                    print(f"  ❌ Failed to set Java version: {set_response.status_code}")
                    print(f"  Response: {set_response.text}")
                
                # Clean up
                requests.post(f"http://localhost:8000/servers/{container_id}/stop")
                requests.delete(f"http://localhost:8000/servers/{container_id}")
            else:
                print("  ❌ No container ID returned")
        else:
            print(f"  ❌ Failed to create server: {response.status_code}")
            
    except Exception as e:
        print(f"  ❌ Exception: {e}")

def test_docker_build():
    """Test that the Docker build works with the shell script fixes"""
    print("\n=== Testing Docker Build ===")
    
    try:
        result = subprocess.run(
            "docker build -t mc-runtime:test -f docker/runtime.Dockerfile .",
            shell=True, capture_output=True, text=True
        )
        
        if result.returncode == 0:
            print("  ✅ Docker build successful")
        else:
            print("  ❌ Docker build failed")
            print(f"  Error: {result.stderr}")
            
    except Exception as e:
        print(f"  ❌ Exception during Docker build: {e}")

def main():
    print("🚀 Testing Java Version Selection Fixes")
    
    # Test 1: Docker build
    test_docker_build()
    
    # Test 2: Java version selection logic (if API is available)
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            test_java_version_selection_logic()
            test_java_version_api()
        else:
            print("\n⚠️  API not available, skipping API tests")
    except:
        print("\n⚠️  API not available, skipping API tests")
    
    print("\n✅ Testing completed!")

if __name__ == "__main__":
    main()
