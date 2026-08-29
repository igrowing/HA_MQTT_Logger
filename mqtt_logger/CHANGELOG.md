# Changelog

## 1.1.0

- Replace the Node-RED MQTT ingest flow with a small built-in Python service.
  Same behaviour and the same Loki streams (`source="mqtt"`, and
  `source="mqtt-logger"` with `type="stats"` / `type="error"`), so the
  dashboard is unchanged - but ~100-140 MB smaller image per architecture and
  much lower RAM (Node-RED idled around 80-120 MB; the Python service is
  ~15-25 MB).
- New buffered writer: messages are queued and shipped to Loki in batches
  with automatic retry/backoff while Loki is briefly unavailable. If Loki is
  down long enough to fill the buffer (~20k messages) the oldest unsent
  messages are dropped, and the count is reported to the `type="error"`
  stream on recovery.
- `filter_regex` patterns are now Python (`re`) syntax instead of JavaScript.
  Common patterns (anchors, character classes, quantifiers, alternation) are
  identical; a few constructs differ (named groups are `(?P<name>...)`,
  JavaScript-only lookbehind quirks, `\d`/`\w` Unicode semantics).
- The optional Node-RED editor on port `18880` is removed. `/data/nodered` is
  deleted automatically on upgrade; Loki history and Grafana settings carry
  over untouched.

## 1.0.9

- Fix typos in documentation.

## 1.0.8

- Drop armhf from pipeline build.

## 1.0.7

- Fix build for armv7.

## 1.0.6

- Remove **MQTT messages (readable)** panel as low added value for high screen footprint.

## 1.0.5

- Make JSON payloads readable without changing what gets stored. The
  **Message** column (and **Last message** on the devices table) now opens in
  a formatted, collapsible JSON viewer via the magnifier that appears on
  hover, and a new **MQTT messages (readable)** panel renders the same
  messages as a pretty-printed log stream whose lines expand into a per-key
  field table. Both are display-only - Loki keeps every payload verbatim.

## 1.0.4

- Open the MQTT Devices dashboard directly instead of Grafana's stock home
  page.
  
## 1.0.3

- Fix the sidebar panel showing a grey "refused to connect" page: Grafana
  sent `X-Frame-Options: deny`, so the browser blocked the Ingress iframe.
- Fix Grafana's asset URLs under Ingress by deriving `root_url` from the
  app's own Ingress path at startup.
- Fix the endless MQTT reconnect loop caused by sharing the client id
  `nodered-loki-logger` with the hand-imported flow from the pre-app version
  of this project. New client id is `ha-mqtt-logger-addon`; existing installs
  are migrated on start.
- Update documentation.

## 1.0.2

- Fix Node-RED authentication mechanism for MQTT broker, crashed the app.

## 1.0.0

- Initial release. Combines Node-RED, Loki, and Grafana into a single app:
  install, set MQTT credentials/retention/filter patterns, and the MQTT
  Devices dashboard is ready in the sidebar - no manual Node-RED/Grafana/Loki
  setup required.
