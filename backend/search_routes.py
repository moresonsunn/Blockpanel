from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException
from typing import Any, Dict, List, Optional, Tuple
import logging

from auth import require_auth
from database import get_db
from runtime_adapter import get_runtime_manager_or_docker
from file_manager import list_dir as fm_list_dir
from models import PlayerAction, User
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


def _normalize_terms(raw: str) -> List[str]:
    return [t for t in raw.lower().split() if t]


def _match_and_score(terms: List[str], values: List[Any]) -> int:
    if not terms:
        return 1
    normalized: List[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip().lower()
        if not text:
            continue
        normalized.append(text)
    if not normalized:
        return -1
    total = 0
    for term in terms:
        term_score = 0
        for text in normalized:
            if term in text:
                if text == term:
                    term_score = max(term_score, 6)
                elif text.startswith(term):
                    term_score = max(term_score, 5)
                elif term in text.split():
                    term_score = max(term_score, 4)
                else:
                    term_score = max(term_score, 3)
        if term_score == 0:
            return -1
        total += term_score
    return total


def _primary_port(server: Dict[str, Any]) -> Optional[int]:
    try:
        mappings = server.get("port_mappings") or {}
        primary = mappings.get("25565/tcp")
        if isinstance(primary, dict):
            host = primary.get("host_port")
            if host:
                return int(host)
    except Exception:
        pass
    try:
        raw_ports = server.get("ports") or {}
        mapping = raw_ports.get("25565/tcp")
        if isinstance(mapping, list) and mapping:
            host_port = mapping[0].get("HostPort")
            if host_port:
                return int(host_port)
    except Exception:
        pass
    return None


def _runtime_mode(server: Dict[str, Any]) -> str:
    image = str(server.get("image") or "").lower()
    if image == "local":
        return "local"
    if "local" in image and "runtime" in image:
        return "local"
    return "docker"


def _modpack_label(labels: Dict[str, Any]) -> Tuple[str, str]:
    provider = str(labels.get("mc.modpack.provider") or "").strip()
    pack_id = str(labels.get("mc.modpack.id") or "").strip()
    version_id = str(labels.get("mc.modpack.version_id") or "").strip()
    if provider and pack_id:
        label = f"{provider}:{pack_id}"
        if version_id:
            label = f"{label}@{version_id}"
        return label, provider
    return "", ""


def _gather_server_results(
    servers: List[Dict[str, Any]],
    terms: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    results: List[Dict[str, Any]] = []
    by_name: Dict[str, Dict[str, Any]] = {}
    for server in servers:
        name = str(server.get("name") or "").strip()
        server_id = str(server.get("id") or "").strip()
        if not name:
            continue
        host_port = _primary_port(server)
        labels = server.get("labels") or {}
        modpack_label, modpack_provider = _modpack_label(labels)
        runtime = _runtime_mode(server)
        score = _match_and_score(
            terms,
            [
                name,
                server_id,
                host_port,
                runtime,
                labels.get("mc.modpack.provider"),
                labels.get("mc.modpack.id"),
                modpack_label,
            ],
        )
        if score < 0:
            continue
        if terms and any(term == name.lower() for term in terms):
            score += 8
        elif terms and any(term in name.lower() for term in terms):
            score += 4
        result = {
            "id": f"server:{server_id or name}",
            "type": "server",
            "name": name,
            "description": f"{runtime} runtime" + (f" · port {host_port}" if host_port else ""),
            "server_id": server_id or name,
            "server_name": name,
            "host_port": host_port,
            "runtime": runtime,
            "modpack": modpack_label or None,
            "modpack_provider": modpack_provider or None,
            "score": score,
        }
        results.append(result)
        if name not in by_name:
            by_name[name] = {
                "id": server_id or name,
                "host_port": host_port,
                "runtime": runtime,
                "labels": labels,
            }
    return results, by_name


def _gather_player_results(
    db: Session,
    terms: List[str],
    server_index: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not terms:
        return []
    stmt = (
        db.query(PlayerAction.server_name, PlayerAction.player_name)
        .distinct()
        .limit(500)
    )
    rows = stmt.all()
    results: List[Dict[str, Any]] = []
    for server_name, player_name in rows:
        if not player_name or not server_name:
            continue
        score = _match_and_score(terms, [player_name, server_name])
        if score < 0:
            continue
        server_meta = server_index.get(server_name) or {}
        result = {
            "id": f"player:{server_name}:{player_name}",
            "type": "player",
            "name": player_name,
            "description": f"Player on {server_name}",
            "server_name": server_name,
            "server_id": server_meta.get("id") or server_name,
            "score": score + 2,
        }
        results.append(result)
    return results


def _candidate_config_paths(server_name: str) -> List[Tuple[str, str]]:
    candidates: List[Tuple[str, str]] = []
    try:
        entries = fm_list_dir(server_name, ".")
    except HTTPException:
        entries = []
    except Exception as exc:
        log.debug("Failed to list root for %s: %s", server_name, exc)
        entries = []
    for item in entries:
        name = item.get("name")
        if not name or item.get("is_dir"):
            continue
        candidates.append((name, name))
    for subdir in ("config", "configs"):
        try:
            entries = fm_list_dir(server_name, subdir)
        except HTTPException:
            continue
        except Exception as exc:
            log.debug("Failed to list %s/%s: %s", server_name, subdir, exc)
            continue
        for item in entries:
            name = item.get("name")
            if not name or item.get("is_dir"):
                continue
            rel_path = f"{subdir}/{name}"
            candidates.append((rel_path, name))
    return candidates


def _gather_config_results(
    servers: List[Dict[str, Any]],
    terms: List[str],
    server_index: Dict[str, Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    if not terms:
        return []
    results: List[Dict[str, Any]] = []
    for server in servers:
        if len(results) >= limit:
            break
        server_name = str(server.get("name") or "").strip()
        if not server_name:
            continue
        candidates = _candidate_config_paths(server_name)
        if not candidates:
            continue
        for rel_path, display_name in candidates:
            score = _match_and_score(terms, [display_name, rel_path, server_name])
            if score < 0:
                continue
            server_meta = server_index.get(server_name) or {}
            result = {
                "id": f"config:{server_name}:{rel_path}",
                "type": "config",
                "name": display_name,
                "path": rel_path,
                "description": f"{server_name} · {rel_path}",
                "server_name": server_name,
                "server_id": server_meta.get("id") or server_name,
                "score": score + 1,
            }
            results.append(result)
            if len(results) >= limit:
                break
    return results


@router.get("")
async def global_search(
    q: str = Query("", max_length=80, description="Query string"),
    limit: int = Query(15, ge=1, le=50),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    query = q or ""
    terms = _normalize_terms(query)

    try:
        runtime_manager = get_runtime_manager_or_docker()
        servers_raw = runtime_manager.list_servers()
    except Exception as exc:
        log.warning("Failed to list servers for search: %s", exc)
        servers_raw = []

    servers_results, server_index = _gather_server_results(servers_raw, terms)

    player_results = _gather_player_results(db, terms, server_index)
    config_results = _gather_config_results(servers_raw, terms, server_index, limit * 2)

    all_results = servers_results + player_results + config_results
    total_count = len(all_results)

    all_results.sort(key=lambda item: (-item.get("score", 0), item.get("type"), item.get("name", "")))
    trimmed = all_results[:limit]

    return {
        "query": query,
        "results": trimmed,
        "total": total_count,
    }
