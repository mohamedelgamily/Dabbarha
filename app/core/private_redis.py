"""TLS Redis connections pinned to freshly resolved, explicitly allowed private IPs."""
from __future__ import annotations

import ipaddress
import socket
import time

import dns.exception
import dns.resolver
from redis.connection import SSLConnection


_PRIVATE_NETWORKS = tuple(map(ipaddress.ip_network, (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7",
)))


def parse_private_cidrs(raw: str) -> tuple[str, ...]:
    """Parse narrow RFC1918/ULA allowlists; never accept public or loopback CIDRs."""
    if not raw.strip():
        raise ValueError("private Redis CIDR allowlist is required")
    result: list[str] = []
    for part in raw.split(","):
        try:
            network = ipaddress.ip_network(part.strip(), strict=True)
        except ValueError:
            raise ValueError("invalid private Redis CIDR allowlist") from None
        minimum_prefix = 16 if network.version == 4 else 48
        if (network.prefixlen < minimum_prefix
                or not any(network.subnet_of(private) for private in _PRIVATE_NETWORKS)):
            raise ValueError("Redis CIDRs must be narrow RFC1918 or IPv6 ULA networks")
        canonical = str(network)
        if canonical in result:
            raise ValueError("duplicate Redis CIDR")
        result.append(canonical)
    return tuple(result)


def is_dns_hostname(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    if not host or len(host) > 253 or host.endswith("."):
        return False
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    labels = ascii_host.split(".")
    if len(labels) < 2 or labels[-1] == "localhost":
        return False
    return all(
        1 <= len(label) <= 63
        and label[0].isalnum()
        and label[-1].isalnum()
        and all(char.isalnum() or char == "-" for char in label)
        for label in labels
    )


def is_private_network_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Accept only RFC1918/ULA addresses, rather than Python's broader is_private set."""
    return any(address.version == network.version and address in network for network in _PRIVATE_NETWORKS)


def resolve_allowed_private_addresses(host: str, cidrs: tuple[str, ...], timeout: float) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    """Resolve A/AAAA with a deadline and reject the whole answer if any IP is outside the allowlist."""
    networks = tuple(ipaddress.ip_network(value) for value in cidrs)
    resolver = dns.resolver.Resolver(configure=True)
    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    deadline = time.monotonic() + timeout
    try:
        for record_type in ("A", "AAAA"):
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise dns.exception.Timeout("private Redis DNS deadline exceeded")
                answer = resolver.resolve(host, record_type, lifetime=remaining, search=False)
            except dns.resolver.NoAnswer:
                continue
            addresses.update(ipaddress.ip_address(record.address) for record in answer)
    except (dns.exception.DNSException, OSError, ValueError):
        raise OSError("private Redis hostname resolution failed") from None
    if not addresses or any(not any(address.version == network.version and address in network for network in networks)
                            for address in addresses):
        raise OSError("private Redis hostname resolved outside its configured network")
    if len(addresses) > 8:
        raise OSError("private Redis hostname returned too many addresses")
    return tuple(sorted(addresses, key=lambda item: (item.version, int(item))))


class PrivateDNSSSLConnection(SSLConnection):
    """Reconnect using only allowed private DNS answers while verifying TLS for the DNS name."""

    def __init__(self, *, allowed_cidrs: tuple[str, ...], dns_timeout: float, **kwargs):
        if kwargs.get("ssl_cert_reqs") != "required" or kwargs.get("ssl_check_hostname") is not True:
            raise ValueError("private Redis DNS requires certificate and hostname verification")
        self.allowed_cidrs = tuple(allowed_cidrs)
        self.dns_timeout = dns_timeout
        super().__init__(**kwargs)

    def _connect(self):
        addresses = resolve_allowed_private_addresses(self.host, self.allowed_cidrs, self.dns_timeout)
        last_error = None
        deadline = time.monotonic() + self.socket_connect_timeout
        for address in addresses:
            family = socket.AF_INET if address.version == 4 else socket.AF_INET6
            sock = None
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("private Redis connection deadline exceeded")
                sock = socket.socket(family, socket.SOCK_STREAM)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                if self.socket_keepalive:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    for option, value in self.socket_keepalive_options.items():
                        sock.setsockopt(socket.IPPROTO_TCP, option, value)
                sock.settimeout(remaining)
                sockaddr = (str(address), self.port) if address.version == 4 else (str(address), self.port, 0, 0)
                sock.connect(sockaddr)
                sock.settimeout(self.socket_timeout)
                return sock
            except OSError as exc:
                last_error = exc
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
        if last_error is not None:
            raise last_error
        raise OSError("private Redis hostname had no usable address")
