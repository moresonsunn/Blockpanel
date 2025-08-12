from typing import List, Protocol

class ServerProvider(Protocol):
    name: str
    def list_versions(self) -> List[str]:
        ...
    def get_download_url(self, version: str) -> str:
        ...

# Providers will be registered here at import time
PROVIDERS = {}

def register_provider(provider: ServerProvider):
    PROVIDERS[provider.name] = provider


def get_provider_names() -> List[str]:
    return list(PROVIDERS.keys())


def get_provider(name: str) -> ServerProvider:
    if name not in PROVIDERS:
        raise ValueError(f"Unknown server type: {name}")
    return PROVIDERS[name]
