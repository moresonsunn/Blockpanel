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

    # --- Server lifecycle ---
    def list_servers(self) -> List[Dict]:
        items = self.local.list_servers()
        for it in items:
            it.setdefault("labels", {})
            it.setdefault("mounts", [])
            it.setdefault("image", "local")
            raw_ports = {f"{MINECRAFT_PORT}/tcp": None}
            it.setdefault("ports", raw_ports)
            it.setdefault("port_mappings", {f"{MINECRAFT_PORT}/tcp": {"host_port": None, "host_ip": None}})
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
    ) -> Dict:
        return self.local.create_server(
            name,
            server_type,
            version,
            host_port=host_port,
            loader_version=loader_version,
            min_ram=min_ram,
            max_ram=max_ram,
            installer_version=installer_version,
        )

    def create_server_from_existing(
        self,
        name: str,
        host_port: Optional[int] = None,
        min_ram: str = "1G",
        max_ram: str = "2G",
        extra_env: Optional[Dict[str, str]] = None,
        extra_labels: Optional[Dict[str, str]] = None,
    ) -> Dict:
        return self.local.create_server_from_existing(
            name,
            host_port=host_port,
            min_ram=min_ram,
            max_ram=max_ram,
            extra_env=extra_env,
            extra_labels=extra_labels,
        )

    def stop_server(self, container_id: str) -> Dict:
        return self.local.stop_server(container_id)

    def start_server(self, container_id: str) -> Dict:
        return self.local.create_server_from_existing(container_id)

    def restart_server(self, container_id: str) -> Dict:
        self.local.stop_server(container_id)
        return self.local.create_server_from_existing(container_id)

    def kill_server(self, container_id: str) -> Dict:
        return self.local.stop_server(container_id)

    def delete_server(self, container_id: str) -> Dict:
        return self.local.stop_server(container_id)

    def update_metadata(self, container_id: str, **fields: Any) -> None:
        self.local.update_metadata(container_id, **fields)

    # --- Info & metrics ---
    def get_server_stats(self, container_id: str) -> Dict:
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
        return {"online": 0, "max": 0, "names": []}

    def get_server_info(self, container_id: str) -> Dict:
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
        java_version = meta.get("java_version", "unknown")
        minecraft_version = meta.get("minecraft_version") or meta.get("game_version")
        loader_version = meta.get("loader_version")

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
        }
        return info

    def update_server_java_version(self, container_id: str, java_version: str) -> Dict:
        return {"id": container_id, "java_version": java_version}

    # --- Console/logs ---
    def get_server_logs(self, container_id: str, tail: int = 200) -> Dict:
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
        return self.get_server_logs(container_id, tail=tail)

    def send_command(self, container_id: str, command: str) -> Dict:
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

    # --- Ports helpers used by API ---
    def get_used_host_ports(self, only_minecraft: bool = True) -> Set[int]:
        return set()

    def pick_available_port(self, preferred: Optional[int] = None, start: int = 25565, end: int = 25999) -> int:
        return int(preferred or start)


def get_runtime_manager():
    if os.getenv("RUNTIME_MODE", "docker").lower() == "local":
        return LocalAdapter()
    return None
