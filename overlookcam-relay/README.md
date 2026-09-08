# OverlookCam Relay

OverlookCam Relay listens for Frigate events over MQTT and submits supported events to the hosted OverlookCam Push Service.

## Setup

After installing and starting the add-on, open **Web UI** from the add-on's Info page.

The Web UI is the primary configuration interface. It lets you add or remove as many Frigate installations as you need. Each Frigate installation can use its own:

- Display name
- MQTT host and port
- MQTT username and password
- Frigate MQTT event topic
- Optional camera filter

The default Frigate event topic is `frigate/events`.

Leave the camera filter blank to accept events from every camera on that Frigate installation, or enter a comma-separated list of Frigate camera IDs.

After making changes, choose **Save & restart relay**. The status indicator at the top of the Web UI will show whether the relay process is running.

## OverlookCam account

The Web UI can generate either:

- A pairing code for the OverlookCam app
- An account claim code for the OverlookCam account portal

The relay keeps its installation identity across restarts and updates.

## Networking

The add-on uses host networking so it can connect directly to MQTT brokers reachable from the Home Assistant host.

## Persistence

Relay configuration is stored in the add-on data directory. The OverlookCam installation identity is persisted under `/data/installation.json`, so restarting or updating the add-on keeps the same cloud installation identity.

## Multiple Frigate installations

There is no fixed Home/Store or primary/secondary limit. Use **+ Add Frigate installation** in the Web UI whenever another Frigate server needs to be connected.
