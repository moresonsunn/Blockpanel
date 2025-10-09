import os
from pathlib import Path
from typing import Dict, List, Optional, Set

from local_runtime import LocalRuntimeManager, MINECRAFT_PORT
from config import SERVERS_ROOT


class LocalAdapter:
    """
    Adapter that exposes a DockerManager-like interface backed by LocalRuntimeManager.
    Only implements methods used by the API; non-essential calls return defaults.
    """

    def __init__(self) -> None:
        self.local = LocalRuntimeManager()

    # --- Server lifecycle ---
    def list_servers(self) -> List[Dict]:
        items = self.local.list_servers()
        # Normalize shape to match DockerManager.list_servers()
        for it in items:
            it.setdefault("labels", {})
            it.setdefault("mounts", [])
            it.setdefault("image", "local")
            # Provide raw ports and port_mappings keys for UI helpers
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
        # Start by treating it as existing
        return self.local.create_server_from_existing(container_id)

    def restart_server(self, container_id: str) -> Dict:
        self.local.stop_server(container_id)
        return self.local.create_server_from_existing(container_id)

    def kill_server(self, container_id: str) -> Dict:
        return self.local.stop_server(container_id)

    def delete_server(self, container_id: str) -> Dict:
        # Local mode: just stop; keep files on disk like Docker version does
        return self.local.stop_server(container_id)

    # --- Info & metrics ---
    def get_server_stats(self, container_id: str) -> Dict:
        # No cgroups in local mode; return zeros
        return {
            "id": container_id,
            "cpu_percent": 0.0,
            "memory_usage_mb": 0.0,
            "memory_limit_mb": 0.0,
            "memory_percent": 0.0,
            "network_rx_mb": 0.0,
            "network_tx_mb": 0.0,
        }

    def get_bulk_server_stats(self, ttl_seconds: int = 3) -> Dict:
        items = {}
        for it in self.list_servers():
            cid = it.get("id") or it.get("name")
            if cid:
                items[cid] = self.get_server_stats(cid)
        return items

    def get_player_info(self, container_id: str) -> Dict:
        return {"online": 0, "max": 0, "names": []}

    def get_server_info(self, container_id: str) -> Dict:
        # Minimal info for UI
        p = (SERVERS_ROOT / container_id).resolve()
        exists = p.exists()
        java_version = None
        try:
            sp = p / "server.properties"
            if sp.exists():
                for line in sp.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("enable-rcon"):
                        break
        except Exception:
            pass
        return {
            "id": container_id,
            "name": container_id,
            "status": "running",
            "java_version": java_version or "unknown",
            "mounts": [],
            "ports": {f"{MINECRAFT_PORT}/tcp": None},
            "port_mappings": {f"{MINECRAFT_PORT}/tcp": {"host_port": None, "host_ip": None}},
            "exists": exists,
        }

    def update_server_java_version(self, container_id: str, java_version: str) -> Dict:
        # Not supported in local mode dynamically
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
        # Not supported; requires stdin pipe to Java process
        return {"id": container_id, "ok": False, "error": "Not supported in local mode"}

    # --- Ports helpers used by API ---
    def get_used_host_ports(self, only_minecraft: bool = True) -> Set[int]:
        # No extra containers, assume none in use by us
        return set()

    def pick_available_port(self, preferred: Optional[int] = None, start: int = 25565, end: int = 25999) -> int:
        # In local mode, ports are bound in-process; honor preferred or default
        return int(preferred or start)


def get_runtime_manager():
    """Factory that returns local adapter if RUNTIME_MODE=local, else None."""
    if os.getenv("RUNTIME_MODE", "docker").lower() == "local":
        return LocalAdapter()
    return None
