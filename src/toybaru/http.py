"""Shared HTTP client factory with IPv4-only transport.

Some DNS setups (e.g. pihole + IPv6) cause AAAA lookups to fail while A records
work fine. We force IPv4 via httpcore's local_address="0.0.0.0" to avoid this.
"""

import httpx
import httpcore


def make_client(timeout: int = 30, follow_redirects: bool = True) -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    return httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=follow_redirects,
    )
