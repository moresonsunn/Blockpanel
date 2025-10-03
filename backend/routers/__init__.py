"""Centralized router exports for FastAPI app inclusion.

This module re-exports the routers defined in sibling modules so app.py can
import them from a single location, keeping imports tidy and task-oriented.
"""

from ..auth_routes import router as auth_router  # Authentication & users (tokens/session)
from ..scheduler_routes import router as scheduler_router  # Scheduler & jobs
from ..player_routes import router as player_router  # Player management
from ..world_routes import router as world_router  # World uploads/backups
from ..plugin_routes import router as plugin_router  # Plugin uploads
from ..api.user_routes import router as user_router  # Admin user management
from ..monitoring_routes import router as monitoring_router  # Metrics & monitoring
from ..health_routes import router as health_router  # Health checks
from .modpack_routes import router as modpack_router  # Modpack providers/import
from .catalog_routes import router as catalog_router  # Catalog listings
from ..integrations_routes import router as integrations_router  # External integrations

__all__ = [
    "auth_router",
    "scheduler_router",
    "player_router",
    "world_router",
    "plugin_router",
    "user_router",
    "monitoring_router",
    "health_router",
    "modpack_router",
    "catalog_router",
    "integrations_router",
]
