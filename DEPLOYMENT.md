# Deployment Guide

## Quick Start (Development)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Minecraft-Controller
   ```

2. **Copy environment configuration**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start the application**
   ```bash
   docker compose up -d --build
   ```

4. **Access the application**
   - Web Interface: http://localhost:8000/ui
   - API Documentation: http://localhost:8000/docs
   - Default Login: admin / admin123

## Production Deployment

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB+ RAM recommended
- 20GB+ disk space
- SSL certificates (recommended)

### Step-by-Step Production Setup

1. **Server Preparation**
   ```bash
   # Update system
   sudo apt update && sudo apt upgrade -y
   
   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   
   # Install Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

2. **Application Setup**
   ```bash
   # Clone repository
   git clone <repository-url> /opt/minecraft-controller
   cd /opt/minecraft-controller
   
   # Setup environment
   cp .env.example .env
   nano .env  # Configure your settings
   ```

3. **Production Environment Configuration**
   ```bash
   # Generate secure secret key
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   
   # Set strong PostgreSQL password
   # Configure SSL settings
   # Set up backup destinations
   ```

4. **Deploy with Production Configuration**
   ```bash
   # Start production stack
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   
   # Verify deployment
   docker-compose ps
   curl -f http://localhost/health/quick
   ```

### SSL/TLS Setup

1. **Using Let's Encrypt (Recommended)**
   ```bash
   # Install Certbot
   sudo apt install certbot python3-certbot-nginx
   
   # Generate certificate
   sudo certbot --nginx -d yourdomain.com
   
   # Update nginx.conf to enable HTTPS
   ```

2. **Using Custom Certificates**
   ```bash
   # Place certificates in ssl/ directory
   mkdir ssl
   cp your-cert.pem ssl/cert.pem
   cp your-key.pem ssl/key.pem
   
   # Update nginx configuration
   # Restart nginx service
   ```

### Database Backup Strategy

1. **Automated PostgreSQL Backups**
   ```bash
   # Create backup script
   cat > /opt/minecraft-controller/backup-db.sh << 'EOF'
   #!/bin/bash
   BACKUP_DIR="/opt/backups/postgres"
   DATE=$(date +%Y%m%d_%H%M%S)
   
   mkdir -p $BACKUP_DIR
   docker exec mc-postgres pg_dump -U postgres minecraft_controller | gzip > $BACKUP_DIR/backup_$DATE.sql.gz
   
   # Keep only last 30 days
   find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +30 -delete
   EOF
   
   chmod +x /opt/minecraft-controller/backup-db.sh
   ```

2. **Setup Cron Job**
   ```bash
   # Add to crontab
   echo "0 2 * * * /opt/minecraft-controller/backup-db.sh" | crontab -
   ```

### Monitoring and Logs

1. **Application Logs**
   ```bash
   # View logs
   docker-compose logs -f controller
   docker-compose logs -f db
   docker-compose logs -f nginx
   
   # Log rotation (add to logrotate)
   sudo nano /etc/logrotate.d/minecraft-controller
   ```

2. **System Monitoring**
   ```bash
   # Monitor resources
   docker stats
   
   # Check health endpoints
   curl http://localhost/health/
   curl http://localhost/monitoring/system-health
   ```

### Security Checklist

- [ ] Change default admin password
- [ ] Generate secure JWT secret key
- [ ] Use strong PostgreSQL password
- [ ] Enable HTTPS with valid certificates
- [ ] Configure firewall (allow only 80, 443, SSH)
- [ ] Set up fail2ban for login protection
- [ ] Regular security updates
- [ ] Monitor security logs
- [ ] Backup encryption
- [ ] Network segmentation (if applicable)

### Performance Optimization

1. **Database Optimization**
   ```sql
   -- PostgreSQL performance settings
   ALTER SYSTEM SET shared_buffers = '256MB';
   ALTER SYSTEM SET effective_cache_size = '1GB';
   ALTER SYSTEM SET work_mem = '16MB';
   SELECT pg_reload_conf();
   ```

2. **Docker Resource Limits**
   ```yaml
   # Adjust in docker-compose.prod.yml
   deploy:
     resources:
       limits:
         cpus: '2.0'
         memory: 4G
   ```

### Troubleshooting

1. **Common Issues**
   ```bash
   # Database connection failed
   docker exec mc-postgres pg_isready -U postgres
   
   # Permission denied errors
   sudo chown -R 1000:1000 data/
   
   # Port conflicts
   sudo netstat -tulpn | grep :8000
   
   # Memory issues
   free -h
   docker system prune -f
   ```

2. **Debug Mode**
   ```bash
   # Enable debug logging
   echo "LOG_LEVEL=DEBUG" >> .env
   docker-compose restart controller
   ```

### Updates and Maintenance

1. **Application Updates**
   ```bash
   # Backup before update
   ./backup-db.sh
   
   # Pull latest changes
   git pull origin main
   
   # Rebuild and restart
   docker-compose down
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

2. **Database Migrations**
   ```bash
   # Auto-handled by application startup
   # Manual migration if needed:
   docker exec mc-controller python -c "from database import init_db; init_db()"
   ```

### Scaling Considerations

1. **Horizontal Scaling**
   - Use external PostgreSQL cluster
   - Implement Redis for session storage
   - Load balancer with multiple controller instances
   - Shared file storage for server data

2. **Vertical Scaling**
   - Increase container resource limits
   - Optimize PostgreSQL settings
   - Use SSD storage for better I/O
   - Monitor and adjust based on usage

## Support

- **Documentation**: Check WARP.md for development details
- **Health Checks**: Monitor `/health/` endpoints
- **Logs**: Use `docker-compose logs` for troubleshooting
- **Metrics**: Access `/monitoring/` endpoints for system stats
