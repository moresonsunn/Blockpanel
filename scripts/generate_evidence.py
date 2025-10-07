#!/usr/bin/env python3
"""Generate a release evidence JSON file (similar to Crafty style).

Captures build metadata:
  - version
  - git commit
  - build timestamp (UTC)
  - image reference + digest (if provided)
  - requirements.txt hash
  - platforms (static for now, matches build matrix)
  - selected environment variables for determinism
"""

from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import os

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--version', required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--image', required=True)
    p.add_argument('--digest', default='')
    p.add_argument('--output', required=True)
    args = p.parse_args()

    req_path = Path('backend/requirements.txt')
    req_hash = sha256_file(req_path) if req_path.exists() else None

    evidence = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": args.version,
        "commit": args.commit,
        "image": args.image,
        "image_tags": [args.version, 'latest'],
        "image_digest": args.digest or None,
        "platforms": ["linux/amd64", "linux/arm64"],
        "requirements_sha256": req_hash,
        "env_sample": {
            "APP_VERSION": os.environ.get('APP_VERSION'),
            "GIT_COMMIT": os.environ.get('GIT_COMMIT'),
        },
        "paths": {
            "dockerfile": "docker/controller-unified.Dockerfile",
            "requirements": "backend/requirements.txt"
        }
    }

    out = Path(args.output)
    out.write_text(json.dumps(evidence, indent=2))
    print(f"Wrote evidence to {out}")

if __name__ == '__main__':
    main()
