#!/usr/bin/env python3
"""
Comprehensive system validation test for Minecraft Controller
Tests all major components and functionality
"""

import subprocess
import shutil
import sys
import time
import json
import os
from pathlib import Path
import importlib.util

def run_command(command, description, cwd=None):
    """Run a command and return success status"""
    print(f"\n=== {description} ===")
    print(f"Running: {command}")
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            cwd=cwd
        )
        if result.returncode == 0:
            print("✅ SUCCESS")
            if result.stdout.strip():
                print(f"Output: {result.stdout.strip()[:200]}...")
            return True
        else:
            print("❌ FAILED")
            print(f"Error: {result.stderr.strip()[:200]}...")
            return False
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return False

def test_python_imports():
    """Test that backend Python modules import successfully using normal module resolution.

    Previous approach loaded files via spec_from_file_location which broke intra-module imports
    (e.g., docker_manager -> config, auth -> database). We now prepend the backend directory to
    sys.path and import modules in a dependency-friendly order.
    """
    print("\n=== Testing Python Module Imports ===")

    backend_dir = Path("backend").resolve()
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    # Order matters: load foundational modules first.
    backend_modules = [
        "config",
        "database",
        "models",
        "docker_manager",
        "auth",
        "auth_routes",
        "scheduler",
        "user_routes",
        "monitoring_routes",
        "health_routes",
        "ai_error_fixer",
        "app",  # app last since it pulls in many of the above
    ]

    success_count = 0
    for module_name in backend_modules:
        try:
            importlib.import_module(module_name)
            print(f"✅ {module_name}")
            success_count += 1
        except Exception as e:
            print(f"❌ {module_name} - import error: {str(e)[:120]}")

    print(f"\nImport Results: {success_count}/{len(backend_modules)} modules imported successfully")
    return success_count == len(backend_modules)

def test_configuration_files():
    """Test configuration file validity"""
    print("\n=== Testing Configuration Files ===")
    
    files_to_test = [
        ("docker-compose.yml", "Docker Compose configuration"),
        ("backend/requirements.txt", "Python requirements"),
        ("frontend/package.json", "Node.js package configuration"),
        ("backend/ai_config.json", "AI configuration"),
        ("frontend/tailwind.config.js", "TailwindCSS configuration")
    ]
    
    success_count = 0
    for file_path, description in files_to_test:
        if Path(file_path).exists():
            print(f"✅ {description} exists")
            
            # Additional validation for specific file types
            if file_path.endswith('.json'):
                try:
                    with open(file_path, 'r') as f:
                        json.load(f)
                    print(f"✅ {description} is valid JSON")
                except json.JSONDecodeError as e:
                    print(f"❌ {description} has invalid JSON: {e}")
                    continue
            
            success_count += 1
        else:
            print(f"❌ {description} missing")
    
    print(f"\nConfiguration Results: {success_count}/{len(files_to_test)} files valid")
    return success_count == len(files_to_test)

def test_docker_configuration():
    """Test Docker configuration (supports both legacy docker-compose and v2 plugin 'docker compose')."""
    print("\n=== Testing Docker Configuration ===")

    compose_legacy = shutil.which("docker-compose") is not None
    if compose_legacy:
        tests = [
            ("docker --version", "Docker availability"),
            ("docker-compose --version", "Docker Compose availability"),
            ("docker-compose config", "Docker Compose configuration validity")
        ]
    else:
        # Use plugin syntax
        tests = [
            ("docker --version", "Docker availability"),
            ("docker compose version", "Docker Compose plugin availability"),
            ("docker compose config", "Docker Compose configuration validity")
        ]

    success_count = 0
    for command, description in tests:
        if run_command(command, description):
            success_count += 1

    return success_count == len(tests)

def test_backend_syntax():
    """Test Python syntax for all backend files"""
    print("\n=== Testing Backend Python Syntax ===")
    
    backend_files = [
        "app.py",
        "auth.py", 
        "auth_routes.py",
        "database.py",
        "models.py",
        "user_routes.py",
        "monitoring_routes.py",
        "health_routes.py"
    ]
    
    success_count = 0
    for file_name in backend_files:
        file_path = f"backend/{file_name}"
        if Path(file_path).exists():
            if run_command(f"python -m py_compile {file_name}", f"Syntax check: {file_name}", cwd="backend"):
                success_count += 1
        else:
            print(f"❌ {file_name} not found")
    
    return success_count == len(backend_files)

def test_frontend_configuration():
    """Test frontend configuration"""
    print("\n=== Testing Frontend Configuration ===")
    
    tests = [
        ("npm --version", "Node.js/npm availability"),
        ("npm install --dry-run", "Package dependencies check", "frontend")
    ]
    
    success_count = 0
    for test_data in tests:
        command = test_data[0]
        description = test_data[1]
        cwd = test_data[2] if len(test_data) > 2 else None
        
        if run_command(command, description, cwd=cwd):
            success_count += 1
    
    return success_count == len(tests)

def test_database_models():
    """Test database model definitions"""
    print("\n=== Testing Database Models ===")
    
    try:
        # Import database modules to check model definitions
        sys.path.append('backend')
        import models
        import database

        # Check if key models exist (ServerTemplate removed with curated templates)
        required_models = ['User', 'ScheduledTask', 'ServerPerformance']
        found_models = []

        for model_name in required_models:
            if hasattr(models, model_name):
                found_models.append(model_name)
                print(f"✅ Model {model_name} exists")
            else:
                print(f"❌ Model {model_name} missing")

        success = len(found_models) == len(required_models)
        print(f"\nModel Results: {len(found_models)}/{len(required_models)} models found")
        return success

    except Exception as e:
        print(f"❌ Error testing models: {e}")
        return False

def test_ai_configuration():
    """Test AI error fixer configuration"""
    print("\n=== Testing AI Configuration ===")
    
    try:
        config_path = Path("backend/ai_config.json")
        if not config_path.exists():
            print("❌ AI configuration file missing")
            return False
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        required_sections = ['ai_error_fixer', 'error_patterns', 'fix_strategies']
        found_sections = []
        
        for section in required_sections:
            if section in config.get('ai_error_fixer', {}):
                found_sections.append(section)
                print(f"✅ AI config section {section} exists")
            else:
                print(f"❌ AI config section {section} missing")
        
        success = len(found_sections) == len(required_sections)
        print(f"\nAI Config Results: {len(found_sections)}/{len(required_sections)} sections found")
        return success
        
    except Exception as e:
        print(f"❌ Error testing AI configuration: {e}")
        return False

def test_file_structure():
    """Test that all required files and directories exist"""
    print("\n=== Testing File Structure ===")
    
    required_structure = [
        "backend/",
        "frontend/", 
        "docker/",
        "backend/app.py",
        "backend/requirements.txt",
        "frontend/src/App.js",
        "frontend/package.json",
        "docker/controller.Dockerfile",
        "docker/runtime.Dockerfile",
        "docker/runtime-entrypoint.sh",
        "docker-compose.yml"
    ]
    
    success_count = 0
    for item in required_structure:
        path = Path(item)
        if path.exists():
            print(f"✅ {item}")
            success_count += 1
        else:
            print(f"❌ {item} missing")
    
    print(f"\nFile Structure Results: {success_count}/{len(required_structure)} items found")
    return success_count == len(required_structure)

def generate_test_report(results):
    """Generate a comprehensive test report"""
    print("\n" + "="*60)
    print("COMPREHENSIVE TEST REPORT")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    
    print(f"\nOverall Results: {passed_tests}/{total_tests} test suites passed")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    print("\nDetailed Results:")
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} {test_name}")
    
    if passed_tests == total_tests:
        print("\n🎉 ALL TESTS PASSED! System is ready for deployment.")
        return True
    else:
        print(f"\n⚠️  {total_tests - passed_tests} test suite(s) failed. Please review the issues above.")
        return False

def main():
    """Run all validation tests"""
    print("🚀 Starting Comprehensive System Validation")
    print("="*60)
    
    # Run all test suites
    test_results = {
        "File Structure": test_file_structure(),
        "Configuration Files": test_configuration_files(),
        "Python Module Imports": test_python_imports(),
        "Backend Syntax": test_backend_syntax(),
        "Database Models": test_database_models(),
        "AI Configuration": test_ai_configuration(),
        "Docker Configuration": test_docker_configuration(),
        "Frontend Configuration": test_frontend_configuration()
    }
    
    # Generate final report
    overall_success = generate_test_report(test_results)
    
    return 0 if overall_success else 1

if __name__ == "__main__":
    sys.exit(main())
