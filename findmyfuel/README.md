# Find My Fuel Add-on

Run the Fuel Finder cache inside Home Assistant and expose per-target fuel summaries for `person.*` and `device_tracker.*` entities.

The add-on:

- syncs UK Fuel Finder station and price data into SQLite
- reads one or more Home Assistant location entities
- returns the cheapest nearby station for each configured target
- works with simple REST and template sensors for dashboards and automations

See [`DOCS.md`](./DOCS.md) for full setup, configuration examples, and Home Assistant YAML snippets.
