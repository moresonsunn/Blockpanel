"""
Server Templates System - Provides predefined server configurations for popular modpacks and server types.
"""

from typing import Dict, List, Optional
import json
from pathlib import Path

class ServerTemplate:
    def __init__(self, id: str, name: str, description: str, type: str, version: str, 
                 loader_version: Optional[str] = None, installer_version: Optional[str] = None,
                 min_ram: str = "2G", max_ram: str = "4G", category: str = "general",
                 icon: str = "🎮", tags: List[str] = None, popular: bool = False):
        self.id = id
        self.name = name
        self.description = description
        self.type = type
        self.version = version
        self.loader_version = loader_version
        self.installer_version = installer_version
        self.min_ram = min_ram
        self.max_ram = max_ram
        self.category = category
        self.icon = icon
        self.tags = tags or []
        self.popular = popular

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "version": self.version,
            "loader_version": self.loader_version,
            "installer_version": self.installer_version,
            "min_ram": self.min_ram,
            "max_ram": self.max_ram,
            "category": self.category,
            "icon": self.icon,
            "tags": self.tags,
            "popular": self.popular
        }

class ServerTemplateManager:
    def __init__(self):
        self.templates = {}
        self._load_default_templates()
        self._load_custom_templates()

    def _load_default_templates(self):
        """Load predefined server templates"""
        
        # Vanilla Templates
        self.add_template(ServerTemplate(
            id="vanilla_latest",
            name="Vanilla Latest",
            description="Latest vanilla Minecraft server - pure gameplay experience",
            type="vanilla",
            version="1.20.4",
            min_ram="1G",
            max_ram="2G",
            category="vanilla",
            icon="🟫",
            tags=["vanilla", "latest", "survival"],
            popular=True
        ))

        self.add_template(ServerTemplate(
            id="vanilla_stable",
            name="Vanilla Stable",
            description="Stable vanilla server for reliable gameplay",
            type="vanilla",
            version="1.20.1",
            min_ram="1G",
            max_ram="2G",
            category="vanilla",
            icon="🟫",
            tags=["vanilla", "stable", "survival"]
        ))

        # Paper Templates
        self.add_template(ServerTemplate(
            id="paper_performance",
            name="Paper Performance",
            description="High-performance Paper server with optimizations for large communities",
            type="paper",
            version="1.20.4",
            min_ram="4G",
            max_ram="8G",
            category="performance",
            icon="📄",
            tags=["paper", "performance", "plugins", "multiplayer"],
            popular=True
        ))

        self.add_template(ServerTemplate(
            id="paper_community",
            name="Paper Community",
            description="Paper server optimized for community gameplay with plugin support",
            type="paper",
            version="1.20.1",
            min_ram="2G",
            max_ram="4G",
            category="performance",
            icon="📄",
            tags=["paper", "community", "plugins"]
        ))

        # Fabric Templates
        self.add_template(ServerTemplate(
            id="fabric_modded",
            name="Fabric Modded",
            description="Latest Fabric server ready for performance and utility mods",
            type="fabric",
            version="1.20.4",
            loader_version="0.15.3",
            min_ram="3G",
            max_ram="6G",
            category="modded",
            icon="🧵",
            tags=["fabric", "mods", "performance"],
            popular=True
        ))

        self.add_template(ServerTemplate(
            id="fabric_technical",
            name="Fabric Technical",
            description="Fabric server for technical Minecraft with carpet and optimization mods",
            type="fabric",
            version="1.20.1",
            loader_version="0.14.24",
            min_ram="4G",
            max_ram="8G",
            category="modded",
            icon="🔧",
            tags=["fabric", "technical", "carpet", "redstone"]
        ))

        # Forge Templates
        self.add_template(ServerTemplate(
            id="forge_kitchen_sink",
            name="Forge All The Mods",
            description="Large Forge modpack server with hundreds of mods",
            type="forge",
            version="1.19.2",
            loader_version="43.3.0",
            min_ram="6G",
            max_ram="12G",
            category="modded",
            icon="🔨",
            tags=["forge", "kitchen-sink", "tech", "magic"],
            popular=True
        ))

        self.add_template(ServerTemplate(
            id="forge_create",
            name="Forge Create Focused",
            description="Forge server focused on Create mod and automation",
            type="forge",
            version="1.20.1",
            loader_version="47.2.20",
            min_ram="4G",
            max_ram="8G",
            category="modded",
            icon="⚙️",
            tags=["forge", "create", "automation", "tech"]
        ))

        # Specialized Templates
        self.add_template(ServerTemplate(
            id="creative_build",
            name="Creative Build Server",
            description="Optimized for creative building with WorldEdit support",
            type="paper",
            version="1.20.4",
            min_ram="2G",
            max_ram="4G",
            category="creative",
            icon="🏗️",
            tags=["creative", "building", "worldedit", "plugins"]
        ))

        self.add_template(ServerTemplate(
            id="pvp_competitive",
            name="PvP Competitive",
            description="Low-latency server optimized for competitive PvP gameplay",
            type="paper",
            version="1.20.1",
            min_ram="2G",
            max_ram="4G",
            category="pvp",
            icon="⚔️",
            tags=["pvp", "competitive", "combat", "plugins"]
        ))

        self.add_template(ServerTemplate(
            id="skyblock_classic",
            name="SkyBlock Adventure",
            description="Classic skyblock server with custom progression",
            type="paper",
            version="1.20.4",
            min_ram="3G",
            max_ram="6G",
            category="adventure",
            icon="🏝️",
            tags=["skyblock", "survival", "adventure", "plugins"]
        ))

        self.add_template(ServerTemplate(
            id="roleplay_medieval",
            name="Medieval Roleplay",
            description="Immersive medieval roleplay server with custom mechanics",
            type="paper",
            version="1.20.1",
            min_ram="4G",
            max_ram="8G",
            category="roleplay",
            icon="🏰",
            tags=["roleplay", "medieval", "immersive", "plugins"]
        ))

    def _load_custom_templates(self):
        """Load user-created custom templates"""
        try:
            custom_path = Path("templates/custom.json")
            if custom_path.exists():
                with open(custom_path, 'r') as f:
                    custom_data = json.load(f)
                    for template_data in custom_data.get("templates", []):
                        template = ServerTemplate(**template_data)
                        self.add_template(template)
        except Exception as e:
            print(f"Failed to load custom templates: {e}")

    def add_template(self, template: ServerTemplate):
        """Add a template to the manager"""
        self.templates[template.id] = template

    def get_template(self, template_id: str) -> Optional[ServerTemplate]:
        """Get a template by ID"""
        return self.templates.get(template_id)

    def list_templates(self, category: Optional[str] = None, popular_only: bool = False) -> List[Dict]:
        """List all templates, optionally filtered by category or popularity"""
        templates = list(self.templates.values())
        
        if category:
            templates = [t for t in templates if t.category == category]
        
        if popular_only:
            templates = [t for t in templates if t.popular]
        
        # Sort by popularity first, then alphabetically
        templates.sort(key=lambda t: (not t.popular, t.name))
        
        return [t.to_dict() for t in templates]

    def get_categories(self) -> List[Dict[str, str]]:
        """Get all available template categories"""
        categories = set(t.category for t in self.templates.values())
        
        category_info = {
            "vanilla": {"name": "Vanilla", "icon": "🟫", "description": "Pure Minecraft experience"},
            "performance": {"name": "Performance", "icon": "⚡", "description": "Optimized for high performance"},
            "modded": {"name": "Modded", "icon": "🔧", "description": "Enhanced with mods and loaders"},
            "creative": {"name": "Creative", "icon": "🎨", "description": "Building and creative focused"},
            "pvp": {"name": "PvP", "icon": "⚔️", "description": "Player vs Player combat"},
            "adventure": {"name": "Adventure", "icon": "🗺️", "description": "Custom gameplay experiences"},
            "roleplay": {"name": "Roleplay", "icon": "🎭", "description": "Immersive roleplay servers"},
            "general": {"name": "General", "icon": "🎮", "description": "General purpose templates"}
        }
        
        return [{"id": cat, **category_info.get(cat, {"name": cat.title(), "icon": "🎮", "description": ""})} 
                for cat in sorted(categories)]

    def create_custom_template(self, template_data: Dict) -> ServerTemplate:
        """Create a new custom template"""
        template = ServerTemplate(**template_data)
        self.add_template(template)
        self._save_custom_templates()
        return template

    def _save_custom_templates(self):
        """Save custom templates to file"""
        try:
            Path("templates").mkdir(exist_ok=True)
            custom_templates = [t.to_dict() for t in self.templates.values() 
                             if not t.id.startswith(('vanilla_', 'paper_', 'fabric_', 'forge_'))]
            
            with open("templates/custom.json", 'w') as f:
                json.dump({"templates": custom_templates}, f, indent=2)
        except Exception as e:
            print(f"Failed to save custom templates: {e}")

# Global template manager instance
_template_manager = None

def get_template_manager() -> ServerTemplateManager:
    global _template_manager
    if _template_manager is None:
        _template_manager = ServerTemplateManager()
    return _template_manager
