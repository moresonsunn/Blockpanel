import os
from pathlib import Path
import importlib
import sys

# Ensure import path works whether running from repo root or backend cwd
here = Path(__file__).resolve()
repo_root = here.parent.parent
backend_dir = here.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

modpack_routes = importlib.import_module('modpack_routes')


def test_purge_moves_known_client_only(tmp_path: Path):
    target = tmp_path
    mods_dir = target / 'mods'
    mods_dir.mkdir(parents=True, exist_ok=True)

    # Create a mix of client-only and server-safe jars
    client_only = [
        'oculus-1.6.9.jar',
        'iris-mc1.21.1-1.7.2.jar',
        'replaymod-1.21.1-2.6.15.jar',
        'dynamic-fps-3.5.2.jar',
        'sodium-fabric-mc1.21-0.6.0.jar',
        'embeddium-1.21.1-0.3.12.jar',
        'xaeros-world-map-1.37.8.jar',
        'Xaeros_Minimap_24.3.1.jar',
        'reeses_sodium_options-1.7.2.jar',
        'lambdynamiclights-2.3.2.jar',
        'betterf3-7.0.0.jar',
        'particular-1.0.0.jar',
        'itemphysiclite-1.0.0.jar',
        'Framework-1.20.1-0.6.17.jar',
    ]
    server_ok = [
        'flywheel-1.21.1-0.6.12.jar',
        'create-1.21.1-0.6.1.jar',
        'jei-19.20.0.jar',
    ]

    for name in client_only + server_ok:
        (mods_dir / name).write_text('x', encoding='utf-8')

    # Run purge
    moved = []
    def capture(ev):
        if isinstance(ev, dict) and ev.get('type') == 'progress' and 'Moved client-only mod' in ev.get('message', ''):
            moved.append(ev.get('message'))

    modpack_routes._purge_client_only_mods(target, push_event=capture)

    # Verify moved files are no longer in mods/ but present in mods-disabled-client/
    disabled = target / 'mods-disabled-client'
    assert disabled.is_dir()

    for name in client_only:
        assert not (mods_dir / name).exists(), f"Client-only {name} should be moved"
        assert (disabled / name).exists(), f"Client-only {name} should be in disabled folder"

    for name in server_ok:
        assert (mods_dir / name).exists(), f"Server-safe {name} should remain in mods"
