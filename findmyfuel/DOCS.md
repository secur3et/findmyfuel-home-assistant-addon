# Find My Fuel

Find My Fuel is a Home Assistant add-on that runs the Fuel Finder cache locally, keeps the UK government forecourt dataset in SQLite, and exposes Home Assistant-friendly endpoints for one or more tracked entities.

You do not need a separate mobile app for this add-on itself. If you want results based on where you are right now, Home Assistant just needs some entity that already has live coordinates. The easiest source is usually the Home Assistant Companion App, but any `person.*` or `device_tracker.*` entity with `latitude` and `longitude` attributes will work.

## How It Works

1. The add-on authenticates against the Fuel Finder API using your information-recipient client ID and client secret.
2. It downloads and caches station data and fuel prices into `/data/fuel_finder.db`.
3. For each configured target, it asks Home Assistant Core for the current entity state through the supervisor proxy.
4. It reads the entity's `latitude` and `longitude`.
5. It finds the cheapest nearby station for that target's preferred fuel type.
6. It exposes a flat JSON summary at `/ha/targets/<slug>` for Home Assistant REST sensors.

The add-on is not tied to the currently logged-in dashboard viewer. Instead, you choose which entities to track. That makes it predictable and works well for several people or vehicles.

## No Separate App Required

You only need the Home Assistant Companion App if you want live phone location and you do not already have another location source.

Use these options:

- `person.alice` if Home Assistant already combines Alice's trackers into a person entity
- `device_tracker.pixel_9` if you want to bind directly to a phone tracker
- `device_tracker.work_van` if you track a vehicle separately

If the chosen entity is unavailable or does not expose coordinates, that target will return an unavailable/error state without breaking the rest of the add-on.

## Configuration

Required:

- `fuel_finder_client_id`
- `fuel_finder_client_secret`

Main runtime options:

- `refresh_interval_minutes`: background refresh cadence, default `30`
- `include_temporarily_closed`: include temporarily closed forecourts, default `false`
- `listen_port`: API port, default `8099`

Each entry in `targets` defines one Home Assistant-facing fuel summary:

- `slug`: stable identifier used in `/ha/targets/<slug>`
- `entity_id`: `person.*` or `device_tracker.*` entity to read coordinates from
- `friendly_name`: user-facing name for dashboards and sensor labels
- `fuel_type`: Fuel Finder fuel code like `E10`, `E5`, or `B7_STANDARD`
- `radius_km`: search radius for this target
- `limit`: how many nearby matches to inspect

Example:

```yaml
fuel_finder_client_id: YOUR_CLIENT_ID
fuel_finder_client_secret: YOUR_CLIENT_SECRET
refresh_interval_minutes: 30
include_temporarily_closed: false
targets:
  - slug: alice_car
    entity_id: person.alice
    friendly_name: Alice Car
    fuel_type: E10
    radius_km: 10
    limit: 5
  - slug: van
    entity_id: device_tracker.work_van
    friendly_name: Work Van
    fuel_type: B7_STANDARD
    radius_km: 20
    limit: 5
```

## Finding The Right Entity ID

In Home Assistant:

1. Go to **Developer Tools**.
2. Open **States**.
3. Search for a `person.*` or `device_tracker.*` entity.
4. Confirm the entity exposes `latitude` and `longitude`.
5. Copy the entity ID into the add-on config.

If you want phone-based “near me” results, the usual path is:

1. Install the Home Assistant Companion App on your phone.
2. Sign in to your Home Assistant instance.
3. Enable location permissions.
4. Use the resulting `device_tracker.*` or `person.*` entity in the add-on.

## Endpoints

The add-on keeps the existing service endpoints:

- `GET /health`
- `POST /refresh`
- `GET /debug/raw/prices`
- `GET /debug/raw/pfs`
- `GET /nearby`

And adds Home Assistant-specific endpoints:

- `GET /ha/targets`
- `GET /ha/targets/<slug>`

`/ha/targets/<slug>` returns a flat JSON payload designed for Home Assistant REST sensors. When a target succeeds, it includes:

- `price_ppl`
- `station_name`
- `brand_name`
- `address`
- `address_line_1`
- `address_line_2`
- `city`
- `county`
- `country`
- `postcode`
- `distance_km`
- `fuel_type`
- `price_last_updated`
- `price_change_effective_timestamp`
- `last_sync_at`

## Home Assistant REST Sensor Example

Add this to `configuration.yaml` or a package:

```yaml
rest:
  - resource: http://local-findmyfuel:8099/ha/targets/alice_car
    scan_interval: 300
    timeout: 15
    sensor:
      - name: Alice Cheapest Fuel
        unique_id: alice_cheapest_fuel
        value_template: >-
          {% if value_json.status == 'ok' %}
            {{ value_json.price_ppl }}
          {% else %}
            {{ value_json.status }}
          {% endif %}
        unit_of_measurement: "ppl"
        json_attributes:
          - station_name
          - brand_name
          - address
          - address_line_1
          - address_line_2
          - city
          - county
          - country
          - postcode
          - distance_km
          - fuel_type
          - price_last_updated
          - price_change_effective_timestamp
          - last_sync_at
          - source_entity_friendly_name
          - source_entity_state
          - status
          - error
```

Optional template sensors for cleaner cards:

```yaml
template:
  - sensor:
      - name: Alice Cheapest Fuel Station
        state: "{{ state_attr('sensor.alice_cheapest_fuel', 'station_name') }}"
      - name: Alice Cheapest Fuel Address
        state: "{{ state_attr('sensor.alice_cheapest_fuel', 'address') }}"
      - name: Alice Cheapest Fuel Distance
        unit_of_measurement: "km"
        state: "{{ state_attr('sensor.alice_cheapest_fuel', 'distance_km') }}"
```

## Installation From A Local Add-on Repository

1. Copy this repository somewhere Home Assistant can access it as an add-on repository.
2. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
3. Open the menu and choose **Repositories**.
4. Add the repository URL or local repository path you use for custom add-ons.
5. Open **Find My Fuel**.
6. Fill in your Fuel Finder credentials and targets.
7. Start the add-on.

## Common Failure Cases

- Missing credentials:
  The add-on cannot authenticate with Fuel Finder.
- Entity not found:
  The configured `entity_id` does not exist in Home Assistant.
- Missing coordinates:
  The entity exists, but it does not expose `latitude` and `longitude`.
- No results:
  No stations with the chosen fuel type were found inside the configured radius.
- Stale sync:
  Fuel Finder refreshes are failing or the API is temporarily unavailable. Check `/health` and add-on logs.

## Why SQLite

SQLite is the right default here because the add-on is one local service with a single local cache and read-heavy lookups. It keeps the add-on self-contained and stores everything under `/data` so backups stay simple.
