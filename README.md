# OverlookCam Home Assistant Add-on Repository

This is the public Home Assistant add-on repository for **OverlookCam Relay**.

OverlookCam Relay connects Frigate MQTT events on your local network to the hosted OverlookCam Push Service so supported OverlookCam apps can receive event notifications.

## Installation

1. In Home Assistant, open **Settings > Apps > App store** (called **Add-ons** on older Home Assistant versions).
2. Open the repository menu and add:

   `https://github.com/OverlookCam/OverlookCam-home-assistant`

3. Install **OverlookCam Relay**.
4. Start the app and enable **Start on boot**.
5. Open the add-on's **Web UI**.
6. Add the Frigate installation(s) you want OverlookCam to monitor.

The Web UI supports any number of Frigate installations. Each source can use its own MQTT broker credentials and can optionally limit notifications to a comma-separated list of Frigate camera IDs.

## Home Assistant Web UI

Version 0.2.0 and later uses Home Assistant ingress instead of exposing a fixed add-on Configuration form. From the Web UI you can:

- Add and remove Frigate installations.
- Configure each MQTT host, port, username, password, and topic.
- Limit a source to selected camera IDs.
- Save the configuration and restart the relay.
- Generate an OverlookCam pairing code.
- Generate an OverlookCam account claim code.

Relay configuration is stored persistently under the add-on data directory and existing legacy Home/Store or Primary/Secondary settings are migrated when possible.

## Cloud service

The relay registers with the hosted OverlookCam Push Service at:

`https://push.overlookcam.com`

Its installation identity is stored persistently in the Home Assistant app data directory.

## Architectures

- amd64
- aarch64
- armv7

## Source

This public repository intentionally contains the runtime required to build the Home Assistant add-on. A customer Home Assistant installation therefore does not require access to OverlookCam's private application repository.
