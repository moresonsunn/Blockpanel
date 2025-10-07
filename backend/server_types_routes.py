from fastapi import APIRouter, HTTPException
from server_providers.providers import get_provider_names, get_provider
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/server-types")
def list_server_types():
    """Return all available server provider types (e.g. vanilla, paper, fabric, purpur, forge, neoforge)."""
    try:
        names = sorted(get_provider_names())
        return {"types": names}
    except Exception as e:
        logger.error(f"Failed to list server types: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/server-types/{server_type}/versions")
def list_server_type_versions(server_type: str):
    """Return all known versions for a given server type."""
    try:
        provider = get_provider(server_type)
        versions = provider.list_versions()
        # Limit extremely long lists to something reasonable but include total count
        truncated = versions[:500]
        return {"type": server_type, "count": len(versions), "versions": truncated, "truncated": len(truncated) < len(versions)}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to list versions for {server_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
