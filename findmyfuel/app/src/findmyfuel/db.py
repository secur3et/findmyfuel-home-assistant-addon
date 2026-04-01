from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
import sqlite3
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    a = sin(d_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(d_lon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else [], separators=(",", ":"))


def _display_address(row: sqlite3.Row) -> str:
    parts = [
        row["address_line_1"],
        row["address_line_2"],
        row["city"],
        row["county"],
        row["postcode"],
        row["country"],
    ]
    return ", ".join(str(part).strip() for part in parts if part)


class FuelFinderRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._managed_connection() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS stations (
                    node_id TEXT PRIMARY KEY,
                    trading_name TEXT,
                    brand_name TEXT,
                    public_phone_number TEXT,
                    is_same_trading_and_brand_name INTEGER NOT NULL DEFAULT 0,
                    temporary_closure INTEGER NOT NULL DEFAULT 0,
                    permanent_closure INTEGER NOT NULL DEFAULT 0,
                    permanent_closure_date TEXT,
                    is_motorway_service_station INTEGER NOT NULL DEFAULT 0,
                    is_supermarket_service_station INTEGER NOT NULL DEFAULT 0,
                    address_line_1 TEXT,
                    address_line_2 TEXT,
                    city TEXT,
                    country TEXT,
                    county TEXT,
                    postcode TEXT,
                    latitude REAL,
                    longitude REAL,
                    amenities_json TEXT NOT NULL DEFAULT '[]',
                    opening_times_json TEXT NOT NULL DEFAULT '{}',
                    fuel_types_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS prices (
                    node_id TEXT NOT NULL,
                    fuel_type TEXT NOT NULL,
                    price REAL NOT NULL,
                    price_last_updated TEXT,
                    price_change_effective_timestamp TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (node_id, fuel_type),
                    FOREIGN KEY (node_id) REFERENCES stations (node_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sync_state (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    last_full_sync_at TEXT,
                    last_incremental_sync_at TEXT,
                    last_successful_sync_at TEXT,
                    last_sync_mode TEXT,
                    last_error TEXT,
                    last_station_batch_count INTEGER NOT NULL DEFAULT 0,
                    last_price_batch_count INTEGER NOT NULL DEFAULT 0
                );

                INSERT OR IGNORE INTO sync_state (singleton_id) VALUES (1);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _managed_connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def upsert_station_page(self, stations: list[dict[str, Any]]) -> None:
        now = utc_now_iso()
        rows = []
        for station in stations:
            location = station.get("location") or {}
            rows.append(
                (
                    station["node_id"],
                    station.get("trading_name"),
                    station.get("brand_name"),
                    station.get("public_phone_number"),
                    int(bool(station.get("is_same_trading_and_brand_name"))),
                    int(bool(station.get("temporary_closure"))),
                    int(bool(station.get("permanent_closure"))),
                    station.get("permanent_closure_date"),
                    int(bool(station.get("is_motorway_service_station"))),
                    int(bool(station.get("is_supermarket_service_station"))),
                    location.get("address_line_1"),
                    location.get("address_line_2"),
                    location.get("city"),
                    location.get("country"),
                    location.get("county"),
                    location.get("postcode"),
                    location.get("latitude"),
                    location.get("longitude"),
                    _json_dumps(station.get("amenities") or []),
                    json.dumps(
                        station.get("opening_times") or {}, separators=(",", ":")
                    ),
                    _json_dumps(station.get("fuel_types") or []),
                    now,
                )
            )

        with self._managed_connection() as connection:
            connection.executemany(
                """
                INSERT INTO stations (
                    node_id,
                    trading_name,
                    brand_name,
                    public_phone_number,
                    is_same_trading_and_brand_name,
                    temporary_closure,
                    permanent_closure,
                    permanent_closure_date,
                    is_motorway_service_station,
                    is_supermarket_service_station,
                    address_line_1,
                    address_line_2,
                    city,
                    country,
                    county,
                    postcode,
                    latitude,
                    longitude,
                    amenities_json,
                    opening_times_json,
                    fuel_types_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    trading_name = excluded.trading_name,
                    brand_name = excluded.brand_name,
                    public_phone_number = excluded.public_phone_number,
                    is_same_trading_and_brand_name = excluded.is_same_trading_and_brand_name,
                    temporary_closure = excluded.temporary_closure,
                    permanent_closure = excluded.permanent_closure,
                    permanent_closure_date = excluded.permanent_closure_date,
                    is_motorway_service_station = excluded.is_motorway_service_station,
                    is_supermarket_service_station = excluded.is_supermarket_service_station,
                    address_line_1 = excluded.address_line_1,
                    address_line_2 = excluded.address_line_2,
                    city = excluded.city,
                    country = excluded.country,
                    county = excluded.county,
                    postcode = excluded.postcode,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    amenities_json = excluded.amenities_json,
                    opening_times_json = excluded.opening_times_json,
                    fuel_types_json = excluded.fuel_types_json,
                    updated_at = excluded.updated_at
                """,
                rows,
            )

    def upsert_price_page(self, price_records: list[dict[str, Any]]) -> None:
        now = utc_now_iso()
        rows = []
        for station in price_records:
            for fuel_price in station.get("fuel_prices") or []:
                rows.append(
                    (
                        station["node_id"],
                        fuel_price["fuel_type"],
                        fuel_price["price"],
                        fuel_price.get("price_last_updated"),
                        fuel_price.get("price_change_effective_timestamp"),
                        now,
                    )
                )

        with self._managed_connection() as connection:
            connection.executemany(
                """
                INSERT INTO prices (
                    node_id,
                    fuel_type,
                    price,
                    price_last_updated,
                    price_change_effective_timestamp,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id, fuel_type) DO UPDATE SET
                    price = excluded.price,
                    price_last_updated = excluded.price_last_updated,
                    price_change_effective_timestamp = excluded.price_change_effective_timestamp,
                    updated_at = excluded.updated_at
                """,
                rows,
            )

    def counts(self) -> dict[str, int]:
        with self._managed_connection() as connection:
            stations = connection.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
            prices = connection.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        return {"stations": stations, "prices": prices}

    def get_sync_state(self) -> dict[str, Any]:
        with self._managed_connection() as connection:
            row = connection.execute(
                """
                SELECT
                    last_full_sync_at,
                    last_incremental_sync_at,
                    last_successful_sync_at,
                    last_sync_mode,
                    last_error,
                    last_station_batch_count,
                    last_price_batch_count
                FROM sync_state
                WHERE singleton_id = 1
                """
            ).fetchone()
        return dict(row)

    def update_sync_state(
        self,
        *,
        last_full_sync_at: str | None = None,
        last_incremental_sync_at: str | None = None,
        last_successful_sync_at: str | None = None,
        last_sync_mode: str | None = None,
        last_error: str | None = None,
        last_station_batch_count: int | None = None,
        last_price_batch_count: int | None = None,
    ) -> None:
        current = self.get_sync_state()
        payload = {
            "last_full_sync_at": (
                last_full_sync_at
                if last_full_sync_at is not None
                else current["last_full_sync_at"]
            ),
            "last_incremental_sync_at": (
                last_incremental_sync_at
                if last_incremental_sync_at is not None
                else current["last_incremental_sync_at"]
            ),
            "last_successful_sync_at": (
                last_successful_sync_at
                if last_successful_sync_at is not None
                else current["last_successful_sync_at"]
            ),
            "last_sync_mode": (
                last_sync_mode if last_sync_mode is not None else current["last_sync_mode"]
            ),
            "last_error": last_error,
            "last_station_batch_count": (
                last_station_batch_count
                if last_station_batch_count is not None
                else current["last_station_batch_count"]
            ),
            "last_price_batch_count": (
                last_price_batch_count
                if last_price_batch_count is not None
                else current["last_price_batch_count"]
            ),
        }
        with self._managed_connection() as connection:
            connection.execute(
                """
                UPDATE sync_state
                SET
                    last_full_sync_at = :last_full_sync_at,
                    last_incremental_sync_at = :last_incremental_sync_at,
                    last_successful_sync_at = :last_successful_sync_at,
                    last_sync_mode = :last_sync_mode,
                    last_error = :last_error,
                    last_station_batch_count = :last_station_batch_count,
                    last_price_batch_count = :last_price_batch_count
                WHERE singleton_id = 1
                """,
                payload,
            )

    def find_nearby_stations(
        self,
        *,
        lat: float,
        lon: float,
        fuel_type: str,
        radius_km: float,
        limit: int,
        include_temporarily_closed: bool,
    ) -> list[dict[str, Any]]:
        with self._managed_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    stations.node_id,
                    stations.trading_name,
                    stations.brand_name,
                    stations.address_line_1,
                    stations.address_line_2,
                    stations.city,
                    stations.county,
                    stations.country,
                    stations.postcode,
                    stations.latitude,
                    stations.longitude,
                    stations.temporary_closure,
                    stations.permanent_closure,
                    stations.is_motorway_service_station,
                    stations.amenities_json,
                    prices.fuel_type,
                    prices.price,
                    prices.price_last_updated,
                    prices.price_change_effective_timestamp
                FROM stations
                JOIN prices ON prices.node_id = stations.node_id
                WHERE
                    prices.fuel_type = ?
                    AND stations.permanent_closure = 0
                    AND stations.latitude IS NOT NULL
                    AND stations.longitude IS NOT NULL
                """,
                (fuel_type.upper(),),
            ).fetchall()

        results = []
        for row in rows:
            if row["temporary_closure"] and not include_temporarily_closed:
                continue
            distance_km = haversine_km(lat, lon, row["latitude"], row["longitude"])
            if distance_km > radius_km:
                continue
            results.append(
                {
                    "node_id": row["node_id"],
                    "trading_name": row["trading_name"],
                    "brand_name": row["brand_name"],
                    "address_line_1": row["address_line_1"],
                    "address_line_2": row["address_line_2"],
                    "city": row["city"],
                    "county": row["county"],
                    "country": row["country"],
                    "display_address": _display_address(row),
                    "fuel_type": row["fuel_type"],
                    "price_ppl": row["price"],
                    "distance_km": round(distance_km, 3),
                    "price_last_updated": row["price_last_updated"],
                    "price_change_effective_timestamp": row[
                        "price_change_effective_timestamp"
                    ],
                    "postcode": row["postcode"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "temporary_closure": bool(row["temporary_closure"]),
                    "is_motorway_service_station": bool(
                        row["is_motorway_service_station"]
                    ),
                    "amenities": json.loads(row["amenities_json"]),
                }
            )

        results.sort(
            key=lambda item: (
                item["price_ppl"],
                item["distance_km"],
                -(self._timestamp_sort_key(item["price_last_updated"])),
            )
        )
        return results[:limit]

    @staticmethod
    def _timestamp_sort_key(value: str | None) -> float:
        if not value:
            return 0.0
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
