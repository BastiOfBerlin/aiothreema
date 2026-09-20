"""Key-pair helpers for Threema Gateway end-to-end encryption."""

from __future__ import annotations

import nacl.public


def generate_key_pair() -> tuple[str, str]:
    """Generate a new NaCl key pair for end-to-end encryption.

    Returns a tuple of (private_key, public_key) as hex-encoded strings.
    """
    private_key = nacl.public.PrivateKey.generate()
    return private_key.encode().hex(), private_key.public_key.encode().hex()


def derive_public_key(private_key_hex: str) -> str:
    """Derive the hex-encoded public key matching a hex-encoded private key."""
    private_key = nacl.public.PrivateKey(bytes.fromhex(private_key_hex))
    return private_key.public_key.encode().hex()
