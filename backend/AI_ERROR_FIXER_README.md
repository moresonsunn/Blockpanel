# 🤖 AI Error Fixer for Minecraft Server Manager

An intelligent, automated error detection and resolution system that monitors your Minecraft server manager and automatically fixes common issues.

## 🚀 Features

### 🔍 **Automatic Error Detection**
- **Real-time Monitoring**: Continuously monitors containers, logs, and system resources
- **Pattern Recognition**: Detects errors using advanced regex patterns
- **Severity Classification**: Categorizes errors by severity (critical, high, medium, low)
- **Smart Filtering**: Avoids duplicate error handling

### 🛠️ **Automatic Fixes**
- **JAR Corruption**: Re-downloads corrupted server JAR files
- **Java Version Mismatch**: Automatically selects and applies correct Java versions
- **Container Issues**: Restarts or recreates problematic containers
- **Memory Issues**: Increases memory limits when needed
- **Port Conflicts**: Finds and assigns available ports
- **File Permissions**: Fixes permission issues automatically
- **Network Issues**: Verifies and restores connectivity
- **Download Failures**: Retries failed downloads

### 🔧 **Manual Control**
- **CLI Interface**: Easy command-line access to all features
- **API Endpoints**: RESTful API for integration
- **Manual Fixes**: Trigger specific fixes on demand
- **Status Monitoring**: Real-time status and statistics

### 🐳 **Docker Integration**
- **Image Management**: Automatic rebuilding of runtime images
- **Container Management**: Full container lifecycle control
- **Docker Hub Upload**: Upload images to Docker Hub
- **System Cleanup**: Remove unused containers, images, and volumes

## 📋 Requirements

- Python 3.8+
- Docker
- Docker Compose
- Required Python packages (see requirements.txt)

## 🛠️ Installation

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository-url>
   cd minecraft-server
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the AI Error Fixer**:
   ```bash
   # Edit the configuration file
   nano backend/ai_config.json
   ```

## 🚀 Quick Start

### Using the CLI

1. **Start AI monitoring**:
   ```bash
   cd backend
   python ai_cli.py start
   ```

2. **Check status**:
   ```bash
   python ai_cli.py status
   ```

3. **Live monitoring**:
   ```bash
   python ai_cli.py monitor --interval 30
   ```

4. **Manual fix**:
   ```bash
   python ai_cli.py fix jar_corruption
   ```

5. **Rebuild runtime image**:
   ```bash
   python ai_cli.py rebuild
   ```

6. **Upload to Docker Hub**:
   ```bash
   python ai_cli.py upload --image-name your-username/minecraft-server-manager
   ```

### Using the API

1. **Start monitoring**:
   ```bash
   curl -X POST http://localhost:8000/ai/start
   ```

2. **Get status**:
   ```bash
   curl http://localhost:8000/ai/status
   ```

3. **Trigger manual fix**:
   ```bash
   curl -X POST http://localhost:8000/ai/fix \
     -H "Content-Type: application/json" \
     -d '{"error_type": "jar_corruption"}'
   ```

4. **Rebuild runtime image**:
   ```bash
   curl -X POST http://localhost:8000/ai/rebuild-runtime
   ```

## 📊 Error Types and Fixes

### 🔴 Critical Errors

#### JAR Corruption
- **Detection**: `Error: Invalid or corrupt jarfile`
- **Auto-fix**: Re-download server JAR file
- **Fallback**: Rebuild Docker image

#### Java Version Mismatch
- **Detection**: `UnsupportedClassVersionError`
- **Auto-fix**: Update Java version in container
- **Fallback**: Rebuild with correct Java version

### 🟡 High Priority Errors

#### Container Issues
- **Detection**: Container exited, failed to start
- **Auto-fix**: Restart container
- **Fallback**: Recreate container

#### Memory Issues
- **Detection**: `OutOfMemoryError`, high memory usage
- **Auto-fix**: Increase memory limits
- **Fallback**: Restart with higher limits

### 🟢 Medium Priority Errors

#### Network Connectivity
- **Detection**: Connection refused, timeouts
- **Auto-fix**: Verify network connectivity
- **Fallback**: Restart network services

#### Port Conflicts
- **Detection**: `Address already in use`
- **Auto-fix**: Find available port
- **Fallback**: Change port assignment

#### File Permissions
- **Detection**: `Permission denied`
- **Auto-fix**: Fix file permissions
- **Fallback**: Recreate with correct permissions

## ⚙️ Configuration

The AI Error Fixer is configured via `backend/ai_config.json`:

```json
{
  "ai_error_fixer": {
    "monitor_interval": 30,
    "log_tail_lines": 100,
    "max_retry_attempts": 3,
    "backup_before_fix": true,
    "auto_rebuild_images": true,
    "auto_restart_containers": true,
    "enable_docker_commands": true,
    "enable_file_operations": true,
    "enable_network_checks": true,
    "notification_webhook": null
  }
}
```

### Key Configuration Options

- **`monitor_interval`**: How often to check for errors (seconds)
- **`log_tail_lines`**: Number of log lines to monitor
- **`max_retry_attempts`**: Maximum retry attempts for fixes
- **`backup_before_fix`**: Create backup before applying fixes
- **`auto_rebuild_images`**: Automatically rebuild Docker images
- **`auto_restart_containers`**: Automatically restart containers
- **`enable_docker_commands`**: Allow Docker command execution
- **`enable_file_operations`**: Allow file system operations
- **`enable_network_checks`**: Allow network connectivity checks

## 🔧 CLI Commands

### Basic Commands
```bash
python ai_cli.py start          # Start AI monitoring
python ai_cli.py stop           # Stop AI monitoring
python ai_cli.py status         # Show current status
python ai_cli.py monitor        # Live monitoring mode
```

### Fix Commands
```bash
python ai_cli.py fix jar_corruption                    # Fix JAR corruption
python ai_cli.py fix java_version_mismatch             # Fix Java version issues
python ai_cli.py fix docker_container_issues           # Fix container issues
python ai_cli.py fix memory_issues                     # Fix memory problems
python ai_cli.py fix port_conflicts                    # Fix port conflicts
python ai_cli.py fix file_permissions                  # Fix permission issues
python ai_cli.py fix network_connectivity              # Fix network issues
python ai_cli.py fix download_failures                 # Fix download problems
```

### System Commands
```bash
python ai_cli.py rebuild         # Rebuild runtime image
python ai_cli.py restart         # Restart all containers
python ai_cli.py cleanup         # Clean up system
python ai_cli.py upload          # Upload to Docker Hub
```

## 🌐 API Endpoints

### AI Error Fixer Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ai/start` | Start AI error monitoring |
| POST | `/ai/stop` | Stop AI error monitoring |
| GET | `/ai/status` | Get AI error fixer status |
| POST | `/ai/fix` | Trigger manual fix |
| POST | `/ai/upload-docker` | Upload to Docker Hub |
| POST | `/ai/rebuild-runtime` | Rebuild runtime image |
| POST | `/ai/restart-containers` | Restart all containers |
| POST | `/ai/cleanup` | Clean up system |

### Example API Usage

```bash
# Start monitoring
curl -X POST http://localhost:8000/ai/start

# Get status
curl http://localhost:8000/ai/status

# Trigger manual fix
curl -X POST http://localhost:8000/ai/fix \
  -H "Content-Type: application/json" \
  -d '{"error_type": "jar_corruption", "container_id": "abc123"}'

# Rebuild runtime image
curl -X POST http://localhost:8000/ai/rebuild-runtime

# Upload to Docker Hub
curl -X POST http://localhost:8000/ai/upload-docker \
  -H "Content-Type: application/json" \
  -d '{"image_name": "your-username/minecraft-server-manager"}'
```

## 📈 Monitoring and Logs

### Status Information
The AI Error Fixer provides comprehensive status information:

```json
{
  "monitoring": true,
  "error_count": 5,
  "fix_count": 3,
  "recent_errors": [...],
  "recent_fixes": [...],
  "config": {...}
}
```

### Log Files
- **AI Error Fixer Logs**: `logs/ai_error_fixer.log`
- **Application Logs**: `logs/app.log`
- **Backup Logs**: `backups/`

### Live Monitoring
Use the CLI monitor mode for real-time updates:
```bash
python ai_cli.py monitor --interval 30
```

## 🔒 Security Considerations

### Docker Commands
- The AI Error Fixer can execute Docker commands
- Ensure proper Docker permissions
- Consider running in a restricted environment

### File Operations
- Can modify file permissions
- Can delete and recreate files
- Ensure proper file system permissions

### Network Access
- Can make network requests
- Can upload to Docker Hub
- Ensure proper network security

## 🚨 Troubleshooting

### Common Issues

1. **Docker Permission Denied**
   ```bash
   # Add user to docker group
   sudo usermod -aG docker $USER
   # Restart Docker service
   sudo systemctl restart docker
   ```

2. **Python Import Errors**
   ```bash
   # Install missing dependencies
   pip install -r requirements.txt
   ```

3. **Configuration Errors**
   ```bash
   # Validate configuration
   python -c "import json; json.load(open('ai_config.json'))"
   ```

4. **Monitoring Not Starting**
   ```bash
   # Check logs
   tail -f logs/ai_error_fixer.log
   # Check Docker status
   docker info
   ```

### Debug Mode
Enable debug logging by modifying the configuration:
```json
{
  "logging": {
    "level": "DEBUG"
  }
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue on GitHub
- Check the troubleshooting section
- Review the logs for error details

---

**🤖 AI Error Fixer** - Making Minecraft server management effortless and error-free!
