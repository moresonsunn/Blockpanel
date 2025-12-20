# Lynx CasaOS App Store

This directory provides a self-contained 3rd party CasaOS App Store implementation for Lynx.

Add the raw URL of `index.json` below to CasaOS Custom Sources to install:

```
https://raw.githubusercontent.com/moresonsunn/Lynx/main/casaos-appstore/index.json
```

Alternatively (recommended), attach `lynx.zip` to a GitHub release and use:

```
https://github.com/moresonsunn/Lynx/releases/latest/download/lynx.zip
```

## Structure
```
casaos-appstore/
  index.json            # App catalog index consumed by CasaOS
  Apps/
    lynx/
      docker-compose.yml # CasaOS manifest (compose + x-casaos metadata)
      icon.png (optional, remote icon used instead)
```

## Update Flow
1. Bump manifest metadata (version, images, etc.).
2. Rebuild the zip package:
  ```
  python scripts/package_casaos_store.py
  ```
  3. Commit the manifest and refreshed `lynx.zip`.
4. Tag a release (e.g., `latest`) and push.
5. Refresh the custom source in the CasaOS UI.

## GitHub Release Publishing
1. Push the commit with updated manifests and regenerated archive.
2. Create (or update) a GitHub release tagged `latest`.
3. Ensure the `lynx.zip` asset is attached automatically via the release (GitHub auto-hosts it at `https://github.com/<org>/<repo>/releases/latest/download/lynx.zip`).
4. Use that URL as the CasaOS custom source.

## TODO (future automation)
- CI job to auto-bump version in this index on tag
- SBOM & signature references
- Alternate mirror (GitLab raw)
