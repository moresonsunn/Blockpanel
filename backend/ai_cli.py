#!/usr/bin/env python3
"""
Command Line Interface for AI Error Fixer
Provides easy access to AI error detection and auto-fix capabilities.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from ai_error_fixer import AIErrorFixer, start_ai_monitoring, stop_ai_monitoring, get_ai_status, manual_fix, upload_to_docker

def print_status(status):
    """Print status information in a formatted way."""
    print("🤖 AI Error Fixer Status")
    print("=" * 40)
    print(f"Monitoring: {'🟢 Active' if status['monitoring'] else '🔴 Inactive'}")
    print(f"Errors Detected: {status['error_count']}")
    print(f"Fixes Applied: {status['fix_count']}")
    
    if status['recent_errors']:
        print("\n📋 Recent Errors:")
        for error in status['recent_errors']:
            print(f"  • {error.get('type', 'unknown')} - {error.get('severity', 'unknown')}")
    
    if status['recent_fixes']:
        print("\n🔧 Recent Fixes:")
        for fix in status['recent_fixes']:
            print(f"  • {fix.get('strategy', 'unknown')} - {fix.get('result', {}).get('message', 'unknown')}")

def main():
    parser = argparse.ArgumentParser(description="AI Error Fixer CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Start monitoring
    start_parser = subparsers.add_parser("start", help="Start AI error monitoring")
    start_parser.add_argument("--config", type=str, help="Path to config file")
    
    # Stop monitoring
    stop_parser = subparsers.add_parser("stop", help="Stop AI error monitoring")
    
    # Status
    status_parser = subparsers.add_parser("status", help="Show AI error fixer status")
    
    # Manual fix
    fix_parser = subparsers.add_parser("fix", help="Manually trigger a fix")
    fix_parser.add_argument("error_type", help="Type of error to fix")
    fix_parser.add_argument("--container-id", help="Container ID (optional)")
    
    # Upload to Docker
    upload_parser = subparsers.add_parser("upload", help="Upload to Docker Hub")
    upload_parser.add_argument("--image-name", default="minecraft-server-manager", help="Docker image name")
    
    # Rebuild runtime
    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild runtime image")
    
    # Restart containers
    restart_parser = subparsers.add_parser("restart", help="Restart all containers")
    
    # Cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up system")
    
    # Monitor mode
    monitor_parser = subparsers.add_parser("monitor", help="Start monitoring with live updates")
    monitor_parser.add_argument("--interval", type=int, default=30, help="Update interval in seconds")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == "start":
            print("🚀 Starting AI error monitoring...")
            start_ai_monitoring()
            print("✅ AI error monitoring started successfully")
            
        elif args.command == "stop":
            print("🛑 Stopping AI error monitoring...")
            stop_ai_monitoring()
            print("✅ AI error monitoring stopped")
            
        elif args.command == "status":
            status = get_ai_status()
            print_status(status)
            
        elif args.command == "fix":
            print(f"🔧 Triggering manual fix for: {args.error_type}")
            result = manual_fix(args.error_type, args.container_id)
            if result.get("success"):
                print(f"✅ Fix applied successfully: {result.get('message')}")
            else:
                print(f"❌ Fix failed: {result.get('error')}")
                
        elif args.command == "upload":
            print(f"📤 Uploading to Docker Hub as {args.image_name}...")
            result = upload_to_docker(args.image_name)
            if result.get("success"):
                print(f"✅ Upload successful: {result.get('message')}")
            else:
                print(f"❌ Upload failed: {result.get('error')}")
                
        elif args.command == "rebuild":
            print("🔨 Rebuilding runtime image...")
            import subprocess
            from pathlib import Path
            
            cmd = [
                "docker", "build", "-t", "mc-runtime:latest", 
                "-f", "docker/runtime.Dockerfile", "docker"
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                cwd=Path.cwd().parent
            )
            
            if result.returncode == 0:
                print("✅ Runtime image rebuilt successfully")
            else:
                print(f"❌ Build failed: {result.stderr}")
                
        elif args.command == "restart":
            print("🔄 Restarting all containers...")
            from docker_manager import DockerManager
            
            docker_manager = DockerManager()
            servers = docker_manager.list_servers()
            
            for server in servers:
                try:
                    container_id = server.get("id")
                    name = server.get("name")
                    if container_id:
                        print(f"  Restarting {name}...")
                        docker_manager.stop_server(container_id)
                        docker_manager.start_server(container_id)
                        print(f"  ✅ {name} restarted")
                except Exception as e:
                    print(f"  ❌ Failed to restart {name}: {e}")
            
            print("✅ Container restart completed")
            
        elif args.command == "cleanup":
            print("🧹 Cleaning up system...")
            import subprocess
            
            operations = [
                ("containers", ["docker", "container", "prune", "-f"]),
                ("images", ["docker", "image", "prune", "-f"]),
                ("volumes", ["docker", "volume", "prune", "-f"]),
            ]
            
            for name, cmd in operations:
                print(f"  Cleaning up {name}...")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"  ✅ {name} cleaned")
                else:
                    print(f"  ❌ Failed to clean {name}: {result.stderr}")
            
            # Clean up old log files
            from pathlib import Path
            log_dir = Path("logs")
            if log_dir.exists():
                print("  Cleaning up old log files...")
                removed_count = 0
                for log_file in log_dir.glob("*.log"):
                    if log_file.stat().st_size > 10 * 1024 * 1024:  # 10MB
                        log_file.unlink()
                        removed_count += 1
                print(f"  ✅ Removed {removed_count} large log files")
            
            print("✅ System cleanup completed")
            
        elif args.command == "monitor":
            print("📊 Starting live monitoring...")
            print("Press Ctrl+C to stop")
            
            start_ai_monitoring()
            
            try:
                while True:
                    status = get_ai_status()
                    print(f"\r🔄 Monitoring: {'🟢' if status['monitoring'] else '🔴'} | "
                          f"Errors: {status['error_count']} | "
                          f"Fixes: {status['fix_count']}", end="", flush=True)
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\n🛑 Stopping monitoring...")
                stop_ai_monitoring()
                print("✅ Monitoring stopped")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
