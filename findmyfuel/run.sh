#!/usr/bin/with-contenv bashio

set -euo pipefail

export FUEL_FINDER_CLIENT_ID
FUEL_FINDER_CLIENT_ID="$(bashio::config 'fuel_finder_client_id')"

export FUEL_FINDER_CLIENT_SECRET
FUEL_FINDER_CLIENT_SECRET="$(bashio::config 'fuel_finder_client_secret')"

export FUEL_FINDER_API_BASE_URL
FUEL_FINDER_API_BASE_URL="$(bashio::config 'api_base_url')"

export FUEL_FINDER_OAUTH_BASE_URL
FUEL_FINDER_OAUTH_BASE_URL="$(bashio::config 'oauth_base_url')"

export FUEL_FINDER_OAUTH_TOKEN_PATH
FUEL_FINDER_OAUTH_TOKEN_PATH="$(bashio::config 'oauth_token_path')"

export FUEL_FINDER_OAUTH_SCOPE
FUEL_FINDER_OAUTH_SCOPE="$(bashio::config 'oauth_scope')"

export FUEL_FINDER_STATION_PATH
FUEL_FINDER_STATION_PATH="$(bashio::config 'station_path')"

export FUEL_FINDER_PRICE_PATH
FUEL_FINDER_PRICE_PATH="$(bashio::config 'price_path')"

export FUEL_FINDER_REQUEST_TIMEOUT_SECONDS
FUEL_FINDER_REQUEST_TIMEOUT_SECONDS="$(bashio::config 'request_timeout_seconds')"

export FUEL_FINDER_REFRESH_INTERVAL_MINUTES
FUEL_FINDER_REFRESH_INTERVAL_MINUTES="$(bashio::config 'refresh_interval_minutes')"

export FUEL_FINDER_INCLUDE_TEMPORARILY_CLOSED
FUEL_FINDER_INCLUDE_TEMPORARILY_CLOSED="$(bashio::config 'include_temporarily_closed')"

export FUEL_FINDER_TARGETS_JSON
FUEL_FINDER_TARGETS_JSON="$(bashio::config 'targets')"

export FUEL_FINDER_HOME_ASSISTANT_TOKEN="${SUPERVISOR_TOKEN:-}"
export FUEL_FINDER_DB_PATH="/data/fuel_finder.db"

LISTEN_HOST="$(bashio::config 'listen_host')"
LISTEN_PORT="$(bashio::config 'listen_port')"

bashio::log.info "Starting Find My Fuel on ${LISTEN_HOST}:${LISTEN_PORT}"
bashio::log.info "Using SQLite cache at ${FUEL_FINDER_DB_PATH}"
bashio::log.info "Loaded Home Assistant target configuration from add-on options"

exec python3 -m uvicorn findmyfuel.main:app \
  --host "${LISTEN_HOST}" \
  --port "${LISTEN_PORT}"
