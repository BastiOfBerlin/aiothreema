"""Unit tests for key-pair helpers."""

from __future__ import annotations

from aiothreema import derive_public_key, generate_key_pair


def test_generate_key_pair() -> None:
    """Test that generate_key_pair returns a consistent hex-encoded key pair."""
    private_hex, public_hex = generate_key_pair()

    assert len(private_hex) == 64
    assert len(public_hex) == 64

    # Should parse as valid hex
    bytes.fromhex(private_hex)
    bytes.fromhex(public_hex)

    assert derive_public_key(private_hex) == public_hex


def test_generate_key_pair_is_random() -> None:
    """Test that successive calls produce different key pairs."""
    private_hex_1, _ = generate_key_pair()
    private_hex_2, _ = generate_key_pair()
    assert private_hex_1 != private_hex_2
