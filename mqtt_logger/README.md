# MQTT Logger

Logs every MQTT message on your Home Assistant broker to Loki and browses it
in a built-in Grafana dashboard - which devices are online, and a searchable
message history filterable by device and topic. A small Python logger, Loki,
and Grafana all run inside this one app; nothing else to install or wire up
by hand.
