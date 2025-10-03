"""
Routers aggregator for FastAPI app.

This package re-exports the routers from the top-level route modules.
We use absolute imports relative to the backend source root (not package
relative) so it works when running the app directly from the backend folder
or inside a container where the working directory is the app root.
"""

# Import routers from top-level modules (files live alongside app.py)
from auth_routes import router as auth_router  # Authentication & tokens
from scheduler_routes import router as scheduler_router  # Scheduler & jobs
from player_routes import router as player_router  # Player management
from world_routes import router as world_router  # World uploads/backups
from plugin_routes import router as plugin_router  # Plugin uploads
from monitoring_routes import router as monitoring_router  # Metrics & monitoring
from health_routes import router as health_router  # Health checks
from modpack_routes import router as modpack_router  # Modpack providers/import
from catalog_routes import router as catalog_router  # Catalog listings
from integrations_routes import router as integrations_router  # External integrations

# Use the new user management router under api/
from api.user_routes import router as user_router  # Admin user/roles/permissions

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
