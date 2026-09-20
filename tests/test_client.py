"""Unit tests for ThreemaGatewayClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import nacl.public
import pytest

from aiothreema import (
    ThreemaAuthError,
    ThreemaConnectionError,
    ThreemaGatewayClient,
    ThreemaSendError,
)

MOCK_GATEWAY_ID = "*TESTGWY"
MOCK_API_SECRET = "test_secret_key_12345"


def _make_resp(status: int = 200, text: str = "OK") -> MagicMock:
    """Create a mock aiohttp response."""
    resp = MagicMock()
    resp.status = status
    resp.ok = status < 400
    resp.text = AsyncMock(return_value=text)
    return resp


def _make_session(
    get_resp: MagicMock | None = None,
    post_resp: MagicMock | None = None,
) -> MagicMock:
    """Create a mock aiohttp client session."""
    session = MagicMock()
    session.get = AsyncMock(return_value=get_resp)
    session.post = AsyncMock(return_value=post_resp)
    return session


# ── validate_credentials ─────────────────────────────────────────────────


async def test_validate_credentials_success() -> None:
    """Test successful credential validation."""
    session = _make_session(get_resp=_make_resp(200, "100"))
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session)
    await client.validate_credentials()
    session.get.assert_awaited_once_with(
        "https://msgapi.threema.ch/credits",
        params={"from": MOCK_GATEWAY_ID, "secret": MOCK_API_SECRET},
    )


async def test_validate_credentials_auth_error() -> None:
    """Test that 401 raises ThreemaAuthError."""
    session = _make_session(get_resp=_make_resp(401))
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session)
    with pytest.raises(ThreemaAuthError):
        await client.validate_credentials()


async def test_validate_credentials_server_error() -> None:
    """Test that non-401 HTTP error raises ThreemaConnectionError."""
    session = _make_session(get_resp=_make_resp(500))
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session)
    with pytest.raises(ThreemaConnectionError):
        await client.validate_credentials()


@pytest.mark.parametrize(
    "side_effect",
    [aiohttp.ClientError("connection reset"), TimeoutError()],
    ids=["client_error", "timeout"],
)
async def test_validate_credentials_connection_error(side_effect: Exception) -> None:
    """Test that a connection error or timeout raises ThreemaConnectionError."""
    session = MagicMock()
    session.get = AsyncMock(side_effect=side_effect)
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session)
    with pytest.raises(ThreemaConnectionError):
        await client.validate_credentials()


@pytest.mark.parametrize(
    "side_effect",
    [aiohttp.ClientPayloadError("connection dropped"), TimeoutError()],
    ids=["payload_error", "timeout"],
)
async def test_validate_credentials_read_error(side_effect: Exception) -> None:
    """Test a failure reading the validation response raises ThreemaConnectionError."""
    resp = _make_resp(200)
    resp.text = AsyncMock(side_effect=side_effect)
    session = _make_session(get_resp=resp)
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session)
    with pytest.raises(ThreemaConnectionError):
        await client.validate_credentials()


# ── send_text_message: simple mode ───────────────────────────────────────


async def test_send_simple_success() -> None:
    """Test successful simple message send."""
    session = _make_session(post_resp=_make_resp(200, "msg123"))
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session)
    message_id = await client.send_text_message("ABCD1234", "Hello!")
    assert message_id == "msg123"
    session.post.assert_awaited_once_with(
        "https://msgapi.threema.ch/send_simple",
        data={
            "from": MOCK_GATEWAY_ID,
            "to": "ABCD1234",
            "secret": MOCK_API_SECRET,
            "text": "Hello!",
        },
    )


async def test_send_simple_auth_error() -> None:
    """Test that 401 during simple send raises ThreemaAuthError."""
    session = _make_session(post_resp=_make_resp(401))
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session)
    with pytest.raises(ThreemaAuthError):
        await client.send_text_message("ABCD1234", "Hello!")


async def test_send_simple_server_error() -> None:
    """Test that non-401 HTTP error during simple send raises ThreemaSendError."""
    session = _make_session(post_resp=_make_resp(500))
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session)
    with pytest.raises(ThreemaSendError):
        await client.send_text_message("ABCD1234", "Hello!")


@pytest.mark.parametrize(
    "side_effect",
    [aiohttp.ClientError("connection reset"), TimeoutError()],
    ids=["client_error", "timeout"],
)
async def test_send_simple_connection_error(side_effect: Exception) -> None:
    """Test a connection error or timeout during simple send raises ThreemaSendError."""
    session = MagicMock()
    session.post = AsyncMock(side_effect=side_effect)
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session)
    with pytest.raises(ThreemaSendError):
        await client.send_text_message("ABCD1234", "Hello!")


@pytest.mark.parametrize(
    "side_effect",
    [aiohttp.ClientPayloadError("connection dropped"), TimeoutError()],
    ids=["payload_error", "timeout"],
)
async def test_send_simple_read_error(side_effect: Exception) -> None:
    """Test a failure reading the send response raises ThreemaSendError."""
    resp = _make_resp(200)
    resp.text = AsyncMock(side_effect=side_effect)
    session = _make_session(post_resp=resp)
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session)
    with pytest.raises(ThreemaSendError):
        await client.send_text_message("ABCD1234", "Hello!")


# ── send_text_message: E2E mode ──────────────────────────────────────────


def _e2e_keys() -> tuple[str, nacl.public.PrivateKey]:
    """Return (sender_private_hex, recipient_private_key) for E2E tests."""
    sender = nacl.public.PrivateKey.generate()
    recipient = nacl.public.PrivateKey.generate()
    return bytes(sender).hex(), recipient


async def test_send_e2e_success() -> None:
    """Test a successful E2E encrypted message send round-trips correctly."""
    sender_hex, recipient_priv = _e2e_keys()
    pub_hex = bytes(recipient_priv.public_key).hex()

    session = MagicMock()
    session.get = AsyncMock(return_value=_make_resp(200, pub_hex))
    session.post = AsyncMock(return_value=_make_resp(200, "msg456"))

    client = ThreemaGatewayClient(
        MOCK_GATEWAY_ID, MOCK_API_SECRET, private_key=sender_hex, session=session
    )
    message_id = await client.send_text_message("ABCD1234", "Hello E2E!")

    assert message_id == "msg456"
    session.get.assert_awaited_once()
    session.post.assert_awaited_once()

    # Decrypt the posted payload and verify it round-trips to the original text.
    _, kwargs = session.post.call_args
    nonce = bytes.fromhex(kwargs["data"]["nonce"])
    box_bytes = bytes.fromhex(kwargs["data"]["box"])
    sender_pub = nacl.public.PrivateKey(bytes.fromhex(sender_hex)).public_key
    decrypt_box = nacl.public.Box(recipient_priv, sender_pub)
    plaintext = decrypt_box.decrypt(box_bytes, nonce)

    msg_type = plaintext[0]
    assert msg_type == 0x01
    padding_length = plaintext[-1]
    text_bytes = plaintext[1:-padding_length]
    assert text_bytes.decode("utf-8") == "Hello E2E!"


async def test_send_e2e_pubkey_not_found() -> None:
    """Test that a 404 fetching pubkey raises ThreemaSendError."""
    sender_hex, _ = _e2e_keys()
    session = MagicMock()
    session.get = AsyncMock(return_value=_make_resp(404))

    client = ThreemaGatewayClient(
        MOCK_GATEWAY_ID, MOCK_API_SECRET, private_key=sender_hex, session=session
    )
    with pytest.raises(ThreemaSendError):
        await client.send_text_message("ABCD1234", "Hello E2E!")


async def test_send_e2e_pubkey_auth_error() -> None:
    """Test that 401 fetching pubkey raises ThreemaAuthError."""
    sender_hex, _ = _e2e_keys()
    session = MagicMock()
    session.get = AsyncMock(return_value=_make_resp(401))

    client = ThreemaGatewayClient(
        MOCK_GATEWAY_ID, MOCK_API_SECRET, private_key=sender_hex, session=session
    )
    with pytest.raises(ThreemaAuthError):
        await client.send_text_message("ABCD1234", "Hello E2E!")


async def test_send_e2e_pubkey_malformed() -> None:
    """Test that a malformed pubkey response raises ThreemaSendError."""
    sender_hex, _ = _e2e_keys()
    session = MagicMock()
    session.get = AsyncMock(return_value=_make_resp(200, "not-hex-and-wrong-length"))

    client = ThreemaGatewayClient(
        MOCK_GATEWAY_ID, MOCK_API_SECRET, private_key=sender_hex, session=session
    )
    with pytest.raises(ThreemaSendError):
        await client.send_text_message("ABCD1234", "Hello E2E!")


@pytest.mark.parametrize(
    "side_effect",
    [aiohttp.ClientError("connection reset"), TimeoutError()],
    ids=["client_error", "timeout"],
)
async def test_send_e2e_pubkey_connection_error(side_effect: Exception) -> None:
    """Test a connection error or timeout fetching pubkey raises ThreemaSendError."""
    sender_hex, _ = _e2e_keys()
    session = MagicMock()
    session.get = AsyncMock(side_effect=side_effect)

    client = ThreemaGatewayClient(
        MOCK_GATEWAY_ID, MOCK_API_SECRET, private_key=sender_hex, session=session
    )
    with pytest.raises(ThreemaSendError):
        await client.send_text_message("ABCD1234", "Hello E2E!")


@pytest.mark.parametrize(
    "side_effect",
    [aiohttp.ClientPayloadError("connection dropped"), TimeoutError()],
    ids=["payload_error", "timeout"],
)
async def test_send_e2e_pubkey_read_error(side_effect: Exception) -> None:
    """Test a failure reading the pubkey response raises ThreemaSendError."""
    sender_hex, _ = _e2e_keys()
    resp = _make_resp(200)
    resp.text = AsyncMock(side_effect=side_effect)
    session = MagicMock()
    session.get = AsyncMock(return_value=resp)

    client = ThreemaGatewayClient(
        MOCK_GATEWAY_ID, MOCK_API_SECRET, private_key=sender_hex, session=session
    )
    with pytest.raises(ThreemaSendError):
        await client.send_text_message("ABCD1234", "Hello E2E!")


@pytest.mark.parametrize(
    "side_effect",
    [aiohttp.ClientError("connection reset"), TimeoutError()],
    ids=["client_error", "timeout"],
)
async def test_send_e2e_post_connection_error(side_effect: Exception) -> None:
    """Test that a connection error or timeout on POST raises ThreemaSendError."""
    sender_hex, recipient_priv = _e2e_keys()
    pub_hex = bytes(recipient_priv.public_key).hex()

    session = MagicMock()
    session.get = AsyncMock(return_value=_make_resp(200, pub_hex))
    session.post = AsyncMock(side_effect=side_effect)

    client = ThreemaGatewayClient(
        MOCK_GATEWAY_ID, MOCK_API_SECRET, private_key=sender_hex, session=session
    )
    with pytest.raises(ThreemaSendError):
        await client.send_text_message("ABCD1234", "Hello E2E!")


# ── session lifecycle ─────────────────────────────────────────────────────


async def test_no_session_raises_without_context_manager() -> None:
    """Test using the client without a session or context manager raises."""
    client = ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET)
    with pytest.raises(RuntimeError):
        await client.validate_credentials()


async def test_context_manager_creates_and_closes_owned_session() -> None:
    """Test the client creates and closes its own session as a context manager."""
    async with ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET) as client:
        assert client._session is not None
        assert not client._session.closed
    assert client._session.closed


async def test_context_manager_does_not_close_supplied_session() -> None:
    """Test an externally supplied session is left open after the context exits."""
    session = _make_session()
    async with ThreemaGatewayClient(MOCK_GATEWAY_ID, MOCK_API_SECRET, session=session):
        pass
    session.close.assert_not_called()
