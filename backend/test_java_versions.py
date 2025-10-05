#!/usr/bin/env python3
"""
Test script to verify all Java versions are available and working.
"""

import subprocess
import sys
from pathlib import Path

def test_java_version(java_bin, version_name):
    """Test if a Java version is available and working."""
    try:
        result = subprocess.run(
            [java_bin, "-version"], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        if result.returncode == 0:
            print(f"✅ {version_name} ({java_bin}): Available")
            # Extract version info from stderr (Java prints version to stderr)
            version_info = result.stderr.strip().split('\n')[0]
            print(f"   Version: {version_info}")
            return True
        else:
            print(f"❌ {version_name} ({java_bin}): Failed with return code {result.returncode}")
            return False
    except FileNotFoundError:
        print(f"❌ {version_name} ({java_bin}): Not found")
        return False
    except subprocess.TimeoutExpired:
        print(f"❌ {version_name} ({java_bin}): Timeout")
        return False
    except Exception as e:
        print(f"❌ {version_name} ({java_bin}): Error - {e}")
        return False

def test_java_versions():
    """Test all Java versions."""
    print("Testing Java versions...")
    print("=" * 50)
    
    java_versions = [
        ("/usr/local/bin/java8", "Java 8"),
        ("/usr/local/bin/java11", "Java 11"),
        ("/usr/local/bin/java17", "Java 17"),
        ("/usr/local/bin/java21", "Java 21"),
    ]
    
    available_versions = []
    for java_bin, version_name in java_versions:
        if test_java_version(java_bin, version_name):
            available_versions.append(version_name)
        print()
    
    print("=" * 50)
    print(f"Available Java versions: {len(available_versions)}/{len(java_versions)}")
    for version in available_versions:
        print(f"  - {version}")
    
    return len(available_versions) == len(java_versions)


if __name__ == "__main__":
    print("Java Version and AI Monitoring Test")
    print("=" * 50)
    
    # Test Java versions
    java_success = test_java_versions()
    
    
    print("\n" + "=" * 50)
    print("Test Results:")
    print(f"Java versions: {'✅ PASS' if java_success else '❌ FAIL'}")
    if java_success:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    print("\n❌ Some tests failed!")
    sys.exit(1)
