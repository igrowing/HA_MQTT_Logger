"""Pure message-processing logic, ported 1:1 from the old Node-RED flow.

Four Function nodes did the work: filter noise, detect payload type, derive
labels from the topic, build the Loki record. The first three live here as
side-effect-free functions so they can be unit-tested without a broker or
Loki; the fourth (record building) lives in :mod:`loki`.
"""

from __future__ import annotations

import json
import logging
import re

log = logging.getLogger("mqtt_logger.pipeline")

# Always-on noise filters. Same four prefixes the flow's filter node dropped:
# HA discovery/state, broker system topics, a generic "discovery/" tree, and
# anything under Tasmota's own "tasmota/" topic word.
_BUILTIN_DROP = re.compile(r"^(homeassistant/|\$SYS/|discovery/|tasmota/)")

# Tasmota's default FullTopic is <prefix>/<device>/<endpoint> with prefix one
# of these, so there the device name is the SECOND segment, not the first.
_TASMOTA_PREFIXES = {"cmnd", "stat", "tele"}


def compile_user_patterns(patterns: list[str]) -> list[re.Pattern]:
    """Compile the app's ``filter_regex`` option into regex objects once.

    A pattern that doesn't compile is logged and skipped, mirroring the old
    flow's ``node.warn`` on a bad ``FILTER_REGEX_JSON`` entry. Note these are
    now Python ``re`` patterns, not JavaScript - common syntax is identical.
    """
    compiled: list[re.Pattern] = []
    for raw in patterns:
        try:
            compiled.append(re.compile(raw))
        except re.error as exc:
            log.warning("ignoring invalid filter_regex pattern %r: %s", raw, exc)
    return compiled


def should_drop(topic: str, payload: bytes, user_patterns: list[re.Pattern]) -> bool:
    """True if this message must not reach Loki.

    Drops the four built-in noise prefixes, then any message whose topic OR
    payload text matches one of the user's ``filter_regex`` patterns.
    """
    if _BUILTIN_DROP.match(topic or ""):
        return True
    if user_patterns:
        payload_str = payload.decode("utf-8", "replace")
        for pat in user_patterns:
            if pat.search(topic or "") or pat.search(payload_str):
                return True
    return False


def detect_format(raw: str) -> str:
    """``"json"`` if the payload parses as JSON, else ``"text"``.

    Parity with the old flow's ``JSON.parse`` probe: a bare number or quoted
    string ("123", '"x"') counts as JSON, an empty or non-JSON payload counts
    as text.
    """
    try:
        json.loads(raw)
        return "json"
    except ValueError:
        return "text"


def extract_labels(topic: str, fmt: str) -> dict[str, str]:
    """Derive the Loki stream labels from the topic.

    device = first topic segment, or the second one for Tasmota's
    cmnd/stat/tele topics; type = last topic segment; both fall back to
    ``"unknown"``. Mirrors the flow's "Extract labels" node.
    """
    parts = [p for p in (topic or "").split("/") if p]
    is_tasmota = bool(parts) and parts[0].lower() in _TASMOTA_PREFIXES

    if is_tasmota:
        device = parts[1] if len(parts) > 1 else "unknown"
    else:
        device = parts[0] if parts else "unknown"

    msg_type = parts[-1] if parts else "unknown"

    return {
        "source": "mqtt",
        "device": device,
        "type": msg_type,
        "topic": topic or "",
        "format": fmt,
    }
