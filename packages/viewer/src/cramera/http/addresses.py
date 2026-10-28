"""
The addresses of this machine: the loopback addresses, the wildcard addresses that
listen on every address, and the address other devices of its network reach it at.
"""

from __future__ import annotations

import ipaddress
import socket

from typing_extensions import FrozenSet, Optional

LOOPBACK = "127.0.0.1"
"""
The IPv4 loopback address.
"""

IPV6_LOOPBACK = "::1"
"""
The IPv6 loopback address.
"""

EVERY_ADDRESS = "0.0.0.0"
"""
The address that listens on every IPv4 address of this machine.
"""

WILDCARD_HOSTS: FrozenSet[str] = frozenset({EVERY_ADDRESS, "::", ""})
"""
The addresses that listen on every address of this machine rather than on one.
"""

ROUTE_PROBE = ("192.0.2.1", 9)
"""
An address of the documentation range (RFC 5737) that is never routed: connecting a
datagram socket towards it picks the address of the default route's interface without
sending anything.
"""

# %% addresses


def own_address(address: str) -> str:
    """
    :param address: An IP address as a socket reports it.
    :return: The address as a page names it: an IPv4 address mapped into IPv6 is the
        IPv4 address.
    """
    parsed = ipaddress.ip_address(address)
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        return str(parsed.ipv4_mapped)
    return str(parsed)


def is_loopback(address: str) -> bool:
    """
    :param address: An IP address as a socket reports it.
    :return: Whether it is a loopback address of this machine.
    """
    return ipaddress.ip_address(own_address(address)).is_loopback


def local_host(host: str) -> str:
    """
    :param host: The address a server listens on.
    :return: The address this machine reaches that server at: a wildcard address is
        reached through the loopback address of its family.
    """
    if host not in WILDCARD_HOSTS:
        return host
    return IPV6_LOOPBACK if ":" in host else LOOPBACK


def network_address() -> Optional[str]:
    """
    :return: The IPv4 address of the interface of this machine's default route, the one
        other devices of its network reach it at; None without a network.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        if probe.connect_ex(ROUTE_PROBE) != 0:
            return None
        return probe.getsockname()[0]


def url_of(host: str, port: int) -> str:
    """
    :param host: A host name or IP address.
    :param port: A port.
    :return: The base URL of an HTTP server there; an IPv6 address is bracketed.
    """
    named = f"[{host}]" if ":" in host else host
    return f"http://{named}:{port}"
