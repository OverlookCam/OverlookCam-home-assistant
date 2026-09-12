# Changelog

## 0.2.7

- Fixed Reolink floodlight authentication when camera credentials contain characters such as `!`.
- Improved reliability of Patio/floodlight camera controls used by the OverlookCam mobile app.

## 0.2.6

- Added Reolink floodlight camera controls for compatible cameras.
- Added Home Assistant add-on options for floodlight camera connection settings.
- Kept pet notification forwarding enabled for `person`, `dog`, and `cat` detections.

## 0.2.5

- Added `dog` and `cat` to the relay's default notification labels alongside `person`.
- Fixed pet detections being dropped by the Home Assistant relay before reaching OverlookCam Push.
