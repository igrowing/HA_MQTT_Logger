import pipeline


def patterns(*raw):
    return pipeline.compile_user_patterns(list(raw))


class TestShouldDrop:
    def test_builtin_noise_prefixes_are_dropped(self):
        for topic in (
            "homeassistant/sensor/x/config",
            "$SYS/broker/uptime",
            "discovery/foo",
            "tasmota/discovery/ABC/config",
        ):
            assert pipeline.should_drop(topic, b"{}", []) is True

    def test_normal_topic_is_kept(self):
        assert pipeline.should_drop("zigbee2mqtt/kitchen/state", b"{}", []) is False

    def test_prefix_match_is_anchored(self):
        # "homeassistant" only as a leading path segment, not mid-topic
        assert pipeline.should_drop("x/homeassistant/y", b"{}", []) is False

    def test_user_pattern_matches_topic(self):
        pats = patterns(r"/debug$")
        assert pipeline.should_drop("device/1/debug", b"payload", pats) is True

    def test_user_pattern_matches_payload(self):
        pats = patterns(r"heartbeat")
        assert pipeline.should_drop("device/1/state", b'{"kind":"heartbeat"}', pats) is True

    def test_user_pattern_no_match(self):
        pats = patterns(r"^never/")
        assert pipeline.should_drop("device/1/state", b"ok", pats) is False

    def test_invalid_pattern_is_skipped_not_fatal(self):
        pats = pipeline.compile_user_patterns(["(unbalanced", r"drop-me"])
        assert len(pats) == 1
        assert pipeline.should_drop("t", b"please drop-me", pats) is True

    def test_non_utf8_payload_does_not_raise(self):
        pats = patterns(r"zzz")
        assert pipeline.should_drop("t", b"\xff\xfe\x00", pats) is False


class TestDetectFormat:
    def test_object(self):
        assert pipeline.detect_format('{"a": 1}') == "json"

    def test_array(self):
        assert pipeline.detect_format("[1, 2, 3]") == "json"

    def test_plain_text(self):
        assert pipeline.detect_format("ON") == "text"

    def test_bare_number_is_json_like_old_flow(self):
        # parity with Node-RED's JSON.parse probe
        assert pipeline.detect_format("23.5") == "json"

    def test_empty_is_text(self):
        assert pipeline.detect_format("") == "text"

    def test_whitespace_padded_json(self):
        assert pipeline.detect_format('  \n{"a":1}\t ') == "json"


class TestExtractLabels:
    def test_basic_topic(self):
        labels = pipeline.extract_labels("zigbee2mqtt/kitchen/state", "json")
        assert labels == {
            "source": "mqtt",
            "device": "zigbee2mqtt",
            "type": "state",
            "topic": "zigbee2mqtt/kitchen/state",
            "format": "json",
        }

    def test_tasmota_prefix_shifts_device_to_second_segment(self):
        for prefix in ("cmnd", "stat", "tele"):
            labels = pipeline.extract_labels(f"{prefix}/tasmota_A1/POWER", "text")
            assert labels["device"] == "tasmota_A1"
            assert labels["type"] == "POWER"

    def test_tasmota_prefix_is_case_insensitive(self):
        assert pipeline.extract_labels("TELE/dev/SENSOR", "json")["device"] == "dev"

    def test_single_segment_topic(self):
        labels = pipeline.extract_labels("heartbeat", "text")
        assert labels["device"] == "heartbeat"
        assert labels["type"] == "heartbeat"

    def test_trailing_slash_is_ignored(self):
        labels = pipeline.extract_labels("device/1/state/", "text")
        assert labels["device"] == "device"
        assert labels["type"] == "state"

    def test_empty_topic_falls_back_to_unknown(self):
        labels = pipeline.extract_labels("", "text")
        assert labels["device"] == "unknown"
        assert labels["type"] == "unknown"

    def test_tasmota_prefix_only(self):
        labels = pipeline.extract_labels("cmnd", "text")
        assert labels["device"] == "unknown"
        assert labels["type"] == "cmnd"
