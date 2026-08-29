import json

import config


def write_options(tmp_path, data):
    p = tmp_path / "options.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_reads_options_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MQTT_USER", raising=False)
    monkeypatch.delenv("MQTT_PASSWORD", raising=False)
    monkeypatch.setenv(
        "OPTIONS_FILE",
        write_options(tmp_path, {"mqtt_username": "logger", "mqtt_password": "s3cret",
                                 "filter_regex": ["^debug/", "heartbeat"]}),
    )
    cfg = config.load()
    assert cfg.mqtt_username == "logger"
    assert cfg.mqtt_password == "s3cret"
    assert cfg.filter_regex == ["^debug/", "heartbeat"]
    assert cfg.has_credentials is True
    assert cfg.mqtt_host == "core-mosquitto"
    assert cfg.loki_url == config.DEFAULT_LOKI_URL


def test_missing_file_falls_back_to_defaults(tmp_path, monkeypatch):
    for var in ("MQTT_USER", "MQTT_PASSWORD", "LOKI_URL", "MQTT_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPTIONS_FILE", str(tmp_path / "nope.json"))
    cfg = config.load()
    assert cfg.mqtt_username == ""
    assert cfg.has_credentials is False
    assert cfg.filter_regex == []


def test_env_overrides_win(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIONS_FILE", write_options(tmp_path, {"mqtt_username": "fromfile"}))
    monkeypatch.setenv("MQTT_USER", "fromenv")
    monkeypatch.setenv("MQTT_HOST", "mosquitto")
    monkeypatch.setenv("MQTT_PORT", "18830")
    monkeypatch.setenv("LOKI_URL", "http://loki:3100/loki/api/v1/push")
    cfg = config.load()
    assert cfg.mqtt_username == "fromenv"
    assert cfg.mqtt_host == "mosquitto"
    assert cfg.mqtt_port == 18830
    assert cfg.loki_url == "http://loki:3100/loki/api/v1/push"


def test_non_list_filter_regex_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIONS_FILE", write_options(tmp_path, {"filter_regex": "oops"}))
    assert config.load().filter_regex == []
