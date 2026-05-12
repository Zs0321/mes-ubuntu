from qrmes_kingdee_integration.auth.signer import generate_signature


def test_generate_signature_matches_known_sha256_example():
    sign = generate_signature(
        db_id="68ff2e73ccf379",
        username="林秀丽",
        app_id="327849_7Zcu2YtP2vBXWWVtRZXoR6Vvyr3W2Ktp",
        app_secret="secret-demo",
        timestamp=1765419679,
    )

    assert sign == "367be29753ba85bc8d9157af4dbbd600723a369e8195d984c29786886093a390"
