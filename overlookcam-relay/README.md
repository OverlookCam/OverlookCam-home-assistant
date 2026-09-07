# OverlookCam Relay

OverlookCam Relay listens for Frigate events over MQTT and submits supported events to the hosted OverlookCam Push Service.

## Configuration

The **Home** source is required. Enter the MQTT host, port, username, password, and topic used by your Frigate installation. The default Frigate event topic is `frigate/events`.

Enable the optional **Store** source only when a second Frigate installation needs to be connected through this relay.

`source_*_push_cameras` may be left blank to accept every camera, or set to a comma-separated list of Frigate camera IDs.

## Networking

The add-on uses host networking so it can connect directly to MQTT brokers on the Home Assistant host's local network.

## Persistence

The OverlookCam installation identity is persisted under `/data/installation.json`, so restarting or updating the add-on keeps the same cloud installation identity.
