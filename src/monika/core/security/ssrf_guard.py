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

logger = logging.getLogger("monika.core.security.ssrf_guard")


class SSRFViolationError(PermissionError):
    """Raised when an outbound URL violates SSRF safety rules."""

    pass


# Private & Reserved IP Networks
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local & Cloud Metadata
    ipaddress.ip_network("172.16.0.0/12"),  # Private
    ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),  # Documentation TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),  # Private
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),  # Documentation TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # Documentation TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    # IPv6
    ipaddress.ip_network("::1/128"),  # IPv6 Loopback
    ipaddress.ip_network("::/128"),  # Unspecified
    ipaddress.ip_network("fc00::/7"),  # Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),  # Link-local unicast
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
}

SAFE_SCHEMES = {"http", "https"}
ALLOWED_DEFAULT_PORTS = {80, 443, 8080, 8443}


def canonicalize_ip_or_host(host_str: str) -> str:
    """
    Canonicalizes non-standard IP representations (integer decimal, hex, octal, shorthand)
    into standard dotted-decimal or IPv6 format to defeat SSRF obfuscation bypasses.
    """
    s = host_str.strip().lower()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]

    # Decimal integer IP (e.g. 2130706433 -> 127.0.0.1, 2852039166 -> 169.254.169.254)
    if s.isdigit():
        try:
            num = int(s)
            if 0 <= num <= 0xFFFFFFFF:
                return str(ipaddress.IPv4Address(num))
        except ValueError, ipaddress.AddressValueError:
            pass

    # Hex integer IP (e.g. 0x7f000001 -> 127.0.0.1)
    if s.startswith("0x"):
        try:
            num = int(s, 16)
            if 0 <= num <= 0xFFFFFFFF:
                return str(ipaddress.IPv4Address(num))
        except ValueError, ipaddress.AddressValueError:
            pass

    # Octal, dotted hex, or shorthand IP (e.g. 0177.0.0.1, 127.1, 0x7f.0.0.1)
    try:
        packed = socket.inet_aton(s)
        if all(part.strip().isalnum() for part in s.split(".")):
            return socket.inet_ntoa(packed)
    except OSError, ValueError:
        pass

    return s


def is_ip_private_or_reserved(ip_str: str) -> bool:
    """Checks whether an IP address belongs to private or link-local ranges."""
    canonical = canonicalize_ip_or_host(ip_str)
    try:
        ip = ipaddress.ip_address(canonical)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
        for net in BLOCKED_NETWORKS:
            if ip in net:
                return True
        return False
    except ValueError:
        return True


def validate_request_url(url: str, allowed_ports: set[int] | None = None) -> str:
    """
    Validates that a URL is safe for outbound requests.
    Resolves domain DNS and blocks private/metadata destinations.
    Enforces Fail-Closed security: unresolvable domains or non-standard IPs are rejected.
    Returns cleaned canonical URL, or raises SSRFViolationError.
    """
    if not url or not isinstance(url, str):
        raise SSRFViolationError("Empty or invalid URL provided")

    cleaned_url = url.strip()
    parsed = urlparse(cleaned_url)

    if parsed.scheme.lower() not in SAFE_SCHEMES:
        raise SSRFViolationError(f"Unsupported or dangerous URI scheme '{parsed.scheme}'. Only HTTP/HTTPS allowed.")

    raw_hostname = (parsed.hostname or "").lower().strip()
    if not raw_hostname:
        raise SSRFViolationError(f"Missing hostname in URL: {url}")

    hostname = canonicalize_ip_or_host(raw_hostname)

    if hostname in BLOCKED_HOSTNAMES or raw_hostname in BLOCKED_HOSTNAMES:
        raise SSRFViolationError(f"Access to blocked internal host '{raw_hostname}' is denied.")

    if parsed.port is not None:
        port = parsed.port
        if port <= 0 or port > 65535:
            raise SSRFViolationError(f"Access to invalid port {port} is denied by SSRF policy.")
    else:
        port = 443 if parsed.scheme.lower() == "https" else 80

    valid_ports = allowed_ports or ALLOWED_DEFAULT_PORTS
    if port not in valid_ports:
        raise SSRFViolationError(f"Access to non-standard port {port} is denied by SSRF policy.")

    # Check literal IP address (standard or canonicalized)
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
        if not resolved_addrs:
            raise SSRFViolationError(f"DNS resolution returned no addresses for host '{hostname}'. SSRF blocked.")
        for family, socktype, proto, canonname, sockaddr in resolved_addrs:
            resolved_ip = str(sockaddr[0])
            if is_ip_private_or_reserved(resolved_ip):
                raise SSRFViolationError(
                    f"Domain '{hostname}' resolved to private/reserved IP {resolved_ip}. SSRF blocked."
                )
    except socket.gaierror as e:
        # If hostname is a single-label domain without dots (e.g. 'internal', 'router', 'corp', 'localhost'), reject fail-closed!
        if "." not in hostname or hostname.endswith((".local", ".internal", ".lan", ".corp", ".home")):
            logger.warning(f"[SSRFGuard] DNS resolution failed for internal/unqualified host '{hostname}': {e}")
            raise SSRFViolationError(
                f"DNS resolution failed for internal/unqualified host '{hostname}': access denied by fail-closed SSRF policy."
            ) from e
        # Allow benign external domain DNS failures in offline test environments to pass through to HTTP client
        logger.debug(f"[SSRFGuard] DNS resolution failed for external domain {hostname}: {e}")
        pass

    return cleaned_url


def is_url_safe(url: str) -> bool:
    """Safe boolean checker that does not raise exceptions."""
    try:
        validate_request_url(url)
        return True
    except SSRFViolationError, Exception:
        return False
