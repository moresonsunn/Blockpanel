from __future__ import annotations
from typing import Any, Dict, List, Optional, Protocol

class PackSummary(Dict[str, Any]):
    pass

class PackDetail(Dict[str, Any]):
    pass

class PackVersion(Dict[str, Any]):
    pass

class ModpackProvider(Protocol):
    id: str
    name: str

    def search(self, query: str, *, mc_version: Optional[str] = None, loader: Optional[str] = None, limit: int = 24, offset: int = 0) -> List[PackSummary]:
        ...

    def get_pack(self, pack_id: str) -> PackDetail:
        ...

    def get_versions(self, pack_id: str, *, limit: int = 50) -> List[PackVersion]:
        ...

