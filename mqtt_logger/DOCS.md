# MQTT Logger and browser

Logs every MQTT message seen by your Home Assistant broker into Loki, then
gives you a Grafana dashboard to see which devices are online and to search
the raw message history - filterable by device and topic.

## Installing

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Figrowing%2FHA_MQTT_Logger)

1. Click the button above (opens your own Home Assistant instance and
   pre-fills the repository URL), or add it manually: Settings ->
   Add-ons/Apps -> Add-on/App Store -> ⋮ -> Repositories -> paste
   `https://github.com/igrowing/HA_MQTT_Logger`.
2. Find **MQTT Logger** in the store and install it.
3. Before starting it: install the official **Mosquitto broker**
   app/add-on if you don't already have one, and create a dedicated MQTT
   user for this app under Settings -> People -> Users (don't reuse your own
   admin account).
4. Open **MQTT Logger**'s Configuration tab, set `mqtt_username` /
   `mqtt_password` to that user, and adjust `retention_days` /
   `filter_regex` if you want (defaults: 30 days, no extra filtering beyond
   the built-in HA-discovery/system-topic noise filters).
5. Return to **MQTT Logger**'s Info tab and assert:
  - "Show in sidebar" - for ease of access to the app;
  - "Watchdog" - for restert of the app if crashes (not likely but safe!)
  - "Auto update" - optionally.
6. Start the app. **MQTT Logger** appears in the sidebar with the dashboard
   ready - no separate Grafana login, no manual Node-RED flow import, no
   Loki setup.

See [mqtt_logger/DOCS.md](mqtt_logger/DOCS.md) for how to verify it's
working end-to-end and for troubleshooting.

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
  whichever device(s) you have selected). Hover a **Message** cell and click
  the magnifier that appears to open the payload in a formatted, collapsible
  JSON viewer instead of reading it as one long line.
- **Message volume heatmap** - message count per device per time bucket, to
  spot busy periods or dead devices at a glance.

The JSON viewer is display-only: Loki still stores every payload exactly
as the device published it, and the Node-RED flow never rewrites your data.

## Advanced: editing the Node-RED flow

The Node-RED editor isn't part of the sidebar panel by default, since the
dashboard is meant to need no manual flow editing. If you want to inspect or
tweak the flow, or the TCP port is already reserved by the other service in your HA, this app maps container port `18880` - open
`http://<your-home-assistant-ip>:18880` directly. Any changes you make there
persist across restarts (they're saved to this app's own data directory, not
overwritten by updates).

## Where the data lives

Everything stateful sits in this app's own persistent volume, mounted at
`/data` inside the container:

| Path | What |
| --- | --- |
| `/data/loki` | The log database itself - chunks, TSDB index, WAL, compactor state |
| `/data/grafana` | Grafana's SQLite DB (users, prefs, any dashboards you add) |
| `/data/nodered` | `flows.json`, credentials, Node-RED settings |

That volume is keyed to the app's slug and is kept when the app is stopped,
restarted, or **updated** - a new version reuses the same volume, so your
message history carries over. Two things do discard it: **uninstalling** the
app, and installing it under a different slug (a local copy used for testing
gets its own empty volume, and nothing migrates between the two).

Home Assistant backups include `/data`, so a full log history is backed up
along with the app - which also means backups grow with `retention_days`. If
that gets unwieldy, `backup_exclude` in `config.yaml` can leave the Loki
chunks out, at the cost of not restoring history with the app.

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
- **The Log tab shows `Connected to broker` / `Disconnected from broker`
  repeating every ~15 seconds, even though the credentials are right:** two
  MQTT clients are sharing one client id, and the broker closes the older
  session every time the other one reconnects. Confirm it in the Mosquitto
  broker app's own log - it prints `Client <id> already connected, closing
  old connection.` The usual cause is the pre-app version of this project,
  whose flow you imported by hand into your own Node-RED and which used the
  same client id; delete or disable that flow, since this app now runs its
  own copy internally. Any other MQTT client reusing the id
  `ha-mqtt-logger-addon` does the same thing.

## Known limitations

- **armv7 / armhf builds are best-effort.** Home Assistant Supervisor
  dropped 32-bit architecture support in the 2025.12 release line; current
  Supervisor versions on 64-bit hardware only need `amd64`/`aarch64`. The
  32-bit images are built separately, aren't covered by the same CI
  guarantees, and may stop building entirely if upstream Node-RED/Loki/
  Grafana images drop 32-bit support first.
- Grafana is reached through Home Assistant's Ingress proxy, which serves the
  app under a per-install path prefix and strips that prefix again before the
  request reaches Grafana. The app reads its own prefix at startup and hands
  it to Grafana as `root_url`, so Grafana's asset URLs line up. If you ever
  see the panel load unstyled or blank after an update, that pairing is the
  first thing to check in the app's **Log** tab.

## How to contribute

* [Open an issue](https://github.com/igrowing/SimplyNet/issues) if you found a bug or want a new feature.

*  <a href="https://www.buymeacoffee.com/igrowing" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a> if you like the app and it makes your life a bit simpler.
