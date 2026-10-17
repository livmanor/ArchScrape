"""
scraper/validator.py — URL validation and SSRF protection.

Rejects:
- Non-HTTP(S) schemes
- Localhost / loopback addresses
- Private RFC-1918 and link-local ranges
- Unresolvable hostnames
- Overly long or malformed URLs
"""

import ipaddress
import logging
import re
import socket
import urllib.parse

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_URL_LEN = 2048

# Private / reserved IP ranges that must never be fetched (SSRF protection)
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("169.254.0.0/16"),   # link-local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),    # shared address space (RFC 6598)
    ipaddress.ip_network("192.0.2.0/24"),     # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3
]

_BLOCKED_HOSTNAMES = {
    "localhost", "metadata.google.internal",
    "instance-data", "169.254.169.254",
}


class URLValidationError(ValueError):
    """Raised when a URL fails security or format validation."""


def _is_private_ip(address: str) -> bool:
    """Return True if address resolves to a private/reserved range."""
    try:
        ip = ipaddress.ip_address(address)
        return any(ip in net for net in _PRIVATE_NETS)
    except ValueError:
        return False


def validate_url(url: str, *, resolve_ip: bool = True) -> str:
    """
    Validate and normalise a URL.

    Parameters
    ----------
    url:        Raw URL string from user input or CSV.
    resolve_ip: If True, resolve the hostname and block private addresses.
                Set to False in unit-tests where DNS is not available.

    Returns
    -------
    Normalised URL string (scheme lowercased, fragment removed).

    Raises
    ------
    URLValidationError on any security or format violation.
    """
    if not isinstance(url, str) or not url.strip():
        raise URLValidationError("URL must be a non-empty string.")

    url = url.strip()
    if len(url) > _MAX_URL_LEN:
        raise URLValidationError(f"URL exceeds maximum length of {_MAX_URL_LEN} characters.")

    parsed = urllib.parse.urlparse(url)

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise URLValidationError(
            f"Disallowed scheme '{parsed.scheme}'. Only http and https are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL has no hostname.")

    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise URLValidationError(f"Blocked hostname: {hostname}")

    # Check whether the hostname is already an IP literal
    if _is_private_ip(hostname):
        raise URLValidationError(f"IP address '{hostname}' is in a private/reserved range.")

    # Resolve hostname to IP and re-check
    if resolve_ip:
        try:
            resolved_ip = socket.gethostbyname(hostname)
        except socket.gaierror as exc:
            raise URLValidationError(f"Cannot resolve hostname '{hostname}': {exc}") from exc

        if _is_private_ip(resolved_ip):
            raise URLValidationError(
                f"Hostname '{hostname}' resolves to private IP '{resolved_ip}'."
            )

    # Strip fragment (not needed for scraping, avoids cache mismatches)
    clean = urllib.parse.urlunparse(parsed._replace(scheme=parsed.scheme.lower(), fragment=""))
    return clean


def normalise_domain(url: str) -> str:
    """
    Extract a canonical domain key from a URL for deduplication.
    Strips www. prefix and lowercases.
    """
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    host = re.sub(r"^www\.", "", host.lower())
    return host


def is_valid_email(email: str) -> bool:
    """Lightweight syntactic email check (not RFC 5322 complete)."""
    pattern = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
    return bool(pattern.match(email.strip())) if email else False


def is_valid_phone(phone: str) -> bool:
    """
    Check if string looks like a phone number with at least 7 digits.
    Accepts Indian mobile (+91...) and landline patterns.
    """
    digits = re.sub(r"[\s\-().+]", "", phone)
    return 7 <= len(digits) <= 15 and digits.lstrip("+").isdigit()
