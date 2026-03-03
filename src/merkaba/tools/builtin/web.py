# src/merkaba/tools/builtin/web.py
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from merkaba.tools.base import Tool, PermissionTier

# Blocked hostname patterns (case-insensitive)
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.aws.internal",
}

# Private/internal IP ranges to block (SSRF protection)
BLOCKED_IP_NETWORKS = [
    # IPv4 private ranges
    ipaddress.ip_network("10.0.0.0/8"),  # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),  # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),  # Private Class C
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local (includes AWS metadata)
    ipaddress.ip_network("0.0.0.0/8"),  # "This" network
    # IPv6 equivalents
    ipaddress.ip_network("::1/128"),  # Loopback
    ipaddress.ip_network("fc00::/7"),  # Unique local addresses
    ipaddress.ip_network("fe80::/10"),  # Link-local
]

# Allowed URL schemes
ALLOWED_SCHEMES = {"http", "https"}


def is_url_allowed(url: str) -> tuple[bool, str]:
    """
    Check if a URL is allowed for fetching (SSRF protection).

    Returns:
        tuple[bool, str]: (is_allowed, reason)
            - If allowed: (True, "")
            - If blocked: (False, "reason for blocking")
    """
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL: {e}"

    # Check scheme
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        return False, f"URL scheme '{scheme}' not allowed. Only http and https are permitted."

    # Extract hostname
    hostname = parsed.hostname
    if not hostname:
        return False, "URL has no hostname"

    # Check blocked hostnames (case-insensitive)
    hostname_lower = hostname.lower()
    if hostname_lower in BLOCKED_HOSTNAMES:
        return False, f"Hostname '{hostname}' is blocked"

    # Resolve hostname to IP address
    try:
        ip_str = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_str)
    except socket.gaierror as e:
        return False, f"Could not resolve hostname '{hostname}': {e}"
    except ValueError as e:
        return False, f"Invalid IP address: {e}"

    # Check if IP is in blocked ranges
    for network in BLOCKED_IP_NETWORKS:
        # Handle IPv4/IPv6 mismatch
        if ip.version == network.version and ip in network:
            return False, f"IP address {ip_str} is in blocked range {network}"

    return True, ""


def _web_fetch(url: str) -> str:
    """Fetch content from a URL with SSRF-safe redirect handling."""
    _MAX_REDIRECTS = 5

    # SSRF protection: validate the initial URL before fetching
    allowed, reason = is_url_allowed(url)
    if not allowed:
        raise ValueError(f"URL not allowed: {reason}")

    current_url = url
    hops = 0

    try:
        while True:
            response = httpx.get(current_url, follow_redirects=False, timeout=30.0)

            # Not a redirect — we're done
            if response.status_code not in (301, 302, 303, 307, 308):
                response.raise_for_status()
                return response.text

            # Redirect: validate the Location before following
            hops += 1
            if hops > _MAX_REDIRECTS:
                raise ValueError("Too many redirects")

            location = response.headers.get("location", "")
            if not location:
                raise ValueError("Redirect with no Location header")

            allowed, reason = is_url_allowed(location)
            if not allowed:
                raise ValueError(f"Redirect target blocked: {reason}")

            current_url = location

    except ValueError:
        raise
    except httpx.TimeoutException:
        return "[error] Request timed out"
    except httpx.ConnectError as e:
        return f"[error] Connection failed: {e}"
    except httpx.HTTPStatusError as e:
        return f"[error] HTTP {e.response.status_code}: {e.response.reason_phrase}"


web_fetch = Tool(
    name="web_fetch",
    description="Fetch content from a URL. Returns the page content as text.",
    function=_web_fetch,
    permission_tier=PermissionTier.MODERATE,
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch"}
        },
        "required": ["url"],
    },
)
