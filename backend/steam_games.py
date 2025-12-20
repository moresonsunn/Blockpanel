"""Curated Steam game catalog used by the Steam install endpoints.

The catalog is kept intentionally small so we can document and test the
images we ship. To make it easier to grow the list without touching code we
also merge in optional JSON descriptors located under backend/data/steam_games.
"""

from __future__ import annotations

import json
from pathlib import Path


BASE_STEAM_GAMES = {
    "palworld": {
        "display_name": "Palworld",
        "summary": "Co-op creature survival shooter with heavy CPU load on busy worlds.",
        "notes": "Set a strong admin password and monitor CPU usage as bases grow.",
        "default_name": "palworld",
        "image": "thijsvanloef/palworld-server-docker:latest",
        "ports": [
            {"container": 8211, "protocol": "udp"},
            {"container": 27015, "protocol": "udp"},
        ],
        "env": {
            "PUID": 1000,
            "PGID": 1000,
            "TZ": "UTC",
            "SERVER_NAME": "Palworld Server",
            "SERVER_PASSWORD": "change-me",
            "ADMIN_PASSWORD": "admin",
        },
        "volume": {"container": "/palworld"},
    },
    "project_zomboid": {
        "display_name": "Project Zomboid",
        "summary": "Isometric zombie survival with persistent worlds and RCON support.",
        "notes": "Watch RAM usage for large maps and set an admin password.",
        "default_name": "zomboid",
        "image": "ghcr.io/ich777/steamcmd:projectzomboid",
        "ports": [
            {"container": 16261, "protocol": "udp"},
            {"container": 16262, "protocol": "tcp"},
        ],
        "env": {
            "PUID": 1000,
            "PGID": 1000,
            "TZ": "UTC",
            "ADMIN_PASSWORD": "admin",
            "SERVER_NAME": "Zomboid Server",
        },
        "volume": {"container": "/home/steam/Zomboid"},
    },
    "valheim": {
        "display_name": "Valheim",
        "summary": "Popular Viking survival sandbox supporting up to 10 players.",
        "notes": "Configure world name and server password; open UDP ports 2456-2458.",
        "default_name": "valheim",
        "image": "lloesche/valheim-server:latest",
        "ports": [
            {"container": 2456, "protocol": "udp"},
            {"container": 2457, "protocol": "udp"},
            {"container": 2458, "protocol": "udp"},
        ],
        "env": {
            "SERVER_NAME": "Valheim Server",
            "WORLD_NAME": "Dedicated",
            "SERVER_PASS": "change-me",
        },
        "volume": {"container": "/config"},
    },
    "tmodloader": {
        "display_name": "Terraria (tModLoader)",
        "summary": "Modded Terraria server via tModLoader with SteamCMD builds.",
        "notes": "Set world seed, max players, and password as desired.",
        "default_name": "tmodloader",
        "image": "ghcr.io/beardedio/terraria:latest",
        "ports": [
            {"container": 7777, "protocol": "tcp"},
        ],
        "env": {
            "WORLD_NAME": "Dedicated",
            "MAX_PLAYERS": 8,
            "TYPE": "tmodloader",
            "WORLD_FILENAME": "Dedicated.wld",
            "WORLD_SIZE": 3,
            "WORLD_DIFFICULTY": 1,
            "WORLD_SEED": "",
        },
        "volume": {"container": "/config"},
    },
    "cs2": {
        "display_name": "Counter-Strike 2",
        "summary": "Dedicated CS2 server with tickrate and RCON configuration.",
        "notes": "Open both UDP and TCP 27015. Configure RCON and lobby passwords.",
        "default_name": "cs2",
        "image": "cm2network/cs2:latest",
        "ports": [
            {"container": 27015, "protocol": "udp"},
            {"container": 27015, "protocol": "tcp"},
        ],
        "env": {
            "SRCDS_RCONPW": "change-me",
            "SRCDS_PW": "",
            "SRCDS_TV_PW": "",
            "SRCDS_FPSMAX": 300,
            "SRCDS_TICKRATE": 128,
        },
        "volume": {"container": "/home/steam/cs2-dedicated"},
    },
    "factorio": {
        "display_name": "Factorio",
        "summary": "Automation factory builder with deterministic saves and mods.",
        "notes": "Enable save/backups and set a server password if needed.",
        "default_name": "factorio",
        "image": "factoriotools/factorio:stable",
        "ports": [
            {"container": 34197, "protocol": "udp"},
        ],
        "env": {
            "SERVER_NAME": "Factorio Server",
            "SERVER_PASSWORD": "",
            "LOAD_LATEST_SAVE": "true",
        },
        "volume": {"container": "/factorio"},
    },
    "rust": {
        "display_name": "Rust",
        "summary": "Survival sandbox with monthly wipes; RCON enabled by default.",
        "notes": "Adjust RCON password immediately and consider enabling team size limits.",
        "default_name": "rust",
        "image": "didstopia/rust-server:latest",
        "ports": [
            {"container": 28015, "protocol": "udp"},
            {"container": 28015, "protocol": "tcp"},
            {"container": 28016, "protocol": "tcp"},
        ],
        "env": {
            "RUST_SERVER_NAME": "Rust Server",
            "RUST_SERVER_DESCRIPTION": "Managed by Lynx",
            "RUST_SERVER_MAXPLAYERS": 32,
            "RUST_RCON_PASSWORD": "change-me",
            "PUID": 1000,
            "PGID": 1000,
            "TZ": "UTC",
        },
        "volume": {"container": "/steamcmd/rust"},
    },
    "satisfactory": {
        "display_name": "Satisfactory",
        "summary": "Co-op factory builder with three exposed UDP ports.",
        "notes": "Back up saves frequently; dedicated servers are still in early access.",
        "default_name": "satisfactory",
        "image": "wolveix/satisfactory-server:latest",
        "ports": [
            {"container": 7777, "protocol": "udp"},
            {"container": 15000, "protocol": "udp"},
            {"container": 15777, "protocol": "udp"},
        ],
        "env": {
            "PUID": 1000,
            "PGID": 1000,
            "TZ": "UTC",
            "DEBUG": "false",
        },
        "volume": {"container": "/config"},
    },
    "7_days_to_die": {
        "display_name": "7 Days to Die",
        "summary": "Zombie survival crafting with scheduled blood moons.",
        "notes": "Enable auto-backups and tweak blood moon frequency in the config.",
        "default_name": "7d2d",
        "image": "didstopia/7dtd-server:latest",
        "ports": [
            {"container": 26900, "protocol": "udp"},
            {"container": 26900, "protocol": "tcp"},
            {"container": 26901, "protocol": "udp"},
            {"container": 26902, "protocol": "udp"},
        ],
        "env": {
            "PUID": 1000,
            "PGID": 1000,
            "TZ": "UTC",
            "EULA": "TRUE",
            "SERVER_NAME": "7 Days Server",
            "SERVER_PASS": "change-me",
        },
        "volume": {"container": "/config"},
    },
    "enshrouded": {
        "display_name": "Enshrouded",
        "summary": "Co-op survival action RPG running under Proton.",
        "notes": "Image uses Wine/Proton; Steam login is required. Query port must stay gamePort+1.",
        "default_name": "enshrouded",
        "image": "colirbi/enshrouded:latest",
        "ports": [
            {"container": 15636, "protocol": "udp"},
            {"container": 15637, "protocol": "udp"},
        ],
        "env": {
            "PUID": 1000,
            "PGID": 1000,
            "TZ": "UTC",
            "SRV_NAME": "Enshrouded Server",
            "SRV_PW": "",
            "MAX_PLAYERS": 16,
            "AUTO_UPDATE": 0,
            "QUERY_PORT": 15637,
            "STEAM_USER": "",
            "STEAM_PASSWORD": "",
        },
        "volume": {"container": "/config"},
    },
    "assetto_corsa": {
        "display_name": "Assetto Corsa",
        "summary": "Dedicated racing server with stracker telemetry.",
        "notes": "Requires a Steam account without Steam Guard. Set STEAM_USER/STEAM_PASSWORD and mount /steamapps writable.",
        "default_name": "assetto",
        "image": "germanrcuriel/assetto-corsa-server:latest",
        "ports": [
            {"container": 8081, "protocol": "tcp"},
            {"container": 9600, "protocol": "tcp"},
            {"container": 9600, "protocol": "udp"},
            {"container": 50041, "protocol": "tcp"},
            {"container": 50042, "protocol": "tcp"},
        ],
        "env": {
            "PUID": 1000,
            "PGID": 1000,
            "TZ": "UTC",
            "STEAM_USER": "",
            "STEAM_PASSWORD": "",
            "AC_SERVER_NAME": "Assetto Server",
            "AC_PASSWORD": "",
            "AC_ADMIN_PASSWORD": "change-me",
            "AC_FORCE_UPDATE": 0,
        },
        "volume": {"container": "/steamapps"},
    },
    "ark_survival_ascended": {
        "display_name": "ARK: Survival Ascended",
        "summary": "UE5 reboot of ARK with high CPU/RAM requirements.",
        "notes": "Peer port is game+1; allow at least 11GB RAM before players join.",
        "default_name": "ark-sa",
        "image": "acekorneya/asa_server:latest",
        "ports": [
            {"container": 7777, "protocol": "udp"},
            {"container": 7778, "protocol": "udp"},
            {"container": 27015, "protocol": "udp"},
            {"container": 37015, "protocol": "tcp"},
        ],
        "env": {
            "SESSION_NAME": "ARK Ascended",
            "SERVER_PASSWORD": "",
            "ADMIN_PASSWORD": "change-me",
            "MAX_PLAYERS": 70,
            "QUERY_PORT": 27015,
            "AUTO_UPDATE": 0,
        },
        "volume": {"container": "/config"},
    },
    "the_front": {
        "display_name": "The Front",
        "summary": "PvPvE survival shooter with four exposed service ports.",
        "notes": "Do not append flags after the password flag; server tags limited to five entries.",
        "default_name": "the-front",
        "image": "mcltn/thefrontdedicated:latest",
        "ports": [
            {"container": 27015, "protocol": "udp"},
            {"container": 27016, "protocol": "udp"},
            {"container": 27017, "protocol": "udp"},
            {"container": 27018, "protocol": "udp"},
        ],
        "env": {
            "SERVER_NAME": "The Front Server",
            "SERVER_PASSWORD": "",
            "QUERY_PORT": 27017,
            "SHUTDOWN_PORT": 27018,
            "MAX_PLAYERS": 50,
            "AUTO_UPDATE": 0,
        },
        "volume": {"container": "/config"},
    },
    "dayz": {
        "display_name": "DayZ",
        "summary": "Open-world survival shooter on Chernarus or modded maps.",
        "notes": "Query port is game+1; set a password if public.",
        "default_name": "dayz",
        "image": "razorbladex401/dayz:latest",
        "ports": [
            {"container": 2302, "protocol": "udp"},
            {"container": 2303, "protocol": "udp"},
            {"container": 2305, "protocol": "udp"},
        ],
        "env": {
            "SERVER_NAME": "DayZ Server",
            "SERVER_PASSWORD": "",
            "ADMIN_PASSWORD": "change-me",
            "MAX_PLAYERS": 60,
        },
        "volume": {"container": "/config"},
    },
    "ark_survival_evolved": {
        "display_name": "ARK: Survival Evolved",
        "summary": "Classic ARK dedicated server.",
        "notes": "Peer port is game+1; allow high CPU/RAM for larger maps.",
        "default_name": "ark-se",
        "image": "turzam/ark:latest",
        "ports": [
            {"container": 7777, "protocol": "udp"},
            {"container": 7778, "protocol": "udp"},
            {"container": 27015, "protocol": "udp"},
            {"container": 27020, "protocol": "tcp"},
        ],
        "env": {
            "SESSION_NAME": "ARK SE",
            "SERVER_PASSWORD": "",
            "ADMIN_PASSWORD": "change-me",
            "MAX_PLAYERS": 70,
            "QUERY_PORT": 27015,
        },
        "volume": {"container": "/config"},
    },
    "conan_exiles": {
        "display_name": "Conan Exiles",
        "summary": "Survival sandbox in the Exiled Lands.",
        "notes": "Enable RCON if you need remote admin; defaults are open.",
        "default_name": "conan-exiles",
        "image": "punchmesan/conanexiles:latest",
        "ports": [
            {"container": 7777, "protocol": "udp"},
            {"container": 7778, "protocol": "udp"},
            {"container": 27015, "protocol": "udp"},
            {"container": 25575, "protocol": "tcp"},
        ],
        "env": {
            "SERVER_NAME": "Conan Server",
            "SERVER_PASSWORD": "",
            "ADMIN_PASSWORD": "change-me",
            "MAXPLAYERS": 40,
        },
        "volume": {"container": "/config"},
    },
    "squad": {
        "display_name": "Squad",
        "summary": "Tactical FPS with VOIP and large maps.",
        "notes": "Set RCON password; ensure UDP ports are forwarded.",
        "default_name": "squad",
        "image": "cm2network/squad:latest",
        "ports": [
            {"container": 7787, "protocol": "udp"},
            {"container": 27165, "protocol": "udp"},
            {"container": 21114, "protocol": "tcp"},
        ],
        "env": {
            "SERVER_NAME": "Squad Server",
            "SERVER_PASSWORD": "",
            "MAX_PLAYERS": 80,
            "RCON_PASSWORD": "change-me",
        },
        "volume": {"container": "/config"},
    },
    "eco": {
        "display_name": "Eco",
        "summary": "Collaborative civilization builder with an economy and laws.",
        "notes": "Back up the world regularly; single TCP/UDP pair.",
        "default_name": "eco",
        "image": "fr34kyn01535/eco-server:latest",
        "ports": [
            {"container": 3000, "protocol": "tcp"},
            {"container": 3001, "protocol": "udp"},
        ],
        "env": {
            "SERVER_NAME": "Eco Server",
            "SERVER_PASSWORD": "",
        },
        "volume": {"container": "/config"},
    },
    "space_engineers": {
        "display_name": "Space Engineers",
        "summary": "Voxel engineering sandbox with dedicated server support.",
        "notes": "Game port defaults to 27016; keep UDP forwarded.",
        "default_name": "space-engineers",
        "image": "devidian/spaceengineers:latest",
        "ports": [
            {"container": 27016, "protocol": "udp"},
            {"container": 27016, "protocol": "tcp"},
        ],
        "env": {
            "SERVER_NAME": "Space Engineers Server",
            "WORLD_NAME": "SE World",
            "MAX_PLAYERS": 16,
        },
        "volume": {"container": "/config"},
    },
    "left4dead2": {
        "display_name": "Left 4 Dead 2",
        "summary": "Co-op zombie shooter dedicated server.",
        "notes": "Set RCON and sv_password if public; uses Source ports.",
        "default_name": "l4d2",
        "image": "sourceservers/left4dead2:latest",
        "ports": [
            {"container": 27015, "protocol": "udp"},
            {"container": 27015, "protocol": "tcp"},
        ],
        "env": {
            "HOSTNAME": "L4D2 Server",
            "RCON_PASSWORD": "change-me",
            "SV_PASSWORD": "",
        },
        "volume": {"container": "/config"},
    },
    "terraria": {
        "display_name": "Terraria (Vanilla)",
        "summary": "Vanilla dedicated Terraria server.",
        "notes": "Single TCP port; for mods use tModLoader entry.",
        "default_name": "terraria",
        "image": "ghcr.io/beardedio/terraria:latest",
        "ports": [
            {"container": 7777, "protocol": "tcp"},
        ],
        "env": {
            "WORLD_NAME": "Dedicated",
            "MAX_PLAYERS": 8,
            "PASSWORD": "",
        },
        "volume": {"container": "/config"},
    },
    "stormworks": {
        "display_name": "Stormworks",
        "summary": "Search and rescue sandbox with vehicle building.",
        "notes": "Set RCON password; query uses RCON port.",
        "default_name": "stormworks",
        "image": "bensonjohnson/swserver:latest",
        "ports": [
            {"container": 25564, "protocol": "udp"},
            {"container": 25575, "protocol": "tcp"},
        ],
        "env": {
            "SERVER_NAME": "Stormworks Server",
            "SERVER_PASSWORD": "",
            "RCON_PASSWORD": "change-me",
            "MAX_PLAYERS": 32,
        },
        "volume": {"container": "/config"},
    },
    "unturned": {
        "display_name": "Unturned",
        "summary": "Free-to-play zombie survival with Steam networking.",
        "notes": "Uses game and query on adjacent ports; set a password for public servers.",
        "default_name": "unturned",
        "image": "imperialplugins/unturned:latest",
        "ports": [
            {"container": 27015, "protocol": "udp"},
            {"container": 27015, "protocol": "tcp"},
            {"container": 27016, "protocol": "udp"},
        ],
        "env": {
            "SERVER_NAME": "Unturned Server",
            "SERVER_PASSWORD": "",
            "PORT": 27015,
        },
        "volume": {"container": "/config"},
    },
    "arma3": {
        "display_name": "Arma 3",
        "summary": "Military sandbox with Zeus and mod support.",
        "notes": "Ports 2302-2305 UDP required; set admin password for RCON/Zeus.",
        "default_name": "arma3",
        "image": "wilkesystems/arma3:latest",
        "ports": [
            {"container": 2302, "protocol": "udp"},
            {"container": 2303, "protocol": "udp"},
            {"container": 2304, "protocol": "udp"},
            {"container": 2305, "protocol": "udp"},
        ],
        "env": {
            "HOSTNAME": "Arma 3 Server",
            "PASSWORD": "",
            "ADMINPASSWORD": "change-me",
            "MAX_PLAYERS": 64,
        },
        "volume": {"container": "/config"},
    },
    "garrys_mod": {
        "display_name": "Garry's Mod",
        "summary": "Sandbox Source server with workshop support.",
        "notes": "Add a GSLT for public listing; set RCON and server password if needed.",
        "default_name": "gmod",
        "image": "hackebein/garrysmod:latest",
        "ports": [
            {"container": 27015, "protocol": "udp"},
            {"container": 27015, "protocol": "tcp"},
            {"container": 27005, "protocol": "udp"},
        ],
        "env": {
            "HOSTNAME": "Garrys Mod Server",
            "RCON_PASSWORD": "change-me",
            "SV_PASSWORD": "",
            "MAX_PLAYERS": 32,
        },
        "volume": {"container": "/config"},
    },
    "insurgency_sandstorm": {
        "display_name": "Insurgency: Sandstorm",
        "summary": "Co-op and PvP tactical shooter dedicated server.",
        "notes": "Forward both game and query UDP ports; set admin password.",
        "default_name": "sandstorm",
        "image": "knobby/sandstorm:latest",
        "ports": [
            {"container": 27102, "protocol": "udp"},
            {"container": 27131, "protocol": "udp"},
            {"container": 27015, "protocol": "tcp"},
        ],
        "env": {
            "SERVER_NAME": "Sandstorm Server",
            "ADMIN_PASSWORD": "change-me",
            "MAX_PLAYERS": 28,
        },
        "volume": {"container": "/config"},
    },
    "killing_floor_2": {
        "display_name": "Killing Floor 2",
        "summary": "Co-op horde shooter with webadmin.",
        "notes": "Forward 7777/udp and 27015/udp plus 8080/tcp for webadmin; set a strong web password.",
        "default_name": "kf2",
        "image": "gameservers/kf2:latest",
        "ports": [
            {"container": 7777, "protocol": "udp"},
            {"container": 27015, "protocol": "udp"},
            {"container": 8080, "protocol": "tcp"},
        ],
        "env": {
            "SERVER_NAME": "Killing Floor 2 Server",
            "GAME_PORT": 7777,
            "QUERY_PORT": 27015,
            "WEB_ADMIN_PASSWORD": "change-me",
        },
        "volume": {"container": "/config"},
    },
    "mordhau": {
        "display_name": "Mordhau",
        "summary": "Medieval melee brawler dedicated server.",
        "notes": "RCON shares 27015; set server and admin passwords.",
        "default_name": "mordhau",
        "image": "cm2network/mordhau:latest",
        "ports": [
            {"container": 7777, "protocol": "udp"},
            {"container": 27015, "protocol": "udp"},
            {"container": 27015, "protocol": "tcp"},
        ],
        "env": {
            "SERVER_NAME": "Mordhau Server",
            "SERVER_PASSWORD": "",
            "ADMIN_PASSWORD": "change-me",
            "MAX_PLAYERS": 48,
        },
        "volume": {"container": "/config"},
    },
    "tf2": {
        "display_name": "Team Fortress 2",
        "summary": "Source-engine TF2 dedicated server.",
        "notes": "Add a GSLT for public servers; set RCON and server password.",
        "default_name": "tf2",
        "image": "cm2network/tf2:latest",
        "ports": [
            {"container": 27015, "protocol": "udp"},
            {"container": 27015, "protocol": "tcp"},
        ],
        "env": {
            "HOSTNAME": "TF2 Server",
            "RCON_PASSWORD": "change-me",
            "SV_PASSWORD": "",
            "MAXPLAYERS": 24,
        },
        "volume": {"container": "/config"},
    },
    "vrising": {
        "display_name": "V Rising",
        "summary": "Vampire survival action RPG with dedicated server.",
        "notes": "Query is game+1; keep both UDP ports forwarded.",
        "default_name": "vrising",
        "image": "trueosiris/vrising:latest",
        "ports": [
            {"container": 9876, "protocol": "udp"},
            {"container": 9877, "protocol": "udp"},
        ],
        "env": {
            "SERVER_NAME": "V Rising Server",
            "SERVER_PASSWORD": "",
            "ADMIN_PASSWORD": "change-me",
        },
        "volume": {"container": "/config"},
    },
}


def _load_additional_catalog() -> dict[str, dict]:
    extra_root = Path(__file__).resolve().parent / "data" / "steam_games"
    if not extra_root.exists() or not extra_root.is_dir():
        return {}

    merged: dict[str, dict] = {}
    for entry in sorted(extra_root.glob("*.json")):
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                for slug, meta in payload.items():
                    if isinstance(slug, str) and isinstance(meta, dict):
                        merged[slug.lower()] = meta
        except Exception:
            # Ignore bad files but keep loading the rest.
            continue
    return merged


STEAM_GAMES = {slug: meta for slug, meta in BASE_STEAM_GAMES.items()}
for slug, meta in _load_additional_catalog().items():
    STEAM_GAMES[slug] = meta
