# HA MQTT Logger

Logs every MQTT message seen by your Home Assistant broker into Loki, then
gives you two Grafana panels to see which devices are online and to search
the raw message history — filterable by device and topic.

## Architecture

```
MQTT broker (core-mosquitto)
   -> Node-RED  ("MQTT -> Loki Logger" flow: filter, label, forward)
        -> Loki (log storage)
             -> Grafana ("MQTT Devices" dashboard)
```

This repo holds the two source-of-truth files you import into your own
Home Assistant instance:

- [node-red/flows.json](node-red/flows.json) — the Node-RED flow that
  subscribes to every MQTT topic, drops noise, labels each message, and
  ships it to Loki.
- [grafana/dashboards/mqtt_devices.json](grafana/dashboards/mqtt_devices.json) —
  the Grafana dashboard with the device-status table and the message browser.


## Prerequisites

- Home Assistant OS or Supervised (so you have access to the Add-on Store).
- Admin access to Settings → Add-ons and Settings → People → Users.

You need four things running: an MQTT broker, Node-RED, Loki, and Grafana.
If you only have HA itself, install all four as below.

## 1. MQTT broker

If you don't already have one, install the official **Mosquitto broker**
add-on (Settings → Add-ons → Add-on Store → Official add-ons). Start it,
and enable **Start on boot**. Its internal hostname is always
`core-mosquitto` on port `1883` — the Node-RED flow already assumes this.

Node-RED needs its own MQTT login (it can't use HA's Supervisor token like
other add-ons do). Create a dedicated user for it under
Settings → People → Users → Add User, with a password — don't reuse your own
admin account.



## 2. Loki

Home Assistant doesn't bundle an official Loki add-on. Two options:

- Settings → Add-ons → Add-on Store → ⋮ → Repositories → Add → https://github.com/bluemaex/home-assistant-addons
- Return to App store.
- Search for "Loki" and install it.


Whichever you choose, note:
- its internal hostname/IP and port (default Loki port is `3100`) — this
  is what you plug into `LOKI_URL` above and into the Grafana datasource
  in step 4.
- enable **Start on boot** and **Watchdog** (if it's an HA add-on) so it
  survives reboots and restarts itself if it crashes.


## 3. Node-RED

Install the **Node-RED** add-on. Start it once so it
initializes, then open its web UI.

### Disable the HTTPS requirement

The add-on ships configured for HTTPS by default (`ssl: true`), which
expects certificate files you probably haven't set up (e.g. via the
Let's Encrypt add-on). Since this Node-RED instance only needs to be
reachable from inside your own Home Assistant network — not the
internet — switch it to plain HTTP instead of provisioning certs:

1. Node-RED add-on → **Configuration** tab.
2. Set `ssl` to `false` (the `certfile`/`keyfile` fields are ignored
   once `ssl` is off). **Save**.
3. On "Info" tab in "Controls" pane enable:
    - Start on boot
    - Watchdog
    - Show in sidebar
4. **Start** or **Restart** the add-on.
5. On a sidebar click on "Node-RED".
6. Open the hamburger menu (top right) → **Import**, and paste/upload
   [node-red/flows.json](node-red/flows.json). Import it as a **new flow tab**.
7. Double-click the **MQTT #** node → open the broker config (pencil icon
   next to "HA Mosquitto") → under the **Security** tab, enter the
   username/password you created in step 1. Server should already be
   `core-mosquitto`, port `1883`.
8. Set the Loki endpoint: right-click the flow tab (**MQTT -> Loki
   Logger**) → **Edit flow** → **Environment Variables** tab → set
   `LOKI_URL` to your Loki add-on's push endpoint, e.g.
   `http://<your_homeassistant_ip_or_hostname>:3100/loki/api/v1/push` (see step 2 for the
   hostname).
9. Click **Deploy**.

Watch the **"running totals"** node in the debug sidebar — its status badge
should start counting up as MQTT traffic flows through.

## 4. Grafana

Install a **Grafana** add-on. Start it, enable **Start on
boot** and **Watchdog**, then open its web UI (default login `admin` /
`admin`, change the password when prompted).

1. Add the datasource: **Connections → Data sources → Add data source →
   Loki**. Set the URL to `http://<your_homeassistant_ip_or_hostname>:3100` (same host you set in
   `LOKI_URL`, without the `/loki/api/v1/push` path). Save & test.
2. Import the dashboard: **Dashboards → New → Import → Upload dashboard
   JSON file**, select
   [grafana/dashboards/mqtt_devices.json](grafana/dashboards/mqtt_devices.json).
   When prompted for the **Loki** input, pick the datasource you just
   created, then **Import**.

You should now see the **MQTT Devices** dashboard with:
- **MQTT devices** — one row per device, green/red "Online" status based
  on whether it's logged a message in the last 10 minutes, OR its last
  known `.../availability`, `.../online`, or `.../status` payload
  (retained LWT, looked back over 24h) says online/true — plus last topic
  and last message seen.
- **MQTT messages** — a searchable table of raw messages, filterable by
  the dashboard's time range plus the **Device** and **MQTT Topic**
  dropdowns at the top (both multi-select, default to all; the Topic list
  narrows to whichever device(s) you have selected).

## Verifying end-to-end

1. Publish a test MQTT message (e.g. via Developer Tools → Actions →
   `mqtt.publish` in Home Assistant, or any MQTT client) to any topic that
   isn't under `homeassistant/`, `$SYS/`, `discovery/`, or `tasmota/`.
2. In Node-RED, confirm the debug sidebar's running-totals counter
   increments.
3. In Grafana, open **Explore**, pick the Loki datasource, and query
   `{source="mqtt"}` — your test message should appear.
4. Open the **MQTT Devices** dashboard and confirm the device shows up.

## Keeping it running

Enable **Start on boot** and **Watchdog** on the Node-RED, Loki, and
Grafana add-ons (Mosquitto has these by default). Watchdog makes Supervisor
restart an add-on automatically if it crashes or gets OOM-killed — it
won't help if you stop an add-on manually, but it recovers from real
crashes without you noticing a gap in the logs.

## Troubleshooting

- **A device/topic you know is active doesn't show up in Grafana's
  filters or table:** check the flow's error stream in Loki —
  `{source="mqtt-logger", type="error", device="<device>"}` — for push
  failures (e.g. oversized payloads hitting Loki's line-size limit).
- **The "Online" column shows nothing / flickers:** this comes from
  joining two Loki queries by the `device` field; if you ever edit the
  panel's transformations, make sure the instant query's labels are
  converted to real fields (`labelsToFields`) before the `joinByField`
  step, otherwise the join silently drops that data.
- **Node-RED stops logging and the gap coincides with the add-on being
  down:** check Settings → Add-ons → Node-RED → Log for a crash/OOM
  around that time, and Settings → System → Logs (Supervisor/Host) for
  out-of-memory kills. Confirm Watchdog is enabled so it self-recovers.
