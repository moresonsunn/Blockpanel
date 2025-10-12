import os
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
import re

from config import SERVERS_ROOT
from download_manager import prepare_server_files
import json

logger = logging.getLogger(__name__)

MINECRAFT_PORT = 25565

_RAM_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMGTP]?)(?:I?B)?\s*$", re.IGNORECASE)


def _ram_to_mb(value: str | int | float, default_mb: int) -> int:
    try:
        if value is None:
            return default_mb
        if isinstance(value, (int, float)):
            return max(int(float(value)), 0)
        raw = str(value).strip()
        if not raw:
            return default_mb
        m = _RAM_PATTERN.match(raw)
        if not m:
            return default_mb
        number = float(m.group(1))
        unit = (m.group(2) or '').upper()
        multipliers = {
            '': 1,  # assume value already in megabytes
            'K': 1.0 / 1024.0,
            'M': 1,
            'G': 1024,
            'T': 1024 * 1024,
            'P': 1024 * 1024 * 1024,
        }
        factor = multipliers.get(unit, 1)
        mb_val = int(round(number * factor))
        if mb_val <= 0:
            return default_mb
        return mb_val
    except Exception:
        return default_mb


def _format_ram(mb_value: int, prefer: str = 'G') -> str:
    if mb_value <= 0:
        return '512M'
    if prefer.upper() == 'G' and mb_value % 1024 == 0:
        return f"{mb_value // 1024}G"
    return f"{mb_value}M"


class LocalRuntimeManager:
    """
    Run Minecraft servers as child processes inside the controller container.
    This mirrors how Crafty runs servers (no extra Docker containers),
    so CasaOS will not create additional "Legacy App" entries.

    Limitations:
      - Only ports exposed on the controller container are reachable from LAN.
        Map additional ports in compose/CasaOS if you need more servers.
      - Stop is best-effort (SIGTERM to process group). Consider enabling RCON for graceful stops.
    """

    def _server_dir(self, name: str) -> Path:
        return SERVERS_ROOT / name

    def _pid_file(self, name: str) -> Path:
        return self._server_dir(name) / ".server.pid"

    def _log_file(self, name: str) -> Path:
        return self._server_dir(name) / "server.stdout.log"

    def _meta_file(self, name: str) -> Path:
        return self._server_dir(name) / "server_meta.json"

    def _load_meta(self, name: str) -> Dict[str, Any]:
        meta_path = self._meta_file(name)
        if meta_path.exists():
            try:
                return json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_meta(self, name: str, meta: Dict[str, Any]) -> None:
        try:
            self._meta_file(name).write_text(json.dumps(meta), encoding="utf-8")
        except Exception:
            pass

    def update_metadata(self, name: str, **fields: Any) -> None:
        meta = self._load_meta(name)
        if not meta:
            meta = {"name": name, "created_at": int(time.time())}
        changed = False
        for key, value in fields.items():
            if value is None:
                continue
            if meta.get(key) != value:
                meta[key] = value
                changed = True
        if changed:
            meta.setdefault("name", name)
            meta.setdefault("created_at", int(time.time()))
            self._save_meta(name, meta)

    def _is_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    def _spawn(self, name: str, env: Dict[str, str]) -> Dict:
        srv_dir = self._server_dir(name)
        srv_dir.mkdir(parents=True, exist_ok=True)

        # Ensure EULA is accepted
        try:
            (srv_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
        except Exception:
            pass

        # Align server.properties with requested port if provided
        try:
            port_val = int(env.get("SERVER_PORT", MINECRAFT_PORT))
            self._ensure_server_port(srv_dir, port_val)
        except Exception:
            pass

        logf = open(self._log_file(name), "ab", buffering=0)
        cmd = ["/usr/local/bin/runtime-entrypoint.sh"]

        # Merge environment
        run_env = os.environ.copy()
        run_env.update(env)

        # Launch as its own process group so we can terminate the whole tree
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(srv_dir),
                stdout=logf,
                stderr=subprocess.STDOUT,
                env=run_env,
                close_fds=True,
            )
        except Exception as e:
            logf.close()
            raise RuntimeError(f"Failed to launch server process: {e}")

        # Write PID file
        try:
            self._pid_file(name).write_text(str(proc.pid), encoding="utf-8")
        except Exception:
            pass
        return {"id": name, "name": name, "status": "running", "pid": proc.pid}

    def _ensure_server_port(self, srv_dir: Path, port: int) -> None:
        props = srv_dir / "server.properties"
        try:
            content = ""
            if props.exists():
                content = props.read_text(encoding="utf-8", errors="ignore")
            lines = [ln for ln in content.splitlines() if ln.strip() != ""] if content else []
            found = False
            for idx, ln in enumerate(lines):
                if ln.strip().startswith("server-port="):
                    lines[idx] = f"server-port={int(port)}"
                    found = True
                    break
            if not found:
                lines.append(f"server-port={int(port)}")
            props.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            # Best effort only
            pass

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
        srv_dir = self._server_dir(name)
        srv_dir.mkdir(parents=True, exist_ok=True)
        # Prepare files (downloads jars/installers)
        prepare_server_files(
            server_type,
            version,
            srv_dir,
            loader_version=loader_version or "",
            installer_version=installer_version or "",
        )
        min_mb = _ram_to_mb(min_ram, default_mb=1024)
        max_mb = _ram_to_mb(max_ram, default_mb=2048)
        # Ensure max >= min
        if max_mb < min_mb:
            max_mb = min_mb
        # Persist metadata for UI and management
        meta = {
            "name": name,
            "type": server_type,
            "version": version,
            "loader_version": loader_version or None,
            "installer_version": installer_version or None,
            "min_ram": _format_ram(min_mb),
            "max_ram": _format_ram(max_mb),
            "min_ram_mb": min_mb,
            "max_ram_mb": max_mb,
            "host_port": int(host_port or MINECRAFT_PORT),
            "created_at": int(time.time()),
        }
        self._save_meta(name, meta)
        env = {
            "SERVER_DIR_NAME": name,
            "MIN_RAM": meta["min_ram"],
            "MAX_RAM": meta["max_ram"],
            "SERVER_PORT": str(host_port or MINECRAFT_PORT),
            "SERVER_TYPE": server_type,
            "SERVER_VERSION": version,
        }
        return self._spawn(name, env)

    def create_server_from_existing(
        self,
        name: str,
        host_port: Optional[int] = None,
        min_ram: str = "1G",
        max_ram: str = "2G",
        extra_env: Optional[Dict[str, str]] = None,
        extra_labels: Optional[Dict[str, str]] = None,
    ) -> Dict:
        srv_dir = self._server_dir(name)
        if not srv_dir.exists() or not srv_dir.is_dir():
            raise RuntimeError(f"Server directory {srv_dir} does not exist")
        # Update or create metadata
        meta = self._load_meta(name)
        # Ensure defaults
        meta.setdefault("name", name)
        meta.setdefault("type", None)
        meta.setdefault("version", None)
        meta.setdefault("created_at", int(time.time()))
        if host_port:
            try:
                meta["host_port"] = int(host_port)
            except Exception:
                pass
        min_mb = _ram_to_mb(min_ram, default_mb=int(meta.get("min_ram_mb") or 1024))
        max_mb = _ram_to_mb(max_ram, default_mb=int(meta.get("max_ram_mb") or 2048))
        if max_mb < min_mb:
            max_mb = min_mb
        meta["min_ram"] = _format_ram(min_mb)
        meta["max_ram"] = _format_ram(max_mb)
        meta["min_ram_mb"] = min_mb
        meta["max_ram_mb"] = max_mb
        self._save_meta(name, meta)
        env = {
            "SERVER_DIR_NAME": name,
            "MIN_RAM": meta["min_ram"],
            "MAX_RAM": meta["max_ram"],
            "SERVER_PORT": str(host_port or MINECRAFT_PORT),
        }
        for k, v in (extra_env or {}).items():
            if v is None:
                continue
            env[str(k)] = str(v)
        return self._spawn(name, env)

    def stop_server(self, server_id: str) -> Dict:
        # server_id is the name in local mode
        name = server_id
        pid_file = self._pid_file(name)
        pid = None
        try:
            if pid_file.exists():
                pid = int(pid_file.read_text().strip())
        except Exception:
            pid = None
        if not pid:
            return {"id": name, "status": "unknown", "method": "noop"}

        # Try graceful SIGTERM first
        try:
            os.kill(pid, 15)  # SIGTERM
        except Exception as e:
            logger.warning(f"SIGTERM failed for {name} ({pid}): {e}")
        # Wait a bit
        deadline = time.time() + 10
        while time.time() < deadline:
            if not self._is_running(pid):
                break
            time.sleep(0.5)
        # Force kill if still running
        if self._is_running(pid):
            try:
                os.kill(pid, 9)
            except Exception as e:
                logger.warning(f"SIGKILL failed for {name} ({pid}): {e}")
        try:
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass
        return {"id": name, "status": "stopped", "method": "signal"}

    def list_servers(self) -> List[Dict]:
        items: List[Dict] = []
        try:
            for child in SERVERS_ROOT.iterdir():
                if not child.is_dir():
                    continue
                name = child.name
                pid = None
                try:
                    if self._pid_file(name).exists():
                        pid = int(self._pid_file(name).read_text().strip())
                except Exception:
                    pid = None
                status = "running" if (pid and self._is_running(pid)) else "exited"
                # Load metadata
                meta = {}
                try:
                    mp = self._meta_file(name)
                    if mp.exists():
                        meta = json.loads(mp.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
                host_port = meta.get("host_port") or MINECRAFT_PORT
                server_type = meta.get("type")
                version = meta.get("version")
                items.append({
                    "id": name,
                    "name": name,
                    "status": status,
                    "type": server_type,
                    "version": version,
                    "host_port": host_port,
                    "created_at": meta.get("created_at"),
                    "ports": {f"{MINECRAFT_PORT}/tcp": None},
                })
        except Exception as e:
            logger.warning(f"Local list_servers failed: {e}")
        return items
