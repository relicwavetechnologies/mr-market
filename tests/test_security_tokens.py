from datetime import timedelta

import pytest

from app.security.tokens import TokenDecodeError, decode, issue_access, issue_refresh, require_type

SECRET = "test-secret-with-at-least-32-bytes"
OTHER_SECRET = "other-secret-with-at-least-32-bytes"


def test_issue_decode_access_round_trip():
    token = issue_access("user-123", secret=SECRET)
    payload = decode(token, secret=SECRET)

    assert payload["sub"] == "user-123"
    require_type(payload, "access")


def test_issue_decode_refresh_round_trip():
    token = issue_refresh("user-123", secret=SECRET)
    payload = decode(token, secret=SECRET)

    assert payload["sub"] == "user-123"
    require_type(payload, "refresh")


def test_expired_token_rejected():
    token = issue_access("user-123", ttl=timedelta(seconds=-1), secret=SECRET)

    with pytest.raises(TokenDecodeError):
        decode(token, secret=SECRET)


def test_wrong_secret_rejected():
    token = issue_access("user-123", secret=SECRET)

    with pytest.raises(TokenDecodeError):
        decode(token, secret=OTHER_SECRET)


def test_wrong_token_type_rejected():
    token = issue_refresh("user-123", secret=SECRET)
    payload = decode(token, secret=SECRET)

    with pytest.raises(TokenDecodeError):
        require_type(payload, "access")
