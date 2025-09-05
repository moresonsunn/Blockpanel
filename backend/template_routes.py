from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from database import get_db
from models import ServerTemplate, User
from auth import require_auth, require_moderator
from docker_manager import DockerManager

router = APIRouter(prefix="/templates", tags=["server_templates"])

# Pydantic models
class ServerTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    server_type: str
    minecraft_version: str
    loader_version: Optional[str] = None
    min_ram: str = "1024M"
    max_ram: str = "2048M"
    java_version: str = "21"
    config: Optional[Dict[str, Any]] = None

class ServerTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    server_type: Optional[str] = None
    minecraft_version: Optional[str] = None
    loader_version: Optional[str] = None
    min_ram: Optional[str] = None
    max_ram: Optional[str] = None
    java_version: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class ServerTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    server_type: str
    minecraft_version: str
    loader_version: Optional[str]
    min_ram: str
    max_ram: str
    java_version: str
    config: Optional[Dict[str, Any]]
    created_at: datetime
    
    class Config:
        from_attributes = True

class CreateServerFromTemplate(BaseModel):
    server_name: str
    host_port: Optional[int] = None
    override_config: Optional[Dict[str, Any]] = None

def get_docker_manager() -> DockerManager:
    """Get Docker manager instance."""
    return DockerManager()

@router.get("/", response_model=List[ServerTemplateResponse])
async def list_templates(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """List all available server templates."""
    templates = db.query(ServerTemplate).order_by(ServerTemplate.created_at.desc()).all()
    return templates

@router.post("/", response_model=ServerTemplateResponse)
async def create_template(
    template_data: ServerTemplateCreate,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Create a new server template."""
    # Validate server type
    from server_providers.providers import get_provider_names
    valid_types = get_provider_names()
    if template_data.server_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid server type. Must be one of: {valid_types}"
        )
    
    # Validate Java version
    valid_java_versions = ["8", "11", "17", "21"]
    if template_data.java_version not in valid_java_versions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Java version. Must be one of: {valid_java_versions}"
        )
    
    # Check if template name already exists
    existing_template = db.query(ServerTemplate).filter(
        ServerTemplate.name == template_data.name
    ).first()
    if existing_template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template name already exists"
        )
    
    # Create template
    template = ServerTemplate(
        name=template_data.name,
        description=template_data.description,
        server_type=template_data.server_type,
        minecraft_version=template_data.minecraft_version,
        loader_version=template_data.loader_version,
        min_ram=template_data.min_ram,
        max_ram=template_data.max_ram,
        java_version=template_data.java_version,
        config=template_data.config,
        created_by=current_user.id
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return template

@router.get("/{template_id}", response_model=ServerTemplateResponse)
async def get_template(
    template_id: int,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get a specific server template."""
    template = db.query(ServerTemplate).filter(ServerTemplate.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    return template

@router.put("/{template_id}", response_model=ServerTemplateResponse)
async def update_template(
    template_id: int,
    template_data: ServerTemplateUpdate,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Update a server template."""
    template = db.query(ServerTemplate).filter(ServerTemplate.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # Update fields
    if template_data.name is not None:
        # Check for name conflicts
        existing_template = db.query(ServerTemplate).filter(
            ServerTemplate.name == template_data.name,
            ServerTemplate.id != template_id
        ).first()
        if existing_template:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Template name already exists"
            )
        template.name = template_data.name
    
    if template_data.description is not None:
        template.description = template_data.description
    
    if template_data.server_type is not None:
        from server_providers.providers import get_provider_names
        valid_types = get_provider_names()
        if template_data.server_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid server type. Must be one of: {valid_types}"
            )
        template.server_type = template_data.server_type
    
    if template_data.minecraft_version is not None:
        template.minecraft_version = template_data.minecraft_version
    
    if template_data.loader_version is not None:
        template.loader_version = template_data.loader_version
    
    if template_data.min_ram is not None:
        template.min_ram = template_data.min_ram
    
    if template_data.max_ram is not None:
        template.max_ram = template_data.max_ram
    
    if template_data.java_version is not None:
        valid_java_versions = ["8", "11", "17", "21"]
        if template_data.java_version not in valid_java_versions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Java version. Must be one of: {valid_java_versions}"
            )
        template.java_version = template_data.java_version
    
    if template_data.config is not None:
        template.config = template_data.config
    
    db.commit()
    db.refresh(template)
    
    return template

@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Delete a server template."""
    template = db.query(ServerTemplate).filter(ServerTemplate.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    db.delete(template)
    db.commit()
    
    return {"message": "Template deleted successfully"}

@router.post("/{template_id}/create-server")
async def create_server_from_template(
    template_id: int,
    server_data: CreateServerFromTemplate,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Create a new server from a template."""
    template = db.query(ServerTemplate).filter(ServerTemplate.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    try:
        # Get Docker manager
        docker_manager = get_docker_manager()
        
        # Merge template config with override config
        final_config = template.config.copy() if template.config else {}
        if server_data.override_config:
            final_config.update(server_data.override_config)
        
        # Create server using template parameters
        result = docker_manager.create_server(
            name=server_data.server_name,
            server_type=template.server_type,
            version=template.minecraft_version,
            host_port=server_data.host_port,
            loader_version=template.loader_version,
            min_ram=template.min_ram,
            max_ram=template.max_ram
        )
        
        # If server creation was successful, apply Java version from template
        if result.get("id"):
            try:
                docker_manager.update_server_java_version(
                    result["id"], 
                    template.java_version
                )
            except Exception as e:
                # Log but don't fail if Java version update fails
                import logging
                logging.warning(f"Failed to set Java version from template: {e}")
        
        # Add template info to result
        result["created_from_template"] = {
            "template_id": template.id,
            "template_name": template.name,
            "java_version": template.java_version,
            "config_applied": final_config
        }
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create server from template: {str(e)}"
        )

@router.get("/popular/")
async def get_popular_templates(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get popular/recommended server templates."""
    # This could be expanded to track usage and popularity
    popular_templates = [
        {
            "name": "Vanilla Latest",
            "description": "Latest Minecraft vanilla server",
            "server_type": "vanilla",
            "minecraft_version": "1.21",
            "java_version": "21",
            "min_ram": "1024M",
            "max_ram": "2048M"
        },
        {
            "name": "Paper Performance",
            "description": "High-performance Paper server with optimizations",
            "server_type": "paper",
            "minecraft_version": "1.21",
            "java_version": "21",
            "min_ram": "2048M",
            "max_ram": "4096M"
        },
        {
            "name": "Fabric Modded",
            "description": "Fabric server ready for mods",
            "server_type": "fabric",
            "minecraft_version": "1.21",
            "java_version": "21",
            "min_ram": "2048M",
            "max_ram": "4096M"
        },
        {
            "name": "Legacy 1.12.2",
            "description": "Classic 1.12.2 server for older mods",
            "server_type": "forge",
            "minecraft_version": "1.12.2",
            "java_version": "8",
            "min_ram": "1024M",
            "max_ram": "3072M"
        }
    ]
    
    return {"popular_templates": popular_templates}

@router.post("/import")
async def import_template_from_server(
    server_name: str,
    template_name: str,
    description: Optional[str] = None,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Create a template from an existing server configuration."""
    try:
        # Get server information
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        target_server = None
        for server in servers:
            if server.get("name") == server_name:
                target_server = server
                break
        
        if not target_server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        # Get server info and configuration
        server_info = docker_manager.get_server_info(target_server["id"])
        
        # Extract template data from server
        template_data = {
            "name": template_name,
            "description": description or f"Template created from server {server_name}",
            "server_type": server_info.get("server_type", "vanilla"),
            "minecraft_version": server_info.get("server_version", "1.21"),
            "loader_version": server_info.get("loader_version"),
            "java_version": server_info.get("java_version", "21"),
            "min_ram": "1024M",  # Default values - could be extracted from container
            "max_ram": "2048M",
            "config": {
                "imported_from": server_name,
                "import_date": datetime.utcnow().isoformat()
            }
        }
        
        # Create template
        template = ServerTemplate(
            name=template_data["name"],
            description=template_data["description"],
            server_type=template_data["server_type"],
            minecraft_version=template_data["minecraft_version"],
            loader_version=template_data["loader_version"],
            min_ram=template_data["min_ram"],
            max_ram=template_data["max_ram"],
            java_version=template_data["java_version"],
            config=template_data["config"],
            created_by=current_user.id
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        
        return template
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import template from server: {str(e)}"
        )