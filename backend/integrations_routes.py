from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
from auth import require_admin
from models import User
from integrations_store import get_integration_key, set_integration_key

router = APIRouter(prefix="/integrations", tags=["integrations"])

@router.get("/status")
async def integrations_status():
    return {
        "curseforge": {
            "configured": bool(get_integration_key("curseforge"))
        }
    }

class CurseForgeKey(BaseModel):
    api_key: str

@router.post("/curseforge-key")
async def set_curseforge_key(payload: CurseForgeKey, current_user: User = Depends(require_admin)):
    if not payload.api_key or len(payload.api_key.strip()) < 10:
        raise HTTPException(status_code=400, detail="Invalid API key")
    set_integration_key("curseforge", payload.api_key.strip())
    return {"ok": True}

