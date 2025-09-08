from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

# Persist in the servers data volume so it survives image rebuilds
STORE_PATH = Path("/data/servers/integrations.json")


def read_store() -> dict:
    if STORE_PATH.exists():
        try:
            return json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_store(data: dict) -> None:
    try:
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_integration_key(name: str) -> Optional[str]:
    data = read_store()
    v = data.get(name) or {}
    key = v.get("api_key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def set_integration_key(name: str, api_key: str) -> None:
    data = read_store()
    data[name] = data.get(name) or {}
    data[name]["api_key"] = api_key
    write_store(data)

