import ipaddress
from urllib.parse import urlparse


def is_local_url(base_url: str | None) -> bool:
    """Return whether a URL points to a local or unspecified address."""
    if not base_url:
        return False
    try:
        host = urlparse(base_url).hostname or ""
    except ValueError:
        return False
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified
