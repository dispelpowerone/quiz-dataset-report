import textwrap

from quiz_dataset_report.config import load_config


def test_load_config_expands_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "bot@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(textwrap.dedent("""
            smtp:
              host: smtp.gmail.com
              username: ${SMTP_USERNAME}
              password: ${SMTP_PASSWORD}
              from_address: ${SMTP_USERNAME}
            maintainers:
              - team@example.com
            apps:
              - name: Ontario
                domain: on
                dataset: analytics_347566445
            """))
    cfg = load_config(cfg_path)
    assert cfg.smtp.username == "bot@example.com"
    assert cfg.smtp.password == "secret"
    assert cfg.smtp.from_address == "bot@example.com"
    assert cfg.maintainers == ["team@example.com"]
    assert cfg.apps[0].domain == "on"
    # defaults applied
    assert cfg.clickhouse.database == "firebase"
    assert cfg.report.days == 30
    assert cfg.languages[1] == "EN"


def test_app_lookup_by_name_or_domain(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(textwrap.dedent("""
            apps:
              - name: Ontario
                domain: on
                dataset: ds1
              - name: Texas
                domain: tx
                dataset: ds2
                enabled: false
            """))
    cfg = load_config(cfg_path)
    assert cfg.app_by_key("on").name == "Ontario"
    assert cfg.app_by_key("TEXAS").domain == "tx"
    assert cfg.app_by_key("missing") is None
