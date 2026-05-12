from qrmes_kingdee_integration.config import KingdeeRuntimeConfig, load_settings


def test_load_settings_prefers_environment_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("KINGDEE_BASE_URL", "http://example.com/k3cloud")
    monkeypatch.setenv("KINGDEE_DB_ID", "db-001")
    monkeypatch.setenv("KINGDEE_USERNAME", "tester")
    monkeypatch.setenv("KINGDEE_APP_ID", "app-001")
    monkeypatch.setenv("KINGDEE_APP_SECRET", "secret-001")
    monkeypatch.setenv("KINGDEE_TIMEOUT_SECS", "29")

    settings = load_settings(project_root=tmp_path)

    assert isinstance(settings.kingdee, KingdeeRuntimeConfig)
    assert settings.kingdee.base_url == "http://example.com/k3cloud"
    assert settings.kingdee.db_id == "db-001"
    assert settings.kingdee.username == "tester"
    assert settings.kingdee.timeout_seconds == 29
    assert settings.kingdee.is_ready is True


def test_public_summary_reports_missing_fields():
    summary = KingdeeRuntimeConfig(
        base_url="",
        db_id="",
        username="tester",
        app_id="",
        app_secret="",
        lcid=2052,
        timeout_seconds=15,
        verify_ssl=True,
    ).public_summary

    assert summary["configured"] is False
    assert summary["missing"] == [
        "KINGDEE_BASE_URL",
        "KINGDEE_DB_ID",
        "KINGDEE_APP_ID",
        "KINGDEE_APP_SECRET",
    ]


def test_load_settings_supports_local_sync_db_path(monkeypatch, tmp_path):
    monkeypatch.setenv("QRMES_KINGDEE_DB_PATH", str(tmp_path / 'custom.db'))

    settings = load_settings(project_root=tmp_path)

    assert settings.local_db_path == tmp_path / 'custom.db'


def test_load_settings_falls_back_to_qrmes_config_json(monkeypatch, tmp_path):
    cfg = tmp_path / 'webdav_config.json'
    cfg.write_text(
        '{"kingdee_base_url":"http://172.16.30.251/k3cloud","kingdee_acct_id":"69ca3e07b23d85","kingdee_username":"邱子航","kingdee_app_id":"app-x","kingdee_app_secret":"secret-x","kingdee_timeout_secs":21,"kingdee_verify_ssl":false}',
        encoding='utf-8',
    )
    monkeypatch.delenv('KINGDEE_BASE_URL', raising=False)
    monkeypatch.delenv('KINGDEE_DB_ID', raising=False)
    monkeypatch.delenv('KINGDEE_USERNAME', raising=False)
    monkeypatch.delenv('KINGDEE_APP_ID', raising=False)
    monkeypatch.delenv('KINGDEE_APP_SECRET', raising=False)
    monkeypatch.setenv('QRMES_KINGDEE_CONFIG_JSON', str(cfg))

    settings = load_settings(project_root=tmp_path)

    assert settings.kingdee.base_url == 'http://172.16.30.251/k3cloud'
    assert settings.kingdee.db_id == '69ca3e07b23d85'
    assert settings.kingdee.username == '邱子航'
    assert settings.kingdee.app_id == 'app-x'
    assert settings.kingdee.app_secret == 'secret-x'
    assert settings.kingdee.timeout_seconds == 21
    assert settings.kingdee.verify_ssl is False
