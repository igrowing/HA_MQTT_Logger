"""Make the add-on's service modules importable from the unit tests.

The service lives at mqtt_logger/rootfs/opt/mqtt-logger/ (its in-container
path is /opt/mqtt-logger). Unit tests import config/pipeline/loki/stats
directly from there - no packaging, no install step.
"""

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "mqtt_logger" / "rootfs" / "opt" / "mqtt-logger"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
