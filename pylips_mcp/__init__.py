"""pylips-mcp : serveur MCP pour TV Philips (API JointSpace v6)."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pylips-mcp")
except PackageNotFoundError:  # lance depuis le depot sans installation
    __version__ = "dev"
