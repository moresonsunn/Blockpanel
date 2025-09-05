import requests
from typing import List
from .providers import register_provider

API_BASE = "https://api.papermc.io/v2/projects/paper"

class PaperProvider:
    name = "paper"

    def list_versions(self) -> List[str]:
        resp = requests.get(API_BASE, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data.get("versions", [])

    def get_download_url(self, version: str) -> str:
        # Get latest build for the version
        try:
            vresp = requests.get(f"{API_BASE}/versions/{version}", timeout=20)
            vresp.raise_for_status()
            vdata = vresp.json()
            builds = vdata.get("builds", [])
            if not builds:
                raise ValueError(f"No builds found for Paper version {version}")
            build = builds[-1]
            
            # Get build details to find the correct filename
            bresp = requests.get(f"{API_BASE}/versions/{version}/builds/{build}", timeout=20)
            bresp.raise_for_status()
            bdata = bresp.json()
            
            # Extract the correct application filename
            downloads = bdata.get("downloads", {})
            application = downloads.get("application", {})
            filename = application.get("name")
            
            if not filename:
                # Fallback to default naming pattern
                filename = f"paper-{version}-{build}.jar"
            
            return f"{API_BASE}/versions/{version}/builds/{build}/downloads/{filename}"
            
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Failed to get Paper download URL for version {version}: {e}")
        except Exception as e:
            raise ValueError(f"Unexpected error getting Paper download URL for version {version}: {e}")

# Register on import
register_provider(PaperProvider())
