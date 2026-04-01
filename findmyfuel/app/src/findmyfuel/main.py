from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from html import escape
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from findmyfuel.background import BackgroundRefreshLoop
from findmyfuel.client import FuelFinderApiError, FuelFinderAuthError, FuelFinderClient
from findmyfuel.config import Settings, load_settings
from findmyfuel.db import FuelFinderRepository
from findmyfuel.home_assistant import (
    HomeAssistantClient,
    HomeAssistantTargetService,
)
from findmyfuel.sync import SyncService


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_timestamp(value: str | None) -> str:
    parsed = _parse_timestamp(value)
    if not parsed:
        return "Unknown"
    return parsed.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def _format_relative_age(value: str | None) -> str:
    parsed = _parse_timestamp(value)
    if not parsed:
        return "Unknown"
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    total_minutes = max(int(delta.total_seconds() // 60), 0)
    if total_minutes < 60:
        return f"{total_minutes} min ago"
    if total_minutes < 1440:
        hours = total_minutes // 60
        return f"{hours}h ago"
    days = total_minutes // 1440
    return f"{days}d ago"


def _freshness_tone(value: str | None) -> str:
    parsed = _parse_timestamp(value)
    if not parsed:
        return "muted"
    age_hours = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600
    if age_hours <= 12:
        return "fresh"
    if age_hours <= 48:
        return "recent"
    return "stale"


def _maps_link(item: dict[str, Any]) -> str:
    return (
        "https://www.google.com/maps/search/?api=1&query="
        f"{item['latitude']},{item['longitude']}"
    )


def _render_nearby_page(
    *,
    lat: float,
    lon: float,
    fuel: str,
    radius_km: float,
    limit: int,
    include_temporarily_closed: bool,
    items: list[dict[str, Any]],
) -> str:
    cheapest = min(items, key=lambda item: item["price_ppl"], default=None)
    freshest = max(
        items,
        key=lambda item: _parse_timestamp(item["price_last_updated"]) or datetime.min.replace(tzinfo=timezone.utc),
        default=None,
    )

    cards = []
    for index, item in enumerate(items, start=1):
        amenities = item.get("amenities") or []
        amenity_markup = "".join(
            f'<li class="chip">{escape(str(amenity).replace("_", " ").title())}</li>'
            for amenity in amenities
        ) or '<li class="chip chip-muted">No amenity data</li>'
        closure_badge = (
            '<span class="status status-warn">Temporarily closed</span>'
            if item["temporary_closure"]
            else ""
        )
        motorway_badge = (
            '<span class="status status-neutral">Motorway services</span>'
            if item["is_motorway_service_station"]
            else ""
        )
        freshness_tone = _freshness_tone(item["price_last_updated"])
        cards.append(
            f"""
            <article class="station-card">
              <div class="station-meta">
                <div class="rank">#{index}</div>
                <div>
                  <p class="eyebrow">{escape(item["brand_name"] or "Independent")}</p>
                  <h2>{escape(item["trading_name"] or "Unnamed station")}</h2>
                  <p class="subtle">{escape(item["display_address"] or item["postcode"] or "Address unavailable")}</p>
                </div>
              </div>
              <div class="price-panel">
                <p class="price">{item["price_ppl"]:.1f}<span>ppl</span></p>
                <p class="distance">{item["distance_km"]:.1f} km away</p>
              </div>
              <div class="badges">
                <span class="status status-{freshness_tone}">{escape(_format_relative_age(item["price_last_updated"]))}</span>
                {closure_badge}
                {motorway_badge}
              </div>
              <p class="updated">Updated {escape(_format_timestamp(item["price_last_updated"]))}</p>
              <ul class="chips">{amenity_markup}</ul>
              <div class="actions">
                <a href="{escape(_maps_link(item), quote=True)}" target="_blank" rel="noreferrer">Open in Maps</a>
              </div>
            </article>
            """
        )

    cheapest_summary = (
        f"{cheapest['trading_name']} at {cheapest['price_ppl']:.1f} ppl"
        if cheapest
        else "No stations found"
    )
    freshest_summary = (
        f"{freshest['trading_name']} updated { _format_relative_age(freshest['price_last_updated']) }"
        if freshest
        else "No updates yet"
    )

    return f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Find My Fuel Nearby Results</title>
        <style>
          :root {{
            --bg: #f4efe6;
            --panel: rgba(255, 252, 247, 0.86);
            --panel-strong: #fffaf3;
            --ink: #1f1b16;
            --muted: #665b51;
            --line: rgba(59, 40, 22, 0.12);
            --accent: #d95d39;
            --accent-deep: #8f2d14;
            --highlight: #1f7a5c;
            --warn: #b8621b;
            --shadow: 0 22px 60px rgba(67, 39, 19, 0.12);
          }}
          * {{ box-sizing: border-box; }}
          body {{
            margin: 0;
            font-family: Georgia, "Times New Roman", serif;
            color: var(--ink);
            background:
              radial-gradient(circle at top left, rgba(217, 93, 57, 0.18), transparent 28rem),
              radial-gradient(circle at top right, rgba(31, 122, 92, 0.14), transparent 24rem),
              linear-gradient(180deg, #f7f1e8 0%, #efe3d3 100%);
          }}
          .shell {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 32px 20px 56px;
          }}
          .hero {{
            padding: 28px;
            border: 1px solid var(--line);
            border-radius: 28px;
            background: var(--panel);
            backdrop-filter: blur(12px);
            box-shadow: var(--shadow);
          }}
          .eyebrow {{
            margin: 0 0 10px;
            font-size: 0.78rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--accent-deep);
          }}
          h1, h2, p {{ margin-top: 0; }}
          h1 {{
            margin-bottom: 12px;
            font-size: clamp(2.1rem, 5vw, 4.2rem);
            line-height: 0.95;
          }}
          .hero-copy {{
            max-width: 62ch;
            color: var(--muted);
            font-size: 1.03rem;
          }}
          .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 14px;
            margin-top: 22px;
          }}
          .summary-card, .station-card {{
            border: 1px solid var(--line);
            border-radius: 24px;
            background: var(--panel-strong);
          }}
          .summary-card {{
            padding: 18px;
          }}
          .summary-card strong {{
            display: block;
            margin-top: 8px;
            font-size: 1.1rem;
          }}
          .results {{
            display: grid;
            gap: 16px;
            margin-top: 22px;
          }}
          .station-card {{
            display: grid;
            grid-template-columns: minmax(0, 1.8fr) minmax(0, 0.9fr);
            gap: 18px;
            padding: 22px;
            box-shadow: 0 12px 30px rgba(67, 39, 19, 0.08);
          }}
          .station-meta {{
            display: flex;
            gap: 14px;
            align-items: start;
          }}
          .rank {{
            min-width: 48px;
            height: 48px;
            display: grid;
            place-items: center;
            border-radius: 16px;
            background: #f8dfce;
            color: var(--accent-deep);
            font-weight: 700;
          }}
          .subtle, .updated {{
            color: var(--muted);
          }}
          .price-panel {{
            text-align: right;
          }}
          .price {{
            margin-bottom: 8px;
            font-size: clamp(2rem, 4vw, 3rem);
            line-height: 0.9;
            font-weight: 700;
            color: var(--accent-deep);
          }}
          .price span {{
            margin-left: 8px;
            font-size: 1rem;
            color: var(--muted);
            font-weight: 400;
          }}
          .distance {{
            font-size: 1rem;
            color: var(--muted);
          }}
          .badges, .chips, .actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
          }}
          .badges {{
            grid-column: 1 / -1;
          }}
          .status, .chip, .actions a {{
            border-radius: 999px;
            padding: 8px 12px;
            font-size: 0.88rem;
            text-decoration: none;
          }}
          .status {{
            border: 1px solid var(--line);
            background: #f8f1e8;
          }}
          .status-fresh {{
            background: rgba(31, 122, 92, 0.12);
            color: #165641;
          }}
          .status-recent {{
            background: rgba(217, 93, 57, 0.1);
            color: var(--accent-deep);
          }}
          .status-stale, .status-warn {{
            background: rgba(184, 98, 27, 0.12);
            color: #7c4b17;
          }}
          .status-neutral, .chip-muted {{
            color: var(--muted);
          }}
          .chips {{
            grid-column: 1 / -1;
            list-style: none;
            margin: 0;
            padding: 0;
          }}
          .chip {{
            border: 1px solid rgba(31, 27, 22, 0.08);
            background: #fff;
          }}
          .actions {{
            grid-column: 1 / -1;
            margin-top: 4px;
          }}
          .actions a {{
            background: var(--ink);
            color: #fffaf3;
          }}
          .empty {{
            margin-top: 22px;
            padding: 26px;
            border-radius: 24px;
            background: var(--panel-strong);
            border: 1px solid var(--line);
            color: var(--muted);
          }}
          @media (max-width: 760px) {{
            .station-card {{
              grid-template-columns: 1fr;
            }}
            .price-panel {{
              text-align: left;
            }}
          }}
        </style>
      </head>
      <body>
        <main class="shell">
          <section class="hero">
            <p class="eyebrow">Nearby {escape(fuel.upper())} prices</p>
            <h1>{len(items)} stations within {radius_km:.0f} km</h1>
            <p class="hero-copy">
              Ranked for quick scanning around {lat:.4f}, {lon:.4f}. This keeps the essentials up top:
              cheapest option, freshest update, and how far you need to drive.
            </p>
            <div class="summary-grid">
              <article class="summary-card">
                <p class="eyebrow">Cheapest</p>
                <strong>{escape(cheapest_summary)}</strong>
              </article>
              <article class="summary-card">
                <p class="eyebrow">Freshest</p>
                <strong>{escape(freshest_summary)}</strong>
              </article>
              <article class="summary-card">
                <p class="eyebrow">Search</p>
                <strong>{escape(fuel.upper())}, {radius_km:.0f} km, limit {limit}</strong>
              </article>
              <article class="summary-card">
                <p class="eyebrow">Closed included</p>
                <strong>{"Yes" if include_temporarily_closed else "No"}</strong>
              </article>
            </div>
          </section>
          {"<section class='results'>" + "".join(cards) + "</section>" if cards else "<section class='empty'><h2>No stations found</h2><p>Try widening the radius, increasing the result limit, or switching fuel type.</p></section>"}
        </main>
      </body>
    </html>
    """


def create_app(
    *,
    settings: Settings | None = None,
    repository: FuelFinderRepository | None = None,
    client: FuelFinderClient | None = None,
    sync_service: SyncService | None = None,
    home_assistant_client: HomeAssistantClient | None = None,
    target_service: HomeAssistantTargetService | None = None,
    background_refresh_loop: BackgroundRefreshLoop | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    repository = repository or FuelFinderRepository(settings.db_path)
    repository.initialize()
    client = client or FuelFinderClient(settings)
    sync_service = sync_service or SyncService(repository, client)
    home_assistant_client = home_assistant_client or HomeAssistantClient(settings)
    target_service = target_service or HomeAssistantTargetService(
        settings,
        repository,
        home_assistant_client,
    )
    background_refresh_loop = background_refresh_loop or BackgroundRefreshLoop(
        sync_service,
        settings.refresh_interval_minutes,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        background_refresh_loop.start()
        try:
            yield
        finally:
            background_refresh_loop.stop()

    app = FastAPI(
        title="Find My Fuel",
        version="0.1.0",
        summary="Laptop prototype API for UK Fuel Finder data.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.repository = repository
    app.state.client = client
    app.state.sync_service = sync_service
    app.state.home_assistant_client = home_assistant_client
    app.state.target_service = target_service
    app.state.background_refresh_loop = background_refresh_loop

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "service": "findmyfuel",
            "credentials_configured": settings.credentials_configured,
            "upstream_base_url": settings.api_base_url,
            "database_path": str(settings.db_path),
            "counts": repository.counts(),
            "sync": repository.get_sync_state(),
            "background_refresh": background_refresh_loop.status(),
            "targets_configured": len(settings.targets),
            "home_assistant_api_available": settings.home_assistant_available,
        }

    @app.post("/refresh")
    def refresh() -> dict[str, Any]:
        try:
            return sync_service.refresh()
        except FuelFinderAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except FuelFinderApiError as exc:
            status_code = 502 if exc.status_code < 500 else exc.status_code
            raise HTTPException(
                status_code=status_code,
                detail={
                    "message": exc.message,
                    "status_code": exc.status_code,
                    "response_body": exc.response_body,
                },
            ) from exc

    @app.get("/debug/raw/prices")
    def debug_raw_prices(batch: int = Query(default=1, ge=1)) -> dict[str, Any]:
        try:
            payload = client.fetch_price_page(batch_number=batch)
        except FuelFinderAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except FuelFinderApiError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"message": exc.message, "response_body": exc.response_body},
            ) from exc
        return {"batch": batch, "count": len(payload), "items": payload}

    @app.get("/debug/raw/pfs")
    def debug_raw_pfs(batch: int = Query(default=1, ge=1)) -> dict[str, Any]:
        try:
            payload = client.fetch_station_page(batch_number=batch)
        except FuelFinderAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except FuelFinderApiError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"message": exc.message, "response_body": exc.response_body},
            ) from exc
        return {"batch": batch, "count": len(payload), "items": payload}

    @app.get("/nearby")
    def nearby(
        lat: float = Query(ge=-90, le=90),
        lon: float = Query(ge=-180, le=180),
        fuel: str = Query(min_length=1),
        radius_km: float = Query(default=10, gt=0, le=100),
        limit: int = Query(default=10, ge=1, le=100),
        include_temporarily_closed: bool = Query(default=settings.include_temporarily_closed),
    ) -> dict[str, Any]:
        items = repository.find_nearby_stations(
            lat=lat,
            lon=lon,
            fuel_type=fuel,
            radius_km=radius_km,
            limit=limit,
            include_temporarily_closed=include_temporarily_closed,
        )
        return {
            "query": {
                "lat": lat,
                "lon": lon,
                "fuel": fuel.upper(),
                "radius_km": radius_km,
                "limit": limit,
                "include_temporarily_closed": include_temporarily_closed,
            },
            "count": len(items),
            "items": items,
        }

    @app.get("/nearby/view", response_class=HTMLResponse)
    def nearby_view(
        lat: float = Query(ge=-90, le=90),
        lon: float = Query(ge=-180, le=180),
        fuel: str = Query(min_length=1),
        radius_km: float = Query(default=10, gt=0, le=100),
        limit: int = Query(default=10, ge=1, le=100),
        include_temporarily_closed: bool = Query(default=False),
    ) -> HTMLResponse:
        items = repository.find_nearby_stations(
            lat=lat,
            lon=lon,
            fuel_type=fuel,
            radius_km=radius_km,
            limit=limit,
            include_temporarily_closed=include_temporarily_closed,
        )
        return HTMLResponse(
            _render_nearby_page(
                lat=lat,
                lon=lon,
                fuel=fuel,
                radius_km=radius_km,
                limit=limit,
                include_temporarily_closed=include_temporarily_closed,
                items=items,
            )
        )

    @app.get("/ha/targets")
    def ha_targets() -> dict[str, Any]:
        return target_service.list_target_summaries()

    @app.get("/ha/targets/{slug}")
    def ha_target(slug: str) -> dict[str, Any]:
        try:
            return target_service.get_target_summary(slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown target '{slug}'.") from exc

    return app


app = create_app()
