from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import os
from typing import Any

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class TargetSettings:
    slug: str
    entity_id: str
    friendly_name: str
    fuel_type: str
    radius_km: float
    limit: int


@dataclass(slots=True)
class Settings:
    client_id: str | None
    client_secret: str | None
    db_path: Path
    api_base_url: str = "https://www.fuel-finder.service.gov.uk"
    oauth_base_url: str = "https://www.fuel-finder.service.gov.uk"
    oauth_token_path: str = "/api/v1/oauth/generate_access_token"
    oauth_scope: str | None = "fuelfinder.read"
    station_path: str = "/api/v1/pfs"
    price_path: str = "/api/v1/pfs/fuel-prices"
    request_timeout_seconds: float = 30.0
    refresh_interval_minutes: int = 30
    include_temporarily_closed: bool = False
    home_assistant_api_base_url: str = "http://supervisor/core/api"
    home_assistant_token: str | None = None
    targets: tuple[TargetSettings, ...] = ()
    user_agent: str = "findmyfuel-prototype/0.1"

    @property
    def credentials_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def home_assistant_available(self) -> bool:
        return bool(self.home_assistant_token)


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _target_from_dict(payload: dict[str, Any]) -> TargetSettings:
    slug = str(payload.get("slug", "")).strip()
    entity_id = str(payload.get("entity_id", "")).strip()
    fuel_type = str(payload.get("fuel_type", "")).strip().upper()
    if not slug:
        raise ValueError("Each target must define a non-empty slug.")
    if not entity_id:
        raise ValueError(f"Target '{slug}' must define an entity_id.")
    if not fuel_type:
        raise ValueError(f"Target '{slug}' must define a fuel_type.")
    friendly_name = str(payload.get("friendly_name") or slug.replace("_", " ").title()).strip()
    radius_km = float(payload.get("radius_km", 10))
    limit = int(payload.get("limit", 10))
    if radius_km <= 0:
        raise ValueError(f"Target '{slug}' must use a positive radius_km.")
    if limit <= 0:
        raise ValueError(f"Target '{slug}' must use a positive limit.")
    return TargetSettings(
        slug=slug,
        entity_id=entity_id,
        friendly_name=friendly_name,
        fuel_type=fuel_type,
        radius_km=radius_km,
        limit=limit,
    )


def _parse_targets(raw_value: str | None) -> tuple[TargetSettings, ...]:
    if not raw_value:
        return ()
    payload = json.loads(raw_value)
    if not isinstance(payload, list):
        raise ValueError("FUEL_FINDER_TARGETS_JSON must contain a JSON list.")
    targets = tuple(_target_from_dict(item) for item in payload)
    slugs = [target.slug for target in targets]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Target slugs must be unique.")
    return targets


def load_settings() -> Settings:
    load_dotenv()
    db_path = Path(os.getenv("FUEL_FINDER_DB_PATH", "data/fuel_finder.db"))
    return Settings(
        client_id=os.getenv("FUEL_FINDER_CLIENT_ID"),
        client_secret=os.getenv("FUEL_FINDER_CLIENT_SECRET"),
        db_path=db_path,
        api_base_url=os.getenv(
            "FUEL_FINDER_API_BASE_URL", "https://www.fuel-finder.service.gov.uk"
        ),
        oauth_base_url=os.getenv(
            "FUEL_FINDER_OAUTH_BASE_URL", "https://www.fuel-finder.service.gov.uk"
        ),
        oauth_token_path=os.getenv(
            "FUEL_FINDER_OAUTH_TOKEN_PATH", "/api/v1/oauth/generate_access_token"
        ),
        oauth_scope=os.getenv("FUEL_FINDER_OAUTH_SCOPE", "fuelfinder.read") or None,
        station_path=os.getenv("FUEL_FINDER_STATION_PATH", "/api/v1/pfs"),
        price_path=os.getenv(
            "FUEL_FINDER_PRICE_PATH", "/api/v1/pfs/fuel-prices"
        ),
        request_timeout_seconds=float(
            os.getenv("FUEL_FINDER_REQUEST_TIMEOUT_SECONDS", "30")
        ),
        refresh_interval_minutes=int(
            os.getenv("FUEL_FINDER_REFRESH_INTERVAL_MINUTES", "30")
        ),
        include_temporarily_closed=_env_bool(
            "FUEL_FINDER_INCLUDE_TEMPORARILY_CLOSED", False
        ),
        home_assistant_api_base_url=os.getenv(
            "FUEL_FINDER_HOME_ASSISTANT_API_BASE_URL", "http://supervisor/core/api"
        ),
        home_assistant_token=os.getenv("FUEL_FINDER_HOME_ASSISTANT_TOKEN")
        or os.getenv("SUPERVISOR_TOKEN"),
        targets=_parse_targets(os.getenv("FUEL_FINDER_TARGETS_JSON")),
    )
