#!/usr/bin/env python3
"""
Test script for AI Error Fixer
Demonstrates the functionality of the AI error detection and auto-fix system.
"""

import time
import json
from ai_error_fixer import AIErrorFixer, start_ai_monitoring, stop_ai_monitoring, get_ai_status, manual_fix

def test_ai_error_fixer():
    """Test the AI error fixer functionality."""
    print("🤖 AI Error Fixer Test Suite")
    print("=" * 50)
    
    # Test 1: Check initial status
    print("\n1. Checking initial status...")
    status = get_ai_status()
    print(f"   Monitoring: {'🟢 Active' if status['monitoring'] else '🔴 Inactive'}")
    print(f"   Errors detected: {status['error_count']}")
    print(f"   Fixes applied: {status['fix_count']}")
    
    # Test 2: Start monitoring
    print("\n2. Starting AI monitoring...")
    start_ai_monitoring()
    time.sleep(2)  # Give it time to start
    
    status = get_ai_status()
    print(f"   Monitoring: {'🟢 Active' if status['monitoring'] else '🔴 Inactive'}")
    
    # Test 3: Test manual fix
    print("\n3. Testing manual fix...")
    result = manual_fix("jar_corruption")
    print(f"   Result: {result.get('success', False)}")
    print(f"   Message: {result.get('message', 'No message')}")
    
    # Test 4: Check status after fix
    print("\n4. Checking status after fix...")
    status = get_ai_status()
    print(f"   Errors detected: {status['error_count']}")
    print(f"   Fixes applied: {status['fix_count']}")
    
    # Test 5: Show recent fixes
    if status['recent_fixes']:
        print("\n5. Recent fixes:")
        for fix in status['recent_fixes']:
            print(f"   • {fix.get('strategy', 'unknown')} - {fix.get('result', {}).get('message', 'unknown')}")
    
    # Test 6: Stop monitoring
    print("\n6. Stopping AI monitoring...")
    stop_ai_monitoring()
    
    status = get_ai_status()
    print(f"   Monitoring: {'🟢 Active' if status['monitoring'] else '🔴 Inactive'}")
    
    print("\n✅ AI Error Fixer test completed!")

def test_error_patterns():
    """Test error pattern detection."""
    print("\n🔍 Testing Error Pattern Detection")
    print("=" * 40)
    
    # Create AI error fixer instance
    ai_fixer = AIErrorFixer()
    
    # Test patterns
    test_cases = [
        ("jar_corruption", "Error: Invalid or corrupt jarfile server.jar"),
        ("java_version_mismatch", "java.lang.UnsupportedClassVersionError: Unsupported major.minor version 52.0"),
        ("docker_container_issues", "Container abc123 failed to start"),
        ("memory_issues", "java.lang.OutOfMemoryError: Java heap space"),
        ("port_conflicts", "Address already in use"),
        ("file_permissions", "Permission denied"),
        ("download_failures", "Download failed: 404 Not Found"),
    ]
    
    for error_type, test_line in test_cases:
        detected = False
        for pattern in ai_fixer.error_patterns.get(error_type, {}).get("patterns", []):
            import re
            if re.search(pattern, test_line, re.IGNORECASE):
                detected = True
                break
        
        status = "✅ Detected" if detected else "❌ Not detected"
        print(f"   {error_type}: {status}")
        print(f"     Test: {test_line}")

def test_fix_strategies():
    """Test fix strategies."""
    print("\n🛠️ Testing Fix Strategies")
    print("=" * 30)
    
    # Create AI error fixer instance
    ai_fixer = AIErrorFixer()
    
    # Test strategies
    for error_type, strategies in ai_fixer.fix_strategies.items():
        print(f"   {error_type}:")
        for strategy in strategies:
            print(f"     • {strategy['name']} (priority: {strategy['priority']})")
        print()

if __name__ == "__main__":
    try:
        test_error_patterns()
        test_fix_strategies()
        test_ai_error_fixer()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
