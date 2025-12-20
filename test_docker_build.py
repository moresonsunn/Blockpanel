#!/usr/bin/env python3
"""
Test script to verify Docker build and Java version installation
"""

import subprocess
import sys
import time

def run_command(command, description):
    """Run a command and return success status"""
    print(f"\n=== {description} ===")
    print(f"Running: {command}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ SUCCESS")
            if result.stdout.strip():
                print("Output:", result.stdout.strip())
            return True
        else:
            print("❌ FAILED")
            print("Error:", result.stderr.strip())
            return False
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return False

def test_java_versions():
    """Test that all Java versions are available in the container"""
    java_tests = [
        ("/usr/local/bin/java8 -version", "Java 8"),
        ("/usr/local/bin/java11 -version", "Java 11"),
        ("/usr/local/bin/java17 -version", "Java 17"),
        ("/usr/local/bin/java21 -version", "Java 21"),
    ]
    
    print("\n=== Testing Java Versions in Container ===")
    
    for cmd, description in java_tests:
        print(f"\n--- Testing {description} ---")
        result = subprocess.run(
            f"docker run --rm --entrypoint /bin/sh lynx:test -lc \"{cmd} 2>&1\"",
            shell=True, capture_output=True, text=True
        )
        
        if result.returncode == 0:
            print(f"✅ {description} works")
            output = result.stdout.strip() or result.stderr.strip()
            if output:
                print("Output:", output)
        else:
            print(f"❌ {description} failed")
            print("Error:", result.stderr.strip() or result.stdout.strip())

def test_java_paths():
    """Test that Java binaries exist at expected paths"""
    print("\n=== Testing Java Binary Paths ===")
    
    path_tests = [
        ("ls -la /usr/local/bin/java8", "Java 8 binary"),
        ("ls -la /usr/local/bin/java11", "Java 11 binary"),
        ("ls -la /usr/local/bin/java17", "Java 17 binary"),
        ("ls -la /usr/local/bin/java21", "Java 21 binary"),
        ("ls -la /opt/", "Java installations in /opt"),
    ]
    
    for command, description in path_tests:
        print(f"\n--- Testing {description} ---")
        result = subprocess.run(
            f"docker run --rm --entrypoint /bin/sh lynx:test -lc \"{command} 2>&1\"",
            shell=True, capture_output=True, text=True
        )
        
        if result.returncode == 0:
            print(f"✅ {description} exists")
            print("Output:", result.stdout.strip() or result.stderr.strip())
        else:
            print(f"❌ {description} missing")
            print("Error:", result.stderr.strip() or result.stdout.strip())

def main():
    print("🚀 Testing Docker Build and Java Versions")
    
    # Step 1: Build the Docker image
    if not run_command(
        "docker build -t lynx:test -f docker/controller-unified.Dockerfile .",
        "Building Unified Docker Image"
    ):
        print("❌ Docker build failed. Stopping tests.")
        return False
    
    # Step 2: Test Java binary paths
    test_java_paths()
    
    # Step 3: Test Java versions
    test_java_versions()
    
    # Step 4: Test basic container functionality
    if run_command(
    "docker run --rm --entrypoint /bin/sh lynx:test -lc \"pwd\"",
        "Testing Basic Container Functionality"
    ):
        print("\n✅ All tests completed successfully!")
        return True
    else:
        print("\n❌ Some tests failed.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
