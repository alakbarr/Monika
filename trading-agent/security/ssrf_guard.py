# ==============================================================================
# File: security/ssrf_guard.py
# Monika Defensive Shield: Server-Side Request Forgery (SSRF) Guard
# ==============================================================================

"""
SSRF Protection Firewall & DNS Resolver Guard.

Prevents unauthorized requests from Monika's scrapers, RSS feeds,
webhook dispatchers, and web readers to:
1. Internal loopback (127.0.0.1, localhost, ::1)
2. Cloud Instance Metadata Services (169.254.169.254, metadata.google.internal)
3. Private Corporate & Home Subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
4. Non-HTTP protocols (file://, gopher://, dict://, ftp://)
5. Dangerous Ports (SSH 22, Telnet 23, SMTP 25, Redis 6379, Postgres 5432)
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger("TradingAgent.Security.SSRFGuard")


class SSRFViolationError(PermissionError):
    """Raised when an outbound URL violates SSRF safety rules."""
    pass


# Private & Reserved IP Networks
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),     # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local & Cloud Metadata
    ipaddress.ip_network("172.16.0.0/12"),     # Private
    ipaddress.ip_network("192.0.0.0/24"),      # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),      # Documentation TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),    # Private
    ipaddress.ip_network("198.18.0.0/15"),     # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),   # Documentation TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),    # Documentation TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved
    ipaddress.ip_network("255.255.255.255/32"),# Broadcast
    # IPv6
    ipaddress.ip_network("::1/128"),           # IPv6 Loopback
    ipaddress.ip_network("::/128"),            # Unspecified
    ipaddress.ip_network("fc00::/7"),          # Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),         # Link-local unicast
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
}

SAFE_SCHEMES = {"http", "https"}
ALLOWED_DEFAULT_PORTS = {80, 443, 8080, 8443}


def is_ip_private_or_reserved(ip_str: str) -> bool:
    """Checks whether an IP address belongs to private or link-local ranges."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
        for net in BLOCKED_NETWORKS:
            if ip in net:
                return True
        return False
    except ValueError:
        return True


def validate_request_url(url: str, allowed_ports: Optional[Set[int]] = None) -> str:
    """
    Validates that a URL is safe for outbound requests.
    Resolves domain DNS and blocks private/metadata destinations.
    Returns cleaned canonical URL, or raises SSRFViolationError.
    """
    if not url or not isinstance(url, str):
        raise SSRFViolationError("Empty or invalid URL provided")

    cleaned_url = url.strip()
    parsed = urlparse(cleaned_url)

    if parsed.scheme.lower() not in SAFE_SCHEMES:
        raise SSRFViolationError(f"Unsupported or dangerous URI scheme '{parsed.scheme}'. Only HTTP/HTTPS allowed.")

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        raise SSRFViolationError(f"Missing hostname in URL: {url}")

    if hostname in BLOCKED_HOSTNAMES:
        raise SSRFViolationError(f"Access to blocked internal host '{hostname}' is denied.")

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    valid_ports = allowed_ports or ALLOWED_DEFAULT_PORTS
    if port not in valid_ports:
        raise SSRFViolationError(f"Access to non-standard port {port} is denied by SSRF policy.")

    # Check literal IP address
    try:
        ipaddress.ip_address(hostname)
        if is_ip_private_or_reserved(hostname):
            raise SSRFViolationError(f"Access to private/reserved IP {hostname} is blocked.")
        return cleaned_url
    except ValueError:
        # Hostname is a domain name, resolve via DNS
        pass

    try:
        resolved_addrs = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        for family, socktype, proto, canonname, sockaddr in resolved_addrs:
            resolved_ip = sockaddr[0]
            if is_ip_private_or_reserved(resolved_ip):
                raise SSRFViolationError(
                    f"Domain '{hostname}' resolved to private/reserved IP {resolved_ip}. SSRF blocked."
                )
    except socket.gaierror as e:
        logger.debug(f"[SSRFGuard] DNS resolution failed for {hostname}: {e}")
        # Allow benign external DNS failures to be handled by HTTP client
        pass

    return cleaned_url


def is_url_safe(url: str) -> bool:
    """Safe boolean checker that does not raise exceptions."""
    try:
        validate_request_url(url)
        return True
    except (SSRFViolationError, Exception):
        return False
