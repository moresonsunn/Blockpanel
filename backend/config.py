from pathlib import Path
import os

# Container-visible servers directory (bind-mounted from host or a named volume)
SERVERS_ROOT = Path(os.environ.get("SERVERS_CONTAINER_ROOT", "/data/servers"))
SERVERS_ROOT.mkdir(parents=True, exist_ok=True)

# Optional: absolute host path to servers directory for bind mounting into runtime containers
SERVERS_HOST_ROOT = os.environ.get("SERVERS_HOST_ROOT", "")

# Named volume to share server data between controller and runtime containers
SERVERS_VOLUME_NAME = os.environ.get("SERVERS_VOLUME_NAME", "minecraft-server_mc_servers_data")