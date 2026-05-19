from __future__ import annotations

import ssl

import certifi


def httpx_ssl_verify() -> ssl.SSLContext | str:
    """Use OS trust store on Windows; fall back to certifi elsewhere."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return certifi.where()
