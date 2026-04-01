from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from findmyfuel.config import Settings, TargetSettings
from findmyfuel.db import FuelFinderRepository


class HomeAssistantError(Exception):
    """Base error for Home Assistant API lookup failures."""


class HomeAssistantUnavailableError(HomeAssistantError):
    """Raised when the Home Assistant API is not available to the service."""


class HomeAssistantEntityNotFoundError(HomeAssistantError):
    """Raised when the requested Home Assistant entity does not exist."""


class HomeAssistantEntityLocationError(HomeAssistantError):
    """Raised when an entity has no usable coordinates."""


@dataclass(frozen=True, slots=True)
class EntityCoordinates:
    entity_id: str
    friendly_name: str
    state: str
    latitude: float
    longitude: float


class HomeAssistantClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.home_assistant_api_base_url.rstrip("/"),
            timeout=self.settings.request_timeout_seconds,
            headers={"User-Agent": self.settings.user_agent},
            transport=self._transport,
        )

    def get_entity_coordinates(self, entity_id: str) -> EntityCoordinates:
        if not self.settings.home_assistant_available:
            raise HomeAssistantUnavailableError(
                "Home Assistant API is unavailable. This endpoint requires SUPERVISOR_TOKEN "
                "or FUEL_FINDER_HOME_ASSISTANT_TOKEN."
            )

        with self._http_client() as client:
            response = client.get(
                f"states/{entity_id}",
                headers={"Authorization": f"Bearer {self.settings.home_assistant_token}"},
            )

        if response.status_code == 404:
            raise HomeAssistantEntityNotFoundError(
                f"Home Assistant entity '{entity_id}' was not found."
            )
        if response.status_code >= 400:
            raise HomeAssistantUnavailableError(
                f"Home Assistant API request failed with status {response.status_code}."
            )

        payload = response.json()
        entity_state = str(payload.get("state") or "")
        attributes = payload.get("attributes") or {}
        friendly_name = str(attributes.get("friendly_name") or entity_id)

        if entity_state.lower() in {"unknown", "unavailable"}:
            raise HomeAssistantEntityLocationError(
                f"Home Assistant entity '{entity_id}' is {entity_state}."
            )

        latitude = attributes.get("latitude")
        longitude = attributes.get("longitude")
        if latitude is None or longitude is None:
            raise HomeAssistantEntityLocationError(
                f"Home Assistant entity '{entity_id}' does not expose latitude/longitude."
            )

        return EntityCoordinates(
            entity_id=entity_id,
            friendly_name=friendly_name,
            state=entity_state,
            latitude=float(latitude),
            longitude=float(longitude),
        )


class HomeAssistantTargetService:
    def __init__(
        self,
        settings: Settings,
        repository: FuelFinderRepository,
        home_assistant_client: HomeAssistantClient,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.home_assistant_client = home_assistant_client

    def list_target_summaries(self) -> dict[str, Any]:
        summaries = [self._build_target_summary(target) for target in self.settings.targets]
        return {
            "count": len(summaries),
            "items": summaries,
            "last_sync_at": self.repository.get_sync_state()["last_successful_sync_at"],
        }

    def get_target_summary(self, slug: str) -> dict[str, Any]:
        for target in self.settings.targets:
            if target.slug == slug:
                return self._build_target_summary(target)
        raise KeyError(slug)

    def _build_target_summary(self, target: TargetSettings) -> dict[str, Any]:
        sync_state = self.repository.get_sync_state()
        base_summary = {
            "slug": target.slug,
            "friendly_name": target.friendly_name,
            "entity_id": target.entity_id,
            "fuel_type": target.fuel_type,
            "radius_km": target.radius_km,
            "limit": target.limit,
            "include_temporarily_closed": self.settings.include_temporarily_closed,
            "last_sync_at": sync_state["last_successful_sync_at"],
            "last_sync_mode": sync_state["last_sync_mode"],
            "source_entity_state": None,
            "source_entity_friendly_name": None,
            "source_latitude": None,
            "source_longitude": None,
            "count": 0,
            "status": "unavailable",
            "state": "unavailable",
            "price_ppl": None,
            "station_name": None,
            "brand_name": None,
            "address": None,
            "address_line_1": None,
            "address_line_2": None,
            "city": None,
            "county": None,
            "country": None,
            "postcode": None,
            "distance_km": None,
            "price_last_updated": None,
            "price_change_effective_timestamp": None,
            "error": None,
        }
        try:
            coordinates = self.home_assistant_client.get_entity_coordinates(target.entity_id)
        except HomeAssistantError as exc:
            base_summary["error"] = str(exc)
            return base_summary

        base_summary.update(
            {
                "source_entity_state": coordinates.state,
                "source_entity_friendly_name": coordinates.friendly_name,
                "source_latitude": coordinates.latitude,
                "source_longitude": coordinates.longitude,
            }
        )

        nearby = self.repository.find_nearby_stations(
            lat=coordinates.latitude,
            lon=coordinates.longitude,
            fuel_type=target.fuel_type,
            radius_km=target.radius_km,
            limit=target.limit,
            include_temporarily_closed=self.settings.include_temporarily_closed,
        )
        base_summary["count"] = len(nearby)
        if not nearby:
            base_summary["status"] = "no_results"
            base_summary["state"] = "no_results"
            base_summary["error"] = (
                f"No {target.fuel_type} stations found within {target.radius_km:g} km."
            )
            return base_summary

        station = nearby[0]
        base_summary.update(
            {
                "status": "ok",
                "state": station["price_ppl"],
                "price_ppl": station["price_ppl"],
                "station_name": station["trading_name"],
                "brand_name": station["brand_name"],
                "address": station["display_address"],
                "address_line_1": station["address_line_1"],
                "address_line_2": station["address_line_2"],
                "city": station["city"],
                "county": station["county"],
                "country": station["country"],
                "postcode": station["postcode"],
                "distance_km": station["distance_km"],
                "price_last_updated": station["price_last_updated"],
                "price_change_effective_timestamp": station[
                    "price_change_effective_timestamp"
                ],
                "error": None,
            }
        )
        return base_summary
