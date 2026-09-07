#!/usr/bin/with-contenv bashio
set -euo pipefail

export OVERLOOKCAM_INSTALLATION_STATE="/data/installation.json"
export OVERLOOKCAM_RELAY_PLATFORM="home-assistant"
export OVERLOOKCAM_RELAY_VERSION="0.1.0"

export SOURCE_HOME_ENABLED="true"
export SOURCE_HOME_NAME="$(bashio::config 'source_home_name')"
export SOURCE_HOME_MQTT_HOST="$(bashio::config 'source_home_mqtt_host')"
export SOURCE_HOME_MQTT_PORT="$(bashio::config 'source_home_mqtt_port')"
export SOURCE_HOME_MQTT_USER="$(bashio::config 'source_home_mqtt_user')"
export SOURCE_HOME_MQTT_PASSWORD="$(bashio::config 'source_home_mqtt_password')"
export SOURCE_HOME_MQTT_TOPIC="$(bashio::config 'source_home_mqtt_topic')"
export SOURCE_HOME_PUSH_CAMERAS="$(bashio::config 'source_home_push_cameras')"
export SOURCE_HOME_SUPPRESS_DURING_SCHEDULE="false"

export SOURCE_STORE_ENABLED="$(bashio::config 'source_store_enabled')"
export SOURCE_STORE_NAME="$(bashio::config 'source_store_name')"
export SOURCE_STORE_MQTT_HOST="$(bashio::config 'source_store_mqtt_host')"
export SOURCE_STORE_MQTT_PORT="$(bashio::config 'source_store_mqtt_port')"
export SOURCE_STORE_MQTT_USER="$(bashio::config 'source_store_mqtt_user')"
export SOURCE_STORE_MQTT_PASSWORD="$(bashio::config 'source_store_mqtt_password')"
export SOURCE_STORE_MQTT_TOPIC="$(bashio::config 'source_store_mqtt_topic')"
export SOURCE_STORE_PUSH_CAMERAS="$(bashio::config 'source_store_push_cameras')"
export SOURCE_STORE_SUPPRESS_DURING_SCHEDULE="false"

if [[ -z "${SOURCE_HOME_MQTT_HOST}" ]]; then
  bashio::log.fatal "Home MQTT host is required."
  exit 1
fi

export FRIGATE_SOURCES="home"
if bashio::config.true 'source_store_enabled'; then
  if [[ -z "${SOURCE_STORE_MQTT_HOST}" ]]; then
    bashio::log.fatal "Store MQTT host is required when the Store source is enabled."
    exit 1
  fi
  export FRIGATE_SOURCES="home,store"
fi

bashio::log.info "Starting OverlookCam Relay for ${FRIGATE_SOURCES}"
cd /opt/overlookcam
exec python3 relay.py
