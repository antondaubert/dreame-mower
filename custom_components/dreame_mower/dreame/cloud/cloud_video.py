"""Live video provisioning for mowers with a camera.

Before a camera stream can be opened, the cloud hands out the identity and
session details the video transport needs. This module performs that exchange
and nothing else: it does not talk to the mower, start a stream, or touch the
native helper that carries the media.

Some values arrive encoded and are normalised here into the form the
transport expects.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Final, Optional

from .cloud_base import DreameMowerCloudBase, _decode_api_strings

_LOGGER = logging.getLogger(__name__)

# Path of the video service within the account API.
VIDEO_SERVICE = "dreame-third-video/tx"

VIDEO_STRINGS: Final = "H4sIAAAAAAAC/4tWcnUNySquKtWK8DStyvMo9lSKBQAr/AMJFAAAAA=="

_VIDEO_STRINGS: Final = _decode_api_strings(VIDEO_STRINGS)
_BLOCK_SIZE = 16


class DreameMowerVideoError(Exception):
    """Raised when video provisioning cannot be completed."""


@dataclass(frozen=True)
class DreameMowerVideoSession:
    """Everything the transport needs to open one live video session."""

    product_id: str
    device_name: str
    p2p_info: str
    app_id: str
    app_secret: str

    @property
    def channel_id(self) -> str:
        """Return the identifier the transport uses for this camera."""
        return f"{self.product_id}/{self.device_name}"


def decode_identity_value(value: Optional[str]) -> Optional[str]:
    """Return the usable form of one encoded identity value.

    Returns None when the value is absent or cannot be read, so a changed
    response shape degrades into "no video" rather than an exception.
    """
    if not value:
        return None

    text = value.strip()
    if text.lower().startswith("0x"):
        text = text[2:]
    try:
        ciphertext = bytes.fromhex(text)
    except ValueError:
        return None
    if not ciphertext or len(ciphertext) % _BLOCK_SIZE:
        return None

    try:
        from cryptography.hazmat.primitives.ciphers import (
            Cipher,
            algorithms,
            modes,
        )
    except ImportError:  # pragma: no cover - always present under Home Assistant
        _LOGGER.warning("Cannot read the video identity: cryptography is missing")
        return None

    material = _VIDEO_STRINGS[0].encode("utf-8")
    decryptor = Cipher(algorithms.AES(material), modes.CBC(material)).decryptor()
    try:
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        decoded = plaintext.rstrip(b"\x00").decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None

    # Only the leading field is used; the rest are pipe-separated extras.
    return decoded.split("|", 1)[0] or None


def _find_value(payload: Any, names: tuple[str, ...]) -> Any:
    """Return the first value stored under any of these keys, of any type."""
    if isinstance(payload, dict):
        for name in names:
            if name in payload:
                return payload[name]
        for value in payload.values():
            found = _find_value(value, names)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_value(item, names)
            if found is not None:
                return found
    return None


def _find_text(payload: Any, names: tuple[str, ...]) -> Optional[str]:
    """Return the first non-empty string stored under any of these keys."""
    if isinstance(payload, dict):
        for name in names:
            value = payload.get(name)
            if isinstance(value, str) and value:
                return value
        for value in payload.values():
            found = _find_text(value, names)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_text(item, names)
            if found is not None:
                return found
    return None


class DreameMowerCloudVideo:
    """Fetch the cloud half of a live video session."""

    def __init__(self, cloud_base: DreameMowerCloudBase, device_id: str) -> None:
        """Bind provisioning to one device on an authenticated cloud session."""
        self._cloud_base = cloud_base
        self._device_id = device_id

    def _post(self, endpoint: str, params: dict[str, Any]) -> Any:
        """Call one video endpoint and return its decoded body."""
        url = f"{self._cloud_base.get_api_url()}/{VIDEO_SERVICE}/{endpoint}"
        return self._cloud_base.request(
            url, json.dumps(params, separators=(",", ":")), retry_count=0
        )

    def _authenticated(self, token: Optional[str], **extra: Any) -> dict[str, Any]:
        """Build the parameters the video endpoints expect."""
        params: dict[str, Any] = {"did": self._device_id, "os": 1}
        if token:
            # The service reads either spelling depending on the endpoint.
            params["accesstoken"] = token
            params["accessToken"] = token
        params.update(extra)
        return params

    def get_access_token(self) -> Optional[str]:
        """Return the short-lived token the other video calls are signed with."""
        response = self._post("user/accesstoken", {"os": 1})
        return _find_text(response, ("accessToken", "accesstoken", "token"))

    def is_eligible(self, token: Optional[str]) -> Optional[bool]:
        """Return whether this account may use video for this device.

        Returns None when the cloud could not be asked, which is a different
        thing from a refusal and must not be reported as one.
        """
        response = self._post("dev/isDevUser", self._authenticated(token))
        _LOGGER.debug("Video eligibility for %s: %s", self._device_id, response)
        if not isinstance(response, dict) or response.get("code") != 0:
            return None
        # The flag is a boolean, so an absent one counts as a refusal.
        return _find_value(response, ("isDevUser", "isDevuser")) is True

    def supports_video(self) -> Optional[bool]:
        """Return whether video is worth offering for this account and device.

        This is the cheap half of provisioning, for deciding whether to create
        entities at all. None means the question could not be answered, in
        which case the caller should assume video might work rather than
        hiding it over a passing cloud failure.
        """
        try:
            token = self.get_access_token()
            if not token:
                return None
            return self.is_eligible(token)
        except Exception as err:  # noqa: BLE001 - an unanswerable question
            _LOGGER.debug("Could not ask whether video is available: %s", err)
            return None

    def get_identity(
        self, token: Optional[str], uid: Optional[str], model: Optional[str]
    ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Return the product id, device name and application values."""
        extra: dict[str, Any] = {}
        if uid:
            extra["uid"] = uid
        if model:
            extra["model"] = model
        response = self._post("mgr/dev/getIdentity", self._authenticated(token, **extra))

        return (
            _find_text(response, ("productId", "product_id")),
            _find_text(response, ("deviceName", "device_name")),
            decode_identity_value(_find_text(response, ("secretId", "secret_id"))),
            decode_identity_value(_find_text(response, ("secretKey", "secret_key"))),
        )

    def get_p2p_info(self, token: Optional[str]) -> Optional[str]:
        """Return the session details the transport connects with."""
        response = self._post("dev/getP2PInfo", self._authenticated(token))
        return _find_text(response, ("p2pInfo", "p2p_info", "initStringApp"))

    def provision(
        self, uid: Optional[str] = None, model: Optional[str] = None
    ) -> DreameMowerVideoSession:
        """Run the whole exchange and return a usable session.

        Raises DreameMowerVideoError when any step does not produce what the
        transport needs, so callers can treat video as simply unavailable.
        """
        token = self.get_access_token()
        if not token:
            raise DreameMowerVideoError("The cloud did not issue a video access token")

        eligible = self.is_eligible(token)
        if eligible is False:
            raise DreameMowerVideoError("This account is not enabled for video")
        if eligible is None:
            # Carry on rather than refuse: the calls that follow will fail
            # clearly enough if video really is not allowed.
            _LOGGER.debug("Could not confirm video eligibility; trying anyway")

        product_id, device_name, app_id, app_secret = self.get_identity(token, uid, model)
        if not product_id or not device_name:
            raise DreameMowerVideoError("The cloud did not return a video identity")
        if not app_id or not app_secret:
            raise DreameMowerVideoError("The video identity is incomplete")

        p2p_info = self.get_p2p_info(token)
        if not p2p_info:
            raise DreameMowerVideoError("The cloud did not return session details")

        _LOGGER.debug("Video provisioning succeeded for %s", self._device_id)
        return DreameMowerVideoSession(
            product_id=product_id,
            device_name=device_name,
            p2p_info=p2p_info,
            app_id=app_id,
            app_secret=app_secret,
        )
