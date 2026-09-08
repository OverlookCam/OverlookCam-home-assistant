#!/usr/bin/with-contenv bashio
set -euo pipefail

export OVERLOOKCAM_INSTALLATION_STATE="/data/installation.json"
export OVERLOOKCAM_RELAY_PLATFORM="home-assistant"
export OVERLOOKCAM_RELAY_VERSION="0.1.1"

export SOURCE_PRIMARY_ENABLED="true"
export SOURCE_PRIMARY_NAME="$(bashio::config 'primary_name')"
export SOURCE_PRIMARY_MQTT_HOST="$(bashio::config 'primary_mqtt_host')"
export SOURCE_PRIMARY_MQTT_PORT="$(bashio::config 'primary_mqtt_port')"
export SOURCE_PRIMARY_MQTT_USER="$(bashio::config 'primary_mqtt_user')"
export SOURCE_PRIMARY_MQTT_PASSWORD="$(bashio::config 'primary_mqtt_password')"
export SOURCE_PRIMARY_MQTT_TOPIC="$(bashio::config 'primary_mqtt_topic')"
export SOURCE_PRIMARY_PUSH_CAMERAS="$(bashio::config 'primary_push_cameras')"
export SOURCE_PRIMARY_SUPPRESS_DURING_SCHEDULE="false"

export SOURCE_SECONDARY_ENABLED="$(bashio::config 'secondary_enabled')"
export SOURCE_SECONDARY_NAME="$(bashio::config 'secondary_name')"
export SOURCE_SECONDARY_MQTT_HOST="$(bashio::config 'secondary_mqtt_host')"
export SOURCE_SECONDARY_MQTT_PORT="$(bashio::config 'secondary_mqtt_port')"
export SOURCE_SECONDARY_MQTT_USER="$(bashio::config 'secondary_mqtt_user')"
export SOURCE_SECONDARY_MQTT_PASSWORD="$(bashio::config 'secondary_mqtt_password')"
export SOURCE_SECONDARY_MQTT_TOPIC="$(bashio::config 'secondary_mqtt_topic')"
export SOURCE_SECONDARY_PUSH_CAMERAS="$(bashio::config 'secondary_push_cameras')"
export SOURCE_SECONDARY_SUPPRESS_DURING_SCHEDULE="false"

if [[ -z "${SOURCE_PRIMARY_MQTT_HOST}" ]]; then
  bashio::log.fatal "Primary MQTT host is required."
  exit 1
fi

export FRIGATE_SOURCES="primary"
if bashio::config.true 'secondary_enabled'; then
  if [[ -z "${SOURCE_SECONDARY_MQTT_HOST}" ]]; then
    bashio::log.fatal "Secondary MQTT host is required when the secondary Frigate source is enabled."
    exit 1
  fi
  export FRIGATE_SOURCES="primary,secondary"
fi

bashio::log.info "Starting OverlookCam Relay for ${FRIGATE_SOURCES}"
cd /opt/overlookcam
exec python3 relay.py
