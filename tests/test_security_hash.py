from app.security.hash import hash_password, verify_password


def test_hash_password_round_trip():
    stored = hash_password("hunter2hunter2")

    assert stored != "hunter2hunter2"
    assert verify_password("hunter2hunter2", stored)


def test_verify_password_rejects_tampered_values():
    stored = hash_password("hunter2hunter2")

    assert not verify_password("wrong-password", stored)
    assert not verify_password("hunter2hunter2", f"{stored}tampered")
    assert not verify_password("hunter2hunter2", "not-an-argon2-hash")
