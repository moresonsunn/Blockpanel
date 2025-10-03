# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Development Commands

### Local Development
```bash
# Backend development
cd backend && pip install -r requirements.txt && uvicorn app:app --reload

# Frontend development  
cd frontend && npm install && npm start

# Full stack with Docker
docker compose up -d --build
```

### Docker Operations
```bash
# Build runtime image (for Minecraft servers)
docker build -t mc-runtime:latest -f docker/runtime.Dockerfile docker

# Rebuild and restart all services
docker compose down && docker compose up -d --build

# View controller logs
docker logs mc-controller -f
```

### Testing
```bash
# Test Docker build and Java versions
python test_docker_build.py

# Test Java version selection fixes
python test_java_version_fixes.py

# Test AI error fixer functionality
python backend/test_ai_fixer.py

# Test server creation for all types
python test_server_types.py
```

### AI Error Fixer Management
```bash
# Check AI fixer status
python backend/ai_cli.py status

# Start/stop monitoring
python backend/ai_cli.py start
python backend/ai_cli.py stop

# Manual fix attempt
python backend/ai_cli.py fix

# Test specific error types
python backend/ai_cli.py test jar_corruption
```

### System Validation
```bash
# Run comprehensive system tests
python test_complete_system.py

# Test individual components
python -m py_compile backend/app.py
docker-compose config
npm install --dry-run
```

### Database Operations
```bash
# Database is automatically initialized on startup
# SQLite database file: backend/minecraft_controller.db

# Reset database (delete file and restart)
rm backend/minecraft_controller.db
docker compose restart controller
```

## Architecture Overview

### High-Level Structure
This is a **multi-container Minecraft server management platform** built with:
- **Controller Container**: FastAPI backend + React frontend (single container)
- **Runtime Containers**: Individual Java environments for each Minecraft server
- **Docker-in-Docker**: Controller manages runtime containers via Docker API

### Core Components

#### Backend Architecture (`backend/`)
- **FastAPI Application** (`app.py`): Main API server with modular router system
- **Docker Manager** (`docker_manager.py`): Orchestrates Minecraft server containers
- **Authentication System**: JWT-based with role hierarchy (admin > moderator > user)
- **Database Layer**: SQLAlchemy + SQLite for persistent data
- **AI Error Fixer** (`ai_error_fixer.py`): Automated error detection and resolution
- **Scheduler System**: APScheduler for automated tasks (backups, restarts, cleanup)

#### Router Organization
```
/auth/*        - Authentication (login, user management)
/players/*     - Player management (whitelist, ban, kick, OP)
/schedule/*    - Task scheduling (automated backups, restarts)
/servers/*     - Core server management endpoints
/worlds/*      - World management (upload, download, backup)
/plugins/*     - Plugin management (upload, delete, reload)
/users/*       - Enhanced user management and statistics
/monitoring/*  - Server monitoring and metrics
/health/*      - System health and status checks
```

#### Frontend Architecture (`frontend/src/`)
- **Single-Page React App** built with Create React App
- **JWT Authentication**: Token stored in localStorage, attached to all requests
- **Real-time Updates**: Polling-based for server stats and logs
- **TailwindCSS**: Utility-first styling with dark theme
- **Component Structure**: Single `App.js` with inline components

### Data Flow Patterns

#### Server Creation Flow
1. **Frontend**: User selects server type, version, and configuration
2. **Provider System**: Determines download URLs and installation steps
3. **Docker Manager**: Creates volume and runtime container
4. **Java Version Selection**: Automatic based on server type/version
5. **Download Manager**: Fetches server JAR and dependencies
6. **Container Launch**: Starts with proper Java version and memory settings

#### Multi-Java Version Support
- **Runtime Image**: Contains Java 8, 11, 17, and 21 (Eclipse Temurin)
- **Auto-Selection Logic**: Based on server type and Minecraft version
  - Vanilla/Paper/Purpur: 1.8-1.16→Java 8, 1.17-1.18→Java 17, 1.19+→Java 21
  - Fabric: 1.19+→Java 21, older→Java 8
  - Forge/NeoForge: 1.12-→Java 8, 1.13+→Java 17
- **Manual Override**: Users can select Java version via Config panel
- **Entrypoint Script**: Dynamic Java binary selection at runtime

#### AI Error Detection System
- **Log Monitoring**: Continuous scanning of server logs for error patterns
- **Error Classification**: 7 categories (jar corruption, Java version mismatches, etc.)
- **Auto-Resolution**: Predefined fix strategies with priority ordering
- **Manual Triggers**: CLI and API endpoints for manual intervention

### Database Schema
**Key Models**:
- `User`: Authentication and role management
- `ScheduledTask`: Cron-based automation (backups, restarts)
- `ServerTemplate`: Predefined configurations for quick server creation
- `PlayerAction`: Audit trail for player management actions
- `BackupTask`: Backup metadata and retention tracking
- `ServerPerformance`: Historical performance metrics and monitoring data

### Configuration Management
**Environment Variables**:
- `SERVERS_CONTAINER_ROOT`: Server data directory inside controller
- `SERVERS_VOLUME_NAME`: Docker volume name for server data
- `DOCKER_HOST`: Docker daemon connection (default: tcp://host.docker.internal:2375)

**Config Files**:
- `backend/ai_config.json`: AI error fixer configuration
- `docker-compose.yml`: Service orchestration
- `backend/requirements.txt`: Python dependencies with pinned bcrypt version

### Security Architecture
- **JWT Authentication**: Bearer token authentication with expiration
- **Role-Based Access**: Three-tier role system (admin/moderator/user)
- **Password Security**: bcrypt hashing with salt
- **Container Isolation**: Each Minecraft server runs in isolated container
- **Docker Socket Access**: Controller has Docker API access for container management

### Development Patterns

#### Error Handling Strategy
- **Graceful Degradation**: Services continue operating when non-critical components fail
- **Comprehensive Logging**: Structured logging throughout the application
- **AI-Powered Recovery**: Automatic detection and resolution of common server issues
- **Validation Layers**: JAR file validation, input sanitization, container health checks

#### Testing Approach
- **Integration Tests**: Full Docker build and Java version validation
- **API Testing**: Server creation flows and Java version selection
- **Error Simulation**: Artificial error injection for AI fixer testing
- **Manual Test Scripts**: Python scripts for common development scenarios

### Deployment Considerations
- **Production Setup**: Requires Docker daemon with TCP endpoint enabled
- **Data Persistence**: Server data persists in Docker volumes
- **Port Management**: Dynamic port allocation for Minecraft servers
- **Resource Management**: Configurable RAM limits per server
- **Backup Strategy**: Automated backup scheduling with retention policies

### Extension Points
- **Server Providers**: Plugin system for adding new server types
- **Authentication Backends**: Configurable auth providers
- **Task Schedulers**: Extensible task types beyond built-in ones
- **AI Fix Strategies**: New error patterns and resolution strategies
- **Frontend Themes**: TailwindCSS-based theming system

### Recently Added Features
- **Enhanced User Management**: User statistics, activity tracking, bulk operations, role management
- **System Monitoring**: Real-time server metrics, performance monitoring, system health checks
- **Health Endpoints**: Comprehensive health monitoring for database, Docker, and application status
- **PostgreSQL Support**: Full PostgreSQL database integration alongside SQLite
- **World Management**: Upload, download, and backup world files
- **Plugin Management**: Upload, delete, and reload server plugins
- **Advanced Analytics**: Historical performance data collection and analysis
- **Production Ready**: Nginx reverse proxy, SSL support, CI/CD pipeline, comprehensive deployment guide
- **Security Features**: Rate limiting, security headers, environment configuration, backup automation

### Production Deployment
- **Environment Configuration**: `.env.example` with all necessary settings
- **Production Docker Compose**: `docker-compose.prod.yml` with resource limits and security
- **Nginx Configuration**: `nginx.conf` with SSL, rate limiting, and security headers
- **CI/CD Pipeline**: `.github/workflows/ci.yml` with automated testing and deployment
- **Deployment Guide**: `DEPLOYMENT.md` with step-by-step production setup instructions
