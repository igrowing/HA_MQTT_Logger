# MQTT Logger and browser

Logs every MQTT message seen by your Home Assistant broker into Loki, then
gives you a Grafana dashboard to see which devices are online and to search
the raw message history - filterable by device and topic.

## Architecture

```
MQTT broker (core-mosquitto)
   -> Node-RED  ("MQTT -> Loki Logger" flow: filter, label, forward)
        -> Loki (log storage, in-container)
             -> Grafana ("MQTT Devices" dashboard, reached via the sidebar)
```

All three services run inside this one app/container. There is nothing to
import or configure by hand in Node-RED or Grafana - the flow and dashboard
are seeded automatically on first start.

## Prerequisites

- The official **Mosquitto broker** app/add-on, started, with **Start on
  boot** enabled. Its internal hostname is always `core-mosquitto` on port
  `1883` - this app assumes that.
- A dedicated MQTT user for this app (Settings -> People -> Users -> Add
  User, with a password - don't reuse your own admin account). Enter its
  username/password in this app's **Configuration** tab.

## Configuration

| Option | Description |
| --- | --- |
| `mqtt_username` | The dedicated MQTT user created above. Leave blank for an anonymous broker connection. |
| `mqtt_password` | Password for that user. |
| `retention_days` | How many days of MQTT history Loki keeps before deleting it. Applies on restart. |
| `filter_regex` | A list of regex patterns (JavaScript syntax). Any MQTT message whose **topic or payload** matches one of these is dropped before it reaches Loki, in addition to the built-in `homeassistant/#`, `$SYS/#`, `discovery/#`, and `tasmota/#` noise filters, which always apply. |

## Using the dashboard

Open **MQTT Logger** from the sidebar (added automatically via Ingress - no
separate login). You'll see:

- **MQTT devices** - one row per device, green/red "Online" status based on
  whether it's logged a message in the last 10 minutes, OR its last known
  `.../availability`, `.../online`, or `.../status` payload (retained LWT,
  looked back over 24h) says online/true - plus last topic and last message
  seen.
- **MQTT messages** - a searchable table of raw messages, filterable by the
  dashboard's time range plus the **Device** and **MQTT Topic** dropdowns at
  the top (both multi-select, default to all; the Topic list narrows to
  whichever device(s) you have selected).
- **Message volume heatmap** - message count per device per time bucket, to
  spot busy periods or dead devices at a glance.

## Advanced: reaching Node-RED directly

The Node-RED editor isn't part of the sidebar panel by default, since the
dashboard is meant to need no manual flow editing. If you want to inspect or
tweak the flow, this app maps container port `1880` - open
`http://<your-home-assistant-ip>:1880` directly. Any changes you make there
persist across restarts (they're saved to this app's own data directory, not
overwritten by updates).

## Verifying end-to-end

1. Publish a test MQTT message (e.g. via Developer Tools -> Actions ->
   `mqtt.publish` in Home Assistant, or any MQTT client) to any topic that
   isn't under `homeassistant/`, `$SYS/`, `discovery/`, or `tasmota/`.
2. Open the app's **Log** tab and confirm you see Node-RED's running-totals
   counter incrementing.
3. Open the **MQTT Logger** dashboard from the sidebar and confirm your test
   device shows up.

## Troubleshooting

- **A device/topic you know is active doesn't show up in the dashboard's
  filters or table:** check for push failures in Loki -
  `{source="mqtt-logger", type="error", device="<device>"}` (e.g. oversized
  payloads hitting Loki's line-size limit).
- **The "Online" column shows nothing / flickers:** this comes from joining
  two Loki queries by the `device` field. If you ever edit the panel's
  transformations, make sure the instant query's labels are converted to
  real fields (`labelsToFields`) before the `joinByField` step, otherwise the
  join silently drops that data.
- **The app stops logging:** check this app's **Log** tab for a crash/OOM
  around the gap, and Settings -> System -> Logs (Supervisor/Host) for
  out-of-memory kills. Watchdog restarts the whole app automatically on a
  real crash.
- **A `filter_regex` pattern doesn't seem to apply:** the pattern list is
  compiled once when Node-RED starts. Restart the app after changing
  `filter_regex` in Configuration.

## Known limitations

- **armv7 / armhf builds are best-effort.** Home Assistant Supervisor
  dropped 32-bit architecture support in the 2025.12 release line; current
  Supervisor versions on 64-bit hardware only need `amd64`/`aarch64`. The
  32-bit images are built separately, aren't covered by the same CI
  guarantees, and may stop building entirely if upstream Node-RED/Loki/
  Grafana images drop 32-bit support first.
- Grafana is reached through Home Assistant's Ingress proxy, which rewrites
  the request path under a per-install prefix. If you notice broken
  styling/assets in the dashboard after an update, it's most likely an
  Ingress sub-path issue in Grafana's own static asset URLs rather than a
  data problem - check the app's **Log** tab for Grafana startup errors
  first.
