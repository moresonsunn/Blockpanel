#!/usr/bin/env python3
"""Rebuild the CasaOS custom store archive with current manifests."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


def package_store(destination: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    store_dir = repo_root / "casaos-appstore"
    if not store_dir.exists():
        raise FileNotFoundError(f"Missing store directory: {store_dir}")

    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in store_dir.rglob("*"):
            if path.is_dir():
                continue
            if path.resolve() == destination:
                # Avoid embedding the archive itself when rebuilding in place.
                continue
            archive.write(path, path.relative_to(store_dir))

    return destination


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional destination for the generated zip (defaults to casaos-appstore/lynx.zip).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    destination = args.output or (repo_root / "casaos-appstore" / "lynx.zip")

    archive_path = package_store(destination)
    print(f"Wrote CasaOS store archive to {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
