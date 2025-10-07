# BlockPanel CasaOS App Store

This directory provides a self-contained 3rd party CasaOS App Store implementation for BlockPanel.

Add the raw URL of `index.json` below to CasaOS Custom Sources to install:

```
https://raw.githubusercontent.com/moresonsunn/minecraft-server/main/casaos-appstore/index.json
```

## Structure
```
casaos-appstore/
  index.json            # App catalog index consumed by CasaOS
  Apps/
    blockpanel/
      app.json          # Detailed BlockPanel app definition
      icon.png (optional, remote icon used instead)
```

## Update Flow
1. Tag a new release (e.g., v0.3.3)
2. Run the helper script (to be added) to regenerate version fields.
3. Commit & push.
4. Refresh custom source in CasaOS UI.

## TODO (future automation)
- CI job to auto-bump version in this index on tag
- SBOM & signature references
- Alternate mirror (GitLab raw)
