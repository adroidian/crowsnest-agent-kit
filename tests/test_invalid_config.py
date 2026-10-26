"""I1: malformed configuration stays inside typed ConfigurationError.

Offline only. Parametrized invalid timeouts and base URLs must raise
ConfigurationError (a CrowsnestError) at construction/configuration
time -- never an untyped ValueError/OverflowError from float, socket
timeout conversion, urlsplit, or parsed.port -- and error messages
must never echo a supplied URL that could contain credentials.
"""
from __future__ import annotations

import pytest

from crowsnest_muse_worker.client import CrowsnestHttpClient
from crowsnest_muse_worker.config import Settings, validate_timeout_seconds
from crowsnest_muse_worker.errors import ConfigurationError, CrowsnestError


@pytest.mark.parametrize(
    "raw",
    [
        "nope", "", "nan", "NaN", "inf", "-inf", "Infinity", "-Infinity",
        "0", "-1", "-0.5",
        "1e308", "1e100",  # finite, but platform socket timeout cannot hold
    ],
)
def test_settings_from_env_rejects_invalid_timeout(raw):
    with pytest.raises(ConfigurationError):
        Settings.from_env({"CROWSNEST_TIMEOUT_SECONDS": raw})


@pytest.mark.parametrize("raw", ["15", "0.001", "5", "3600"])
def test_settings_from_env_accepts_valid_timeout(raw):
    settings = Settings.from_env({"CROWSNEST_TIMEOUT_SECONDS": raw})
    assert settings.timeout_seconds == float(raw)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf"), 0, -1.0, 1e308]
)
def test_settings_direct_construction_rejects_invalid_timeout(value):
    with pytest.raises(ConfigurationError):
        Settings(timeout_seconds=value)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf"), 0, -2, 1e308, "x", None]
)
def test_validate_timeout_seconds_rejects_invalid(value):
    with pytest.raises(ConfigurationError):
        validate_timeout_seconds(value)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:bogus/api",          # port cannot be cast
        "http://localhost:99999/api",          # port out of range
        "http://localhost:-1/api",             # negative port
        "http://[broken/api",                  # invalid IPv6 (urlsplit)
        "http://[::1:bogus/api",
        "ftp://example.invalid/api",           # wrong scheme
        "example.invalid/api",                 # no scheme/host
        "http:///api",                         # no host
        "http://example.invalid/api?x=1",      # query
        "http://example.invalid/api#frag",     # fragment
        "http://example.invalid/v1",           # client appends /v1 itself
        "",
    ],
)
def test_client_rejects_malformed_base_url_as_configuration_error(url):
    with pytest.raises(ConfigurationError):
        CrowsnestHttpClient(url)


def test_client_malformed_url_error_never_echoes_supplied_url():
    secret = "do-not-echo-this"
    url = "http://user:%s@localhost:bogus/api" % secret
    with pytest.raises(ConfigurationError) as excinfo:
        CrowsnestHttpClient(url)
    message = str(excinfo.value)
    assert secret not in message
    assert url not in message
    assert "localhost" not in message
    assert isinstance(excinfo.value, CrowsnestError)


@pytest.mark.parametrize(
    "timeout", [float("nan"), float("inf"), float("-inf"), 0, -1.0, 1e308]
)
def test_client_rejects_invalid_timeout_as_configuration_error(timeout):
    with pytest.raises(ConfigurationError):
        CrowsnestHttpClient(
            "http://127.0.0.1:9/api", timeout=timeout,
            raw_request=lambda m, t, b: (200, b"{}"),
        )


def test_client_accepts_valid_loopback_configuration():
    client = CrowsnestHttpClient(
        "http://127.0.0.1:9/api", timeout=5,
        raw_request=lambda m, t, b: (200, b"{}"),
    )
    assert client.public_projection() == {}
