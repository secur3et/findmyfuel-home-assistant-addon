from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any

import httpx

from findmyfuel.config import Settings


class FuelFinderError(Exception):
    """Base error for upstream Fuel Finder failures."""


class FuelFinderAuthError(FuelFinderError):
    """Raised when auth credentials are missing or rejected."""


@dataclass(slots=True)
class FuelFinderApiError(FuelFinderError):
    status_code: int
    message: str
    response_body: str = ""

    def __str__(self) -> str:
        return f"Fuel Finder API error {self.status_code}: {self.message}"


def format_upstream_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class FuelFinderClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._access_token: str | None = None
        self._access_token_expiry: datetime | None = None

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.api_base_url.rstrip("/"),
            timeout=self.settings.request_timeout_seconds,
            headers={"User-Agent": self.settings.user_agent},
            transport=self._transport,
        )

    def _oauth_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.oauth_base_url.rstrip("/"),
            timeout=self.settings.request_timeout_seconds,
            headers={"User-Agent": self.settings.user_agent},
            transport=self._transport,
        )

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        if (
            not force_refresh
            and self._access_token
            and self._access_token_expiry
            and datetime.now(timezone.utc) < self._access_token_expiry
        ):
            return self._access_token

        if not self.settings.credentials_configured:
            raise FuelFinderAuthError(
                "Fuel Finder credentials are missing. Set FUEL_FINDER_CLIENT_ID and "
                "FUEL_FINDER_CLIENT_SECRET."
            )

        response = self._request_access_token()

        if response.status_code == 401:
            raise FuelFinderAuthError("Fuel Finder credentials were rejected by upstream.")
        if response.status_code >= 400:
            raise FuelFinderApiError(
                status_code=response.status_code,
                message="Unable to obtain access token.",
                response_body=response.text,
            )

        payload = response.json()
        token, expires_in = self._parse_access_token_response(payload)
        if not token:
            raise FuelFinderAuthError("Fuel Finder token response did not include an access token.")

        self._access_token = token
        self._access_token_expiry = datetime.now(timezone.utc) + timedelta(
            seconds=max(expires_in - 30, 30)
        )
        return token

    def _request_access_token(self) -> httpx.Response:
        form_payload = {
            "grant_type": "client_credentials",
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
        }
        if self.settings.oauth_scope:
            form_payload["scope"] = self.settings.oauth_scope

        with self._oauth_client() as client:
            response = client.post(
                self.settings.oauth_token_path,
                data=form_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code < 400 or response.status_code == 401:
            return response

        with self._oauth_client() as client:
            fallback_response = client.post(
                self.settings.oauth_token_path,
                json={
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret,
                },
            )
        return fallback_response

    @staticmethod
    def _parse_access_token_response(payload: dict[str, Any]) -> tuple[str | None, int]:
        if "access_token" in payload:
            return payload.get("access_token"), int(payload.get("expires_in", 3600))

        token_data = payload.get("data") or {}
        return token_data.get("access_token"), int(token_data.get("expires_in", 3600))

    def fetch_station_page(
        self,
        *,
        batch_number: int,
        effective_start_timestamp: datetime | None = None,
    ) -> list[dict[str, Any]]:
        return self._fetch_page(
            path=self.settings.station_path,
            batch_number=batch_number,
            effective_start_timestamp=effective_start_timestamp,
        )

    def fetch_price_page(
        self,
        *,
        batch_number: int,
        effective_start_timestamp: datetime | None = None,
    ) -> list[dict[str, Any]]:
        return self._fetch_page(
            path=self.settings.price_path,
            batch_number=batch_number,
            effective_start_timestamp=effective_start_timestamp,
        )

    def _fetch_page(
        self,
        *,
        path: str,
        batch_number: int,
        effective_start_timestamp: datetime | None,
    ) -> list[dict[str, Any]]:
        response = self._request(
            path=path,
            batch_number=batch_number,
            effective_start_timestamp=effective_start_timestamp,
        )
        if not isinstance(response, list):
            raise FuelFinderApiError(
                status_code=502,
                message="Unexpected response payload from upstream.",
                response_body=json.dumps(response),
            )
        return response

    def _request(
        self,
        *,
        path: str,
        batch_number: int,
        effective_start_timestamp: datetime | None = None,
    ) -> Any:
        token = self.get_access_token()
        params: dict[str, str | int] = {"batch-number": batch_number}
        if effective_start_timestamp is not None:
            params["effective-start-timestamp"] = format_upstream_timestamp(
                effective_start_timestamp
            )

        with self._http_client() as client:
            response = client.get(
                path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )

        if response.status_code == 401:
            token = self.get_access_token(force_refresh=True)
            with self._http_client() as client:
                response = client.get(
                    path,
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )

        if response.status_code >= 400:
            raise FuelFinderApiError(
                status_code=response.status_code,
                message=f"Failed to fetch {path}.",
                response_body=response.text,
            )
        return response.json()
