"""Tests for live video provisioning."""

import json
from typing import Any
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from custom_components.dreame_mower.dreame.cloud.cloud_video import (
    VIDEO_STRINGS,
    DreameMowerCloudVideo,
    DreameMowerVideoError,
    DreameMowerVideoSession,
    decode_identity_value,
)
from custom_components.dreame_mower.dreame.cloud.cloud_base import _decode_api_strings

MATERIAL = _decode_api_strings(VIDEO_STRINGS)[0].encode("utf-8")

DEVICE_ID = "-111603995"


def encode_value(plaintext: str) -> str:
    """Produce a value in the form the identity endpoint returns."""
    raw = plaintext.encode("utf-8")
    padded = raw + b"\x00" * (-len(raw) % 16)
    encryptor = Cipher(algorithms.AES(MATERIAL), modes.CBC(MATERIAL)).encryptor()
    return (encryptor.update(padded) + encryptor.finalize()).hex()


def ok(payload: Any) -> dict[str, Any]:
    """Wrap a payload the way the video service nests its responses."""
    return {"code": 0, "success": True, "data": {"requestId": "r", "data": payload}}


class TestDecodeIdentityValue:
    """Reading the encoded values the identity endpoint returns."""

    def test_decodes_a_value(self):
        assert decode_identity_value(encode_value("AKIDexample")) == "AKIDexample"

    def test_keeps_only_the_leading_field(self):
        encoded = encode_value("AKIDexample|extra|more")
        assert decode_identity_value(encoded) == "AKIDexample"

    def test_accepts_a_hex_prefix(self):
        encoded = encode_value("AKIDexample")
        assert decode_identity_value("0x" + encoded.upper()) == "AKIDexample"

    @pytest.mark.parametrize("value", [None, "", "zzzz", "abcd", "00" * 7])
    def test_rejects_what_it_cannot_decode(self, value):
        assert decode_identity_value(value) is None


class TestDreameMowerCloudVideo:
    """The provisioning exchange."""

    @pytest.fixture
    def cloud_base(self):
        base = Mock()
        base.get_api_url.return_value = "https://eu.example:1"
        return base

    @pytest.fixture
    def video(self, cloud_base):
        return DreameMowerCloudVideo(cloud_base, DEVICE_ID)

    def responses(self, cloud_base, **overrides):
        """Answer each endpoint with a realistic body, overridable per test."""
        bodies = {
            "user/accesstoken": ok({"accessToken": "tok"}),
            "dev/isDevUser": ok({"isDevUser": True}),
            "mgr/dev/getIdentity": ok(
                {
                    "secretId": encode_value("app-id"),
                    "secretKey": encode_value("app-secret"),
                    "deviceId": "PID/DEVNAME",
                    "deviceName": "DEVNAME",
                    "productId": "PID",
                }
            ),
            "dev/getP2PInfo": ok({"p2pInfo": "XP2Pabc"}),
        }
        bodies.update(overrides)

        def request(url: str, data: str, retry_count: int = 0) -> Any:
            for endpoint, body in bodies.items():
                if url.endswith(endpoint):
                    return body
            raise AssertionError(f"unexpected endpoint: {url}")

        cloud_base.request.side_effect = request
        return bodies

    def test_provisions_a_session(self, video, cloud_base):
        self.responses(cloud_base)
        session = video.provision(uid="UID", model="dreame.mower.g2408")
        assert session == DreameMowerVideoSession(
            product_id="PID",
            device_name="DEVNAME",
            p2p_info="XP2Pabc",
            app_id="app-id",
            app_secret="app-secret",
        )
        assert session.channel_id == "PID/DEVNAME"

    def test_sends_the_device_and_token_to_each_endpoint(self, video, cloud_base):
        self.responses(cloud_base)
        video.provision()
        signed = [
            json.loads(call.args[1])
            for call in cloud_base.request.call_args_list
            if not call.args[0].endswith("user/accesstoken")
        ]
        assert signed, "expected calls beyond the token request"
        for params in signed:
            assert params["did"] == DEVICE_ID
            assert params["accesstoken"] == "tok"
            assert params["accessToken"] == "tok"

    def test_passes_the_account_and_model_to_the_identity_call(self, video, cloud_base):
        self.responses(cloud_base)
        video.provision(uid="UID", model="MODEL")
        identity = next(
            json.loads(call.args[1])
            for call in cloud_base.request.call_args_list
            if call.args[0].endswith("getIdentity")
        )
        assert identity["uid"] == "UID"
        assert identity["model"] == "MODEL"

    def test_reports_an_account_without_video(self, video, cloud_base):
        self.responses(cloud_base, **{"dev/isDevUser": ok({"isDevUser": False})})
        with pytest.raises(DreameMowerVideoError, match="not enabled for video"):
            video.provision()

    def test_treats_a_missing_eligibility_flag_as_no_video(self, video, cloud_base):
        self.responses(cloud_base, **{"dev/isDevUser": ok({})})
        with pytest.raises(DreameMowerVideoError, match="not enabled for video"):
            video.provision()

    def test_reports_a_missing_token(self, video, cloud_base):
        self.responses(cloud_base, **{"user/accesstoken": None})
        with pytest.raises(DreameMowerVideoError, match="access token"):
            video.provision()

    def test_reports_a_missing_identity(self, video, cloud_base):
        self.responses(cloud_base, **{"mgr/dev/getIdentity": ok({})})
        with pytest.raises(DreameMowerVideoError, match="video identity"):
            video.provision()

    def test_reports_an_identity_it_cannot_read(self, video, cloud_base):
        self.responses(
            cloud_base,
            **{
                "mgr/dev/getIdentity": ok(
                    {"productId": "PID", "deviceName": "DEVNAME", "secretId": "nothex"}
                )
            },
        )
        with pytest.raises(DreameMowerVideoError, match="identity is incomplete"):
            video.provision()

    def test_reports_missing_session_details(self, video, cloud_base):
        self.responses(cloud_base, **{"dev/getP2PInfo": ok({})})
        with pytest.raises(DreameMowerVideoError, match="session details"):
            video.provision()

    def test_survives_an_unreachable_cloud(self, video, cloud_base):
        cloud_base.request.return_value = None
        with pytest.raises(DreameMowerVideoError):
            video.provision()
