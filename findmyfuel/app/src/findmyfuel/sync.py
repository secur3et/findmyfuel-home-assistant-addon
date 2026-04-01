from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from findmyfuel.client import FuelFinderApiError, FuelFinderClient
from findmyfuel.db import FuelFinderRepository, utc_now_iso


class SyncService:
    def __init__(self, repository: FuelFinderRepository, client: FuelFinderClient) -> None:
        self.repository = repository
        self.client = client

    def refresh(self) -> dict[str, Any]:
        state = self.repository.get_sync_state()
        last_success = state.get("last_successful_sync_at")
        try:
            if last_success:
                return self._incremental_refresh(_parse_stored_timestamp(last_success))
            return self._full_refresh()
        except Exception as exc:
            self.repository.update_sync_state(last_error=str(exc))
            raise

    def _full_refresh(self) -> dict[str, Any]:
        started_at = utc_now_iso()
        station_summary = self._consume_pages(
            lambda batch_number: self.client.fetch_station_page(batch_number=batch_number),
            sink=self.repository.upsert_station_page,
        )
        price_summary = self._consume_pages(
            lambda batch_number: self.client.fetch_price_page(batch_number=batch_number),
            sink=self.repository.upsert_price_page,
        )
        completed_at = utc_now_iso()
        self.repository.update_sync_state(
            last_full_sync_at=completed_at,
            last_incremental_sync_at=completed_at,
            last_successful_sync_at=completed_at,
            last_sync_mode="full",
            last_error=None,
            last_station_batch_count=station_summary["batches"],
            last_price_batch_count=price_summary["batches"],
        )
        return {
            "mode": "full",
            "started_at": started_at,
            "completed_at": completed_at,
            "stations": station_summary,
            "prices": price_summary,
        }

    def _incremental_refresh(self, effective_start_timestamp: datetime) -> dict[str, Any]:
        started_at = utc_now_iso()
        station_summary = self._consume_pages(
            lambda batch_number: self.client.fetch_station_page(
                batch_number=batch_number,
                effective_start_timestamp=effective_start_timestamp,
            ),
            sink=self.repository.upsert_station_page,
        )
        price_summary = self._consume_pages(
            lambda batch_number: self.client.fetch_price_page(
                batch_number=batch_number,
                effective_start_timestamp=effective_start_timestamp,
            ),
            sink=self.repository.upsert_price_page,
        )
        completed_at = utc_now_iso()
        self.repository.update_sync_state(
            last_incremental_sync_at=completed_at,
            last_successful_sync_at=completed_at,
            last_sync_mode="incremental",
            last_error=None,
            last_station_batch_count=station_summary["batches"],
            last_price_batch_count=price_summary["batches"],
        )
        return {
            "mode": "incremental",
            "effective_start_timestamp": effective_start_timestamp.isoformat(),
            "started_at": started_at,
            "completed_at": completed_at,
            "stations": station_summary,
            "prices": price_summary,
        }

    def _consume_pages(
        self,
        fetch_page: Callable[[int], list[dict[str, Any]]],
        *,
        sink: Callable[[list[dict[str, Any]]], None],
    ) -> dict[str, int]:
        batches = 0
        records = 0
        batch_number = 1
        while True:
            try:
                page = fetch_page(batch_number)
            except FuelFinderApiError as exc:
                if exc.status_code == 404:
                    break
                raise
            sink(page)
            batches += 1
            records += len(page)
            batch_number += 1
        return {"batches": batches, "records": records}


def _parse_stored_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
