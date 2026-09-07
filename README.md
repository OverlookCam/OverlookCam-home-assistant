# OverlookCam Home Assistant Add-on Repository

This is the public Home Assistant add-on repository for **OverlookCam Relay**.

OverlookCam Relay connects Frigate MQTT events on your local network to the hosted OverlookCam Push Service so supported OverlookCam apps can receive event notifications.

## Installation

1. In Home Assistant, open **Settings > Apps > App store** (called **Add-ons** on older Home Assistant versions).
2. Open the repository menu and add:

   `https://github.com/OverlookCam/OverlookCam-home-assistant`

3. Refresh the store if necessary.
4. Install **OverlookCam Relay**.
5. Configure the MQTT connection used by Frigate.
6. Start the app and enable **Start on boot**.

The initial package supports one required Frigate/MQTT source and an optional second source. Each source can use its own MQTT broker credentials and can optionally limit notifications to a comma-separated list of Frigate camera IDs.

## Cloud service

The relay registers with the hosted OverlookCam Push Service at:

`https://push.overlookcam.com`

Its installation identity is stored persistently in the Home Assistant app data directory.

## Pairing and account claim

The relay includes the same pairing and account-claim utilities as the standard OverlookCam Relay distribution. These use the relay's persisted installation identity and the hosted Push Service.

## Architectures

- amd64
- aarch64
- armv7

## Source

This public repository intentionally contains the runtime required to build the Home Assistant add-on. A customer Home Assistant installation therefore does not require access to OverlookCam's private application repository.
