#!/usr/bin/with-contenv bashio
set -euo pipefail

export OVERLOOKCAM_INSTALLATION_STATE="/data/installation.json"
export OVERLOOKCAM_RELAY_PLATFORM="home-assistant"
export OVERLOOKCAM_RELAY_VERSION="0.2.3"

bashio::log.info "Starting OverlookCam Relay manager"
cd /opt/overlookcam
exec python3 manager.py
