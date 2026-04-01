# Find My Fuel Embedded Service

This is the Python service packaged inside the Home Assistant add-on.

It:

- authenticates with the UK Fuel Finder API
- caches forecourt and price data in SQLite
- reads Home Assistant entity coordinates through the supervisor proxy
- exposes nearby fuel lookups and flat `/ha/targets/<slug>` summaries

This README exists so the embedded package can build cleanly from the standalone add-on repository without relying on the larger development project.
