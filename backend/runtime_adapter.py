import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
import re
import json
import time
import psutil

from local_runtime import LocalRuntimeManager, MINECRAFT_PORT
from config import SERVERS_ROOT


_RAM_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMGTP]?)(?:I?B)?\s*$", re.IGNORECASE)


def _parse_ram_to_mb(value: object, default_mb: float) -> float:
    try:
        if value is None:
            return default_mb
        if isinstance(value, (int, float)):
            return float(value)
        raw = str(value).strip()
        if not raw:
            return default_mb
        m = _RAM_PATTERN.match(raw)
        if not m:
            return default_mb
        number = float(m.group(1))
        unit = (m.group(2) or '').upper()
        factors = {
            '': 1.0,
            'K': 1.0 / 1024.0,
            'M': 1.0,
            'G': 1024.0,
            'T': 1024.0 * 1024.0,
            'P': 1024.0 * 1024.0 * 1024.0,
        }
        factor = factors.get(unit, 1.0)
        mb_val = number * factor
        if mb_val <= 0:
            return default_mb
        return mb_val
    except Exception:
        return default_mb


def _gather_process_tree(pid: int) -> List[psutil.Process]:
    procs: List[psutil.Process] = []
    try:
        root = psutil.Process(pid)
    except Exception:
        return procs
    procs.append(root)
    try:
        procs.extend(root.children(recursive=True))
    except Exception:
        pass
    return procs


class LocalAdapter:
    """DockerManager-compatible adapter for LocalRuntimeManager."""

    def __init__(self) -> None:
        self.local = LocalRuntimeManager()
        self._docker = None
        self._steam_index: Dict[str, Dict[str, Any]] = {}

    def _get_docker(self):
        if self._docker is None:
            try:
                from docker_manager import DockerManager  # Local import to avoid circular dependency
            except Exception as exc:
                raise RuntimeError(f"Docker manager unavailable: {exc}")
            self._docker = DockerManager()
        return self._docker

    def _refresh_steam_index(self, entries: List[Dict[str, Any]]) -> None:
        index: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("server_kind", "")).lower() != "steam":
                continue
            cid = str(entry.get("id") or "")
            name = str(entry.get("name") or "")
            if cid:
                index[cid] = entry
            if name:
                index[name] = entry
        self._steam_index = index

    def _resolve_steam_id(self, container_id: str) -> Optional[str]:
        if not container_id:
            return None
        cached = self._steam_index.get(container_id)
        if cached and str(cached.get("server_kind", "")).lower() == "steam":
            return str(cached.get("id"))
        try:
            docker = self._get_docker()
        except Exception:
            return None
        try:
            container = docker.client.containers.get(container_id)
        except Exception:
            return None
        labels = (container.attrs.get("Config", {}) or {}).get("Labels", {}) or {}
        if str(labels.get("steam.server", "")).lower() == "true":
            identifier = container.id
            data = {
                "id": identifier,
                "name": getattr(container, "name", container_id),
                "status": getattr(container, "status", "unknown"),
                "server_kind": "steam",
            }
            self._steam_index[identifier] = data
            self._steam_index[data["name"]] = data
            return identifier
        return None

    # --- Server lifecycle ---
    def list_servers(self) -> List[Dict]:
        items = self.local.list_servers()
        for it in items:
            it.setdefault("server_kind", "minecraft")
        for it in items:
            name = it.get("name") or it.get("id")
            it.setdefault("labels", {})
            it.setdefault("mounts", [])
            it.setdefault("image", "local")
            raw_ports = {f"{MINECRAFT_PORT}/tcp": None}
            it.setdefault("ports", raw_ports)
            it.setdefault("port_mappings", {f"{MINECRAFT_PORT}/tcp": {"host_port": None, "host_ip": None}})
            # Enrich labels from metadata so features like updates work in local mode
            try:
                if name:
                    meta_path = (SERVERS_ROOT / str(name) / "server_meta.json")
                    if meta_path.exists():
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        lbl = it.get("labels") or {}
                        if isinstance(meta, dict):
                            prov = meta.get("modpack_provider")
                            pid = meta.get("modpack_id")
                            ver = meta.get("modpack_version_id")
                            if prov:
                                lbl["mc.modpack.provider"] = str(prov)
                            if pid:
                                lbl["mc.modpack.id"] = str(pid)
                            if ver:
                                lbl["mc.modpack.version_id"] = str(ver)
                        it["labels"] = lbl
            except Exception:
                pass

        steam_entries: List[Dict[str, Any]] = []
        try:
            docker = self._get_docker()
            docker_servers = docker.list_servers()
            for entry in docker_servers:
                try:
                    if str(entry.get("server_kind", "")).lower() != "steam":
                        continue
                    steam_entry = dict(entry)
                    steam_entries.append(steam_entry)
                except Exception:
                    continue
        except Exception:
            steam_entries = []

        if steam_entries:
            self._refresh_steam_index(steam_entries)
            items.extend(steam_entries)
        else:
            self._steam_index = {}
        return items

    def create_server(
        self,
        name: str,
        server_type: str,
        version: str,
        host_port: Optional[int] = None,
        loader_version: Optional[str] = None,
        min_ram: str = "1G",
        max_ram: str = "2G",
        installer_version: Optional[str] = None,
        extra_env: Optional[Dict[str, str]] = None,
        extra_labels: Optional[Dict[str, str]] = None,
    ) -> Dict:
        result = self.local.create_server(
            name,
            server_type,
            version,
            host_port=host_port,
            loader_version=loader_version,
            min_ram=min_ram,
            max_ram=max_ram,
            installer_version=installer_version,
        )
        # Persist modpack metadata into local server_meta.json if provided via labels
        try:
            if extra_labels:
                meta_updates: Dict[str, Any] = {}
                if "mc.modpack.provider" in extra_labels:
                    meta_updates["modpack_provider"] = extra_labels.get("mc.modpack.provider")
                if "mc.modpack.id" in extra_labels:
                    meta_updates["modpack_id"] = extra_labels.get("mc.modpack.id")
                if "mc.modpack.version_id" in extra_labels:
                    meta_updates["modpack_version_id"] = extra_labels.get("mc.modpack.version_id")
                if meta_updates:
                    self.local.update_metadata(name, **meta_updates)
        except Exception:
            pass
        return result

    def create_server_from_existing(
        self,
        name: str,
        host_port: Optional[int] = None,
        min_ram: str = "1G",
        max_ram: str = "2G",
        extra_env: Optional[Dict[str, str]] = None,
        extra_labels: Optional[Dict[str, str]] = None,
    ) -> Dict:
        result = self.local.create_server_from_existing(
            name,
            host_port=host_port,
            min_ram=min_ram,
            max_ram=max_ram,
            extra_env=extra_env,
            extra_labels=extra_labels,
        )
        # Persist modpack metadata into local server_meta.json if provided via labels
        try:
            if extra_labels:
                meta_updates: Dict[str, Any] = {}
                if "mc.modpack.provider" in extra_labels:
                    meta_updates["modpack_provider"] = extra_labels.get("mc.modpack.provider")
                if "mc.modpack.id" in extra_labels:
                    meta_updates["modpack_id"] = extra_labels.get("mc.modpack.id")
                if "mc.modpack.version_id" in extra_labels:
                    meta_updates["modpack_version_id"] = extra_labels.get("mc.modpack.version_id")
                if meta_updates:
                    self.local.update_metadata(name, **meta_updates)
        except Exception:
            pass
        return result

    def stop_server(self, container_id: str) -> Dict:
        steam_id = self._resolve_steam_id(container_id)
        if steam_id:
            return self._get_docker().stop_server(steam_id)
        return self.local.stop_server(container_id)

    def start_server(self, container_id: str) -> Dict:
        # For local runtime, starting means spawn from existing folder.
        # Pass None for RAM so LocalRuntimeManager preserves saved metadata values.
        steam_id = self._resolve_steam_id(container_id)
        if steam_id:
            return self._get_docker().start_server(steam_id)
        return self.local.create_server_from_existing(container_id, min_ram=None, max_ram=None)

    def restart_server(self, container_id: str) -> Dict:
        # Stop then start again from existing
        try:
            steam_id = self._resolve_steam_id(container_id)
        except Exception:
            steam_id = None
        if steam_id:
            return self._get_docker().restart_server(steam_id)
        try:
            self.local.stop_server(container_id)
        except Exception:
            pass
        # Preserve previously configured RAM by passing None to defer to metadata
        return self.local.create_server_from_existing(container_id, min_ram=None, max_ram=None)

    def kill_server(self, container_id: str) -> Dict:
        steam_id = self._resolve_steam_id(container_id)
        if steam_id:
            return self._get_docker().kill_server(steam_id)
        return self.local.stop_server(container_id)

    def delete_server(self, container_id: str) -> Dict:
        steam_id = self._resolve_steam_id(container_id)
        if steam_id:
            return self._get_docker().delete_server(steam_id)
        return self.local.stop_server(container_id)

    def update_metadata(self, container_id: str, **fields: Any) -> None:
        self.local.update_metadata(container_id, **fields)

    # --- Info & metrics ---
    def get_server_stats(self, container_id: str) -> Dict:
        steam_id = self._resolve_steam_id(container_id)
        if steam_id:
            return self._get_docker().get_server_stats(steam_id)
        p = (SERVERS_ROOT / container_id).resolve()
        pid = None
        try:
            pid_txt = (p / ".server.pid").read_text().strip()
            pid = int(pid_txt) if pid_txt else None
        except Exception:
            pid = None

        cpu_percent = 0.0
        mem_usage_mb = 0.0
        mem_limit_mb = float(psutil.virtual_memory().total) / (1024 * 1024)
        mem_percent = 0.0
        net_rx_mb = 0.0
        net_tx_mb = 0.0

        try:
            meta_path = (p / "server_meta.json")
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                mem_limit_mb = _parse_ram_to_mb(meta.get("max_ram_mb") or meta.get("max_ram"), mem_limit_mb)
        except Exception:
            pass

        if pid and psutil.pid_exists(pid):
            try:
                procs = _gather_process_tree(pid)
                if not procs:
                    procs = [psutil.Process(pid)]
                # Prime CPU samples
                for pr in procs:
                    try:
                        pr.cpu_percent(interval=None)
                    except Exception:
                        continue
                time.sleep(0.15)
                total_cpu = 0.0
                total_mem = 0
                total_rx = 0
                total_tx = 0
                for pr in procs:
                    try:
                        total_cpu += pr.cpu_percent(interval=None)
                    except Exception:
                        pass
                    try:
                        total_mem += pr.memory_info().rss
                    except Exception:
                        pass
                    net_func = getattr(pr, "net_io_counters", None)
                    if callable(net_func):
                        try:
                            counters = net_func()  # type: ignore[attr-defined]
                            if counters:
                                total_rx += getattr(counters, "bytes_recv", 0)
                                total_tx += getattr(counters, "bytes_sent", 0)
                        except Exception:
                            pass
                mem_usage_mb = float(total_mem) / (1024 * 1024)
                cpu_percent = total_cpu
                if total_rx:
                    net_rx_mb = round(total_rx / (1024 * 1024), 2)
                if total_tx:
                    net_tx_mb = round(total_tx / (1024 * 1024), 2)
                if mem_limit_mb:
                    mem_percent = (mem_usage_mb / mem_limit_mb) * 100.0
            except Exception:
                pass

        if mem_limit_mb <= 0:
            mem_limit_mb = max(mem_usage_mb, 1.0)

        return {
            "id": container_id,
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage_mb": round(mem_usage_mb, 2),
            "memory_limit_mb": round(mem_limit_mb, 2),
            "memory_percent": round(mem_percent, 2),
            "network_rx_mb": net_rx_mb,
            "network_tx_mb": net_tx_mb,
        }

    def get_bulk_server_stats(self, ttl_seconds: int = 3) -> Dict:
        results: Dict[str, Dict] = {}
        for it in self.list_servers():
            container_id = it.get("id") or it.get("name")
            if not container_id:
                continue
            results[container_id] = self.get_server_stats(str(container_id))
        return results

    def get_player_info(self, container_id: str) -> Dict:
        steam_id = self._resolve_steam_id(container_id)
        if steam_id:
            return {"online": 0, "max": 0, "names": []}
        return {"online": 0, "max": 0, "names": []}

    def get_server_info(self, container_id: str) -> Dict:
        steam_id = self._resolve_steam_id(container_id)
        if steam_id:
            info = self._get_docker().get_server_info(steam_id)
            info.setdefault("server_kind", "steam")
            return info
        p = (SERVERS_ROOT / container_id).resolve()
        exists = p.exists()
        meta: Dict[str, Any] = {}
        try:
            mp = p / "server_meta.json"
            if mp.exists():
                meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

        host_port = meta.get("host_port") or MINECRAFT_PORT
        server_type = meta.get("type")
        version = meta.get("version")
        created_at = meta.get("created_at")
        # Accept new created_ts (seconds epoch) or container_created_ts
        if not created_at:
            epoch_source = meta.get("created_ts") or meta.get("container_created_ts")
            if epoch_source:
                try:
                    from datetime import datetime
                    created_at = datetime.utcfromtimestamp(int(epoch_source))
                except Exception:
                    created_at = None
        java_version = meta.get("java_version", "unknown")
        minecraft_version = meta.get("minecraft_version") or meta.get("game_version")
        loader_version = meta.get("loader_version")

        java_args = ""
        try:
            env_overrides = meta.get("env_overrides")
            if isinstance(env_overrides, dict):
                val = env_overrides.get("JAVA_OPTS") or env_overrides.get("JAVA_ARGS")
                if isinstance(val, str):
                    java_args = val
        except Exception:
            java_args = ""

        info = {
            "id": container_id,
            "name": container_id,
            "status": "running",
            "type": server_type,
            "version": version,
            "created_at": created_at,
            "java_version": java_version,
            "minecraft_version": minecraft_version,
            "loader_version": loader_version,
            "mounts": [],
            "ports": {f"{MINECRAFT_PORT}/tcp": None},
            "port_mappings": {f"{MINECRAFT_PORT}/tcp": {"host_port": host_port, "host_ip": None}},
            "exists": exists,
            "java_args": java_args,
            "server_kind": str(meta.get("server_kind") or "minecraft").lower(),
        }
        return info

    def update_server_java_version(self, container_id: str, java_version: str) -> Dict:
        # Apply java version change for local runtime by persisting env overrides
        try:
            if java_version not in ("8", "11", "17", "21"):
                raise ValueError(f"Invalid Java version: {java_version}")
            java_bin = f"/usr/local/bin/java{java_version}"

            # Persist env overrides to server metadata and restart the process
            # Load existing metadata and merge
            try:
                meta_path = (SERVERS_ROOT / container_id / "server_meta.json")
                meta = {}
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8") or "{}")
            except Exception:
                meta = {}

            stored_overrides = meta.get("env_overrides") or {}
            if not isinstance(stored_overrides, dict):
                stored_overrides = {}
            merged = {str(k): str(v) for k, v in stored_overrides.items() if v is not None}
            # Persist both override-style keys and legacy keys for compatibility
            merged["JAVA_VERSION_OVERRIDE"] = str(java_version)
            merged["JAVA_BIN_OVERRIDE"] = str(java_bin)
            merged["JAVA_VERSION"] = str(java_version)
            merged["JAVA_BIN"] = str(java_bin)

            # update metadata (this will persist merged env_overrides)
            try:
                # Persist env_overrides under metadata so create_server_from_existing applies them
                # Also persist top-level java_version for UI visibility
                self.local.update_metadata(container_id, env_overrides=merged, java_version=str(java_version))
            except Exception:
                pass

            # Stop and restart the server so new env is applied
            try:
                self.local.stop_server(container_id)
            except Exception:
                pass
            # Preserve configured RAM by deferring to metadata
            result = self.local.create_server_from_existing(container_id, min_ram=None, max_ram=None)
            return {
                "success": True,
                "message": f"Java version updated to {java_version} and server restarted",
                "java_version": java_version,
                "java_bin": java_bin,
                "restarted": True,
                "result": result,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "id": container_id}

    def update_server_java_args(self, container_id: str, java_args: str) -> Dict:
        """Persist custom Java arguments (JAVA_OPTS) for local runtime and restart the server."""
        try:
            normalized = " ".join((java_args or "").replace("\r", " ").split())
            if len(normalized) > 4096:
                raise ValueError("java_args too long (max 4096 characters when normalized)")

            meta_path = (SERVERS_ROOT / container_id / "server_meta.json")
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8") or "{}") if meta_path.exists() else {}
            except Exception:
                meta = {}

            stored_overrides = meta.get("env_overrides") or {}
            if not isinstance(stored_overrides, dict):
                stored_overrides = {}
            merged = {str(k): str(v) for k, v in stored_overrides.items() if v is not None}
            if normalized:
                merged["JAVA_OPTS"] = normalized
            else:
                merged.pop("JAVA_OPTS", None)

            try:
                self.local.update_metadata(container_id, env_overrides=merged)
            except Exception:
                pass

            try:
                self.local.stop_server(container_id)
            except Exception:
                pass

            result = self.local.create_server_from_existing(
                container_id,
                min_ram=None,
                max_ram=None,
                extra_env=merged or None,
            )

            return {
                "success": True,
                "java_args": normalized,
                "restarted": True,
                "result": result,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "id": container_id}

    # --- Console/logs ---
    def get_server_logs(self, container_id: str, tail: int = 200) -> Dict:
        steam_id = self._resolve_steam_id(container_id)
        if steam_id:
            try:
                logs = self._get_docker().get_server_logs(steam_id, tail=tail)
                logs.setdefault("server_kind", "steam")
                return logs
            except Exception:
                return {"id": container_id, "logs": ""}
        log_path = (SERVERS_ROOT / container_id / "server.stdout.log").resolve()
        try:
            if not log_path.exists():
                return {"id": container_id, "logs": ""}
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            tail_lines = lines[-tail:] if tail and tail > 0 else lines
            return {"id": container_id, "logs": "\n".join(tail_lines)}
        except Exception:
            return {"id": container_id, "logs": ""}

    def get_server_terminal(self, container_id: str, tail: int = 100) -> Dict:
        steam_id = self._resolve_steam_id(container_id)
        if steam_id:
            return self.get_server_logs(steam_id, tail=tail)
        return self.get_server_logs(container_id, tail=tail)

    def send_command(self, container_id: str, command: str) -> Dict:
        steam_id = self._resolve_steam_id(container_id)
        if steam_id:
            return self._get_docker().send_command(steam_id, command)
        fifo_path = (SERVERS_ROOT / container_id / "console.in").resolve()
        try:
            if not fifo_path.exists():
                return {"id": container_id, "ok": False, "error": "Console pipe not available"}
            data = (command or '').strip()
            if not data:
                return {"id": container_id, "ok": False, "error": "Empty command"}
            with open(fifo_path, 'w', encoding='utf-8', buffering=1) as f:
                f.write(data + "\n")
            return {"id": container_id, "ok": True}
        except Exception as e:
            return {"id": container_id, "ok": False, "error": str(e)}

    # --- Rename server support (parity with DockerManager.rename_server) ---
    def rename_server(self, old_name: str, new_name: str) -> Dict:
        """Rename a local-runtime server directory and restart under the new name.

        Steps:
        - Stop any running local process for old_name (best-effort)
        - Rename directory SERVERS_ROOT/old_name -> SERVERS_ROOT/new_name
        - Update server_meta.json (name + previous_names)
        - Recreate the local server process preserving RAM and env_overrides
        """
        old_dir = (SERVERS_ROOT / old_name).resolve()
        new_dir = (SERVERS_ROOT / new_name).resolve()
        if not old_dir.exists() or not old_dir.is_dir():
            return {"ok": False, "error": f"Server directory {old_dir} not found"}
        if new_dir.exists():
            return {"ok": False, "error": f"Target directory {new_dir} already exists"}

        # Stop old process (ignore errors)
        try:
            self.local.stop_server(old_name)
        except Exception:
            pass

        # Read metadata to preserve RAM and env
        meta_path = old_dir / "server_meta.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8") or "{}")
            except Exception:
                meta = {}
        try:
            _min_mb = meta.get("min_ram_mb")
            min_ram = meta.get("min_ram") or (f"{int(_min_mb)}M" if isinstance(_min_mb, (int, float, str)) and str(_min_mb).isdigit() else None)
        except Exception:
            min_ram = meta.get("min_ram")
        try:
            _max_mb = meta.get("max_ram_mb")
            max_ram = meta.get("max_ram") or (f"{int(_max_mb)}M" if isinstance(_max_mb, (int, float, str)) and str(_max_mb).isdigit() else None)
        except Exception:
            max_ram = meta.get("max_ram")
        env_overrides = meta.get("env_overrides") if isinstance(meta.get("env_overrides"), dict) else {}

        # Rename directory
        old_dir.rename(new_dir)

        # Update metadata name/history
        try:
            new_meta = dict(meta or {})
            prev = new_meta.get("previous_names") or []
            if isinstance(prev, list):
                if old_name not in prev:
                    prev.append(old_name)
                new_meta["previous_names"] = prev
            new_meta["name"] = new_name
            (new_dir / "server_meta.json").write_text(json.dumps(new_meta), encoding="utf-8")
        except Exception:
            pass

        # Recreate under new name preserving RAM/env (allow LocalRuntimeManager to infer defaults if None)
        try:
            result = self.local.create_server_from_existing(
                new_name,
                host_port=None,
                min_ram=min_ram,
                max_ram=max_ram,
                extra_env=env_overrides or None,
            )
        except Exception as e:
            return {"ok": False, "error": str(e)}

        return {"ok": True, "old_name": old_name, "new_name": new_name, "result": result}

    # --- Ports helpers used by API ---
    def get_used_host_ports(self, only_minecraft: bool = True) -> Set[int]:
        return set()

    def pick_available_port(self, preferred: Optional[int] = None, start: int = 25565, end: int = 25999) -> int:
        return int(preferred or start)


_adapter_cache: Optional[Any] = None


def get_runtime_manager():
    if os.getenv("RUNTIME_MODE", "docker").lower() == "local":
        return LocalAdapter()
    return None


def get_runtime_manager_or_docker():
    global _adapter_cache
    if _adapter_cache is not None:
        return _adapter_cache

    adapter = None
    try:
        adapter = get_runtime_manager()
    except Exception:
        adapter = None

    if adapter is not None:
        _adapter_cache = adapter
        return adapter

    from docker_manager import DockerManager  # Local import to avoid circular dependency

    _adapter_cache = DockerManager()
    return _adapter_cache
