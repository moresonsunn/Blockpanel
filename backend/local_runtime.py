import os
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List

from config import SERVERS_ROOT
from download_manager import prepare_server_files

logger = logging.getLogger(__name__)

MINECRAFT_PORT = 25565


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
        env = {
            "SERVER_DIR_NAME": name,
            "MIN_RAM": str(min_ram),
            "MAX_RAM": str(max_ram),
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
        env = {
            "SERVER_DIR_NAME": name,
            "MIN_RAM": str(min_ram),
            "MAX_RAM": str(max_ram),
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
                items.append({
                    "id": name,
                    "name": name,
                    "status": status,
                    "type": None,
                    "version": None,
                    "ports": {f"{MINECRAFT_PORT}/tcp": None},
                })
        except Exception as e:
            logger.warning(f"Local list_servers failed: {e}")
        return items
