"""Async client for the Threema Gateway HTTP API."""

from __future__ import annotations

import logging
import os
from types import TracebackType

import aiohttp
import nacl.public
import nacl.utils

from .exceptions import ThreemaAuthError, ThreemaConnectionError, ThreemaSendError

_LOGGER = logging.getLogger(__name__)

_BASE_URL = "https://msgapi.threema.ch"
_HTTP_UNAUTHORIZED = 401
_MSG_TYPE_TEXT = 0x01


class ThreemaGatewayClient:
    """Client for sending messages via the Threema Gateway.

    Accepts an externally managed `aiohttp.ClientSession` (recommended when
    embedding this client in a larger application), or none at all, in which
    case the client creates and owns its own session — use it as an async
    context manager in that case::

        async with ThreemaGatewayClient(gateway_id, api_secret) as client:
            await client.send_text_message("ABCD1234", "Hello!")
    """

    def __init__(
        self,
        gateway_id: str,
        api_secret: str,
        private_key: str | None = None,
        *,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the Threema Gateway client."""
        self.gateway_id = gateway_id
        self.api_secret = api_secret
        self.private_key = private_key
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> ThreemaGatewayClient:
        """Create an owned session, if one wasn't supplied."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the session, if this client owns it."""
        if self._owns_session and self._session is not None:
            await self._session.close()

    @property
    def _client_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError(
                "No aiohttp session available. Either pass one to the "
                "constructor, or use this client as an async context manager."
            )
        return self._session

    async def get_credits(self) -> int:
        """Return the number of remaining credits for this Gateway ID.

        Raises ThreemaAuthError for invalid credentials.
        Raises ThreemaConnectionError for other failures.
        """
        session = self._client_session
        try:
            resp = await session.get(
                f"{_BASE_URL}/credits",
                params={"from": self.gateway_id, "secret": self.api_secret},
            )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ThreemaConnectionError(
                f"Connection error fetching credits: {err}"
            ) from err

        if resp.status == _HTTP_UNAUTHORIZED:
            raise ThreemaAuthError("Invalid Threema Gateway credentials")
        if not resp.ok:
            raise ThreemaConnectionError(
                f"Gateway error fetching credits: HTTP {resp.status}"
            )

        try:
            body = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ThreemaConnectionError(
                f"Connection error reading credits response: {err}"
            ) from err

        try:
            return int(body.strip())
        except ValueError as err:
            raise ThreemaConnectionError(
                f"Unexpected credits response: {body!r}"
            ) from err

    async def validate_credentials(self) -> None:
        """Validate the Gateway credentials by checking remaining credits.

        Raises ThreemaAuthError for invalid credentials.
        Raises ThreemaConnectionError for other failures.
        """
        remaining_credits = await self.get_credits()
        _LOGGER.debug("Gateway credentials validated, credits: %s", remaining_credits)

    async def _fetch_recipient_public_key(
        self, recipient_id: str
    ) -> nacl.public.PublicKey:
        """Fetch recipient public key from Threema Gateway."""
        session = self._client_session
        try:
            resp = await session.get(
                f"{_BASE_URL}/pubkeys/{recipient_id}",
                params={"from": self.gateway_id, "secret": self.api_secret},
            )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ThreemaSendError(
                f"Failed to fetch public key for {recipient_id}: {err}"
            ) from err

        if resp.status == _HTTP_UNAUTHORIZED:
            raise ThreemaAuthError("Invalid Threema Gateway credentials")
        if not resp.ok:
            raise ThreemaSendError(
                f"Failed to fetch public key for {recipient_id}: HTTP {resp.status}"
            )

        try:
            key_hex = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ThreemaSendError(
                f"Connection error reading public key response for "
                f"{recipient_id}: {err}"
            ) from err
        try:
            return nacl.public.PublicKey(bytes.fromhex(key_hex.strip()))
        except ValueError as err:
            raise ThreemaSendError(
                f"Malformed public key received for {recipient_id}: {err}"
            ) from err

    def _build_encrypted_message(
        self, text: str, recipient_public_key: nacl.public.PublicKey
    ) -> tuple[bytes, bytes]:
        """Build and encrypt a text message for E2E delivery.

        Returns (nonce, ciphertext) as raw bytes.
        """
        assert self.private_key is not None
        text_bytes = text.encode("utf-8")
        padding_length = os.urandom(1)[0] or 255
        padding = bytes([padding_length] * padding_length)
        plaintext = bytes([_MSG_TYPE_TEXT]) + text_bytes + padding

        private_key = nacl.public.PrivateKey(bytes.fromhex(self.private_key))
        nonce = nacl.utils.random(nacl.public.Box.NONCE_SIZE)
        box = nacl.public.Box(private_key, recipient_public_key)
        encrypted = box.encrypt(plaintext, nonce)
        return encrypted.nonce, encrypted.ciphertext

    async def send_text_message(self, recipient_id: str, text: str) -> str:
        """Send a text message to a Threema ID.

        Sends end-to-end encrypted if a private key was configured,
        otherwise sends via simple (non-E2E) mode.

        Returns the message ID on success.
        Raises ThreemaSendError on failure.
        """
        session = self._client_session

        try:
            if self.private_key:
                _LOGGER.debug("Sending E2E encrypted message to %s", recipient_id)
                recipient_pub_key = await self._fetch_recipient_public_key(recipient_id)
                nonce, ciphertext = self._build_encrypted_message(
                    text, recipient_pub_key
                )
                resp = await session.post(
                    f"{_BASE_URL}/send_e2e",
                    data={
                        "from": self.gateway_id,
                        "to": recipient_id,
                        "secret": self.api_secret,
                        "nonce": nonce.hex(),
                        "box": ciphertext.hex(),
                    },
                )
            else:
                _LOGGER.debug("Sending simple message to %s", recipient_id)
                resp = await session.post(
                    f"{_BASE_URL}/send_simple",
                    data={
                        "from": self.gateway_id,
                        "to": recipient_id,
                        "secret": self.api_secret,
                        "text": text,
                    },
                )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ThreemaSendError(
                f"Connection error sending message to {recipient_id}: {err}"
            ) from err

        if resp.status == _HTTP_UNAUTHORIZED:
            raise ThreemaAuthError("Invalid Threema Gateway credentials")
        if not resp.ok:
            raise ThreemaSendError(
                f"Gateway error sending message to {recipient_id}: HTTP {resp.status}"
            )

        try:
            message_id = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ThreemaSendError(
                f"Connection error reading send response for {recipient_id}: {err}"
            ) from err
        _LOGGER.debug("Message sent to %s (ID: %s)", recipient_id, message_id)
        return message_id
