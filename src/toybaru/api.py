"""HTTP API layer for Toyota/Subaru Connected Services."""

from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from toybaru.auth.controller import AuthController
from toybaru.http import make_client
from toybaru.const import (
    CLIENT_VERSION,
    USER_AGENT,
    VEHICLE_ACCOUNT_ENDPOINT,
    VEHICLE_COMMAND_ENDPOINT,
    VEHICLE_ELECTRIC_REALTIME_ENDPOINT,
    VEHICLE_ELECTRIC_STATUS_ENDPOINT,
    VEHICLE_LOCATION_ENDPOINT,
    VEHICLE_NOTIFICATIONS_ENDPOINT,
    VEHICLE_REFRESH_STATUS_ENDPOINT,
    VEHICLE_SERVICE_HISTORY_ENDPOINT,
    VEHICLE_STATUS_ENDPOINT,
    VEHICLE_TELEMETRY_ENDPOINT,
    VEHICLE_TRIPS_ENDPOINT,
    VEHICLES_ENDPOINT,
)
from toybaru.exceptions import ApiError


class Api:
    """Low-level API client."""

    def __init__(self, auth: AuthController, timeout: int = 30) -> None:
        self.auth = auth
        self.timeout = timeout

    def _compute_client_ref(self, uuid: str) -> str:
        """Compute x-client-ref HMAC-SHA256."""
        mac = hmac.new(CLIENT_VERSION.encode(), uuid.encode(), hashlib.sha256)
        return mac.hexdigest()

    async def _headers(self, vin: str | None = None) -> dict[str, str]:
        token = await self.auth.ensure_token()
        h = {
            "Authorization": f"Bearer {token}",
            "x-guid": self.auth.uuid,
            "x-brand": self.auth.region.brand,
            "X-Appbrand": self.auth.region.brand,
            "x-channel": "ONEAPP",
            "x-appversion": CLIENT_VERSION,
            "x-api-key": self.auth.region.api_key,
            "x-client-ref": self._compute_client_ref(self.auth.uuid),
            "x-correlationid": str(uuid4()),
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "datetime": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        }
        if vin:
            h["VIN"] = vin
        return h

    async def request(
        self,
        method: str,
        endpoint: str,
        vin: str | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request and return JSON."""
        headers = await self._headers(vin)
        url = f"{self.auth.region.api_base_url}{endpoint}"

        async with make_client(timeout=self.timeout) as client:
            resp = await client.request(method, url, headers=headers, json=body, params=params)

        if resp.status_code not in (200, 202):
            raise ApiError(resp.status_code, resp.text)

        if not resp.content:
            return {}

        data = resp.json()
        # NA API wraps responses in "payload"
        if "payload" in data:
            return data["payload"]
        return data

    async def request_raw(
        self,
        method: str,
        endpoint: str,
        vin: str | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make an authenticated API request and return raw response."""
        headers = await self._headers(vin)
        url = f"{self.auth.region.api_base_url}{endpoint}"

        async with make_client(timeout=self.timeout) as client:
            resp = await client.request(method, url, headers=headers, json=body, params=params)

        return resp

    # --- High-level methods ---

    async def get_vehicles(self) -> dict[str, Any]:
        return await self.request("GET", VEHICLES_ENDPOINT)

    async def get_vehicle_status(self, vin: str) -> dict[str, Any]:
        return await self.request("GET", VEHICLE_STATUS_ENDPOINT, vin=vin)

    async def get_electric_status(self, vin: str) -> dict[str, Any]:
        return await self.request("GET", VEHICLE_ELECTRIC_STATUS_ENDPOINT, vin=vin)

    async def refresh_electric_status(self, vin: str) -> dict[str, Any]:
        return await self.request("POST", VEHICLE_ELECTRIC_REALTIME_ENDPOINT, vin=vin)

    async def get_location(self, vin: str) -> dict[str, Any]:
        return await self.request("GET", VEHICLE_LOCATION_ENDPOINT, vin=vin)

    async def get_telemetry(self, vin: str) -> dict[str, Any]:
        return await self.request("GET", VEHICLE_TELEMETRY_ENDPOINT, vin=vin)

    async def get_trips(
        self,
        vin: str,
        from_date: date,
        to_date: date,
        route: bool = False,
        summary: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        # Params must be encoded directly in the URL path, not as httpx query params
        endpoint = (
            f"{VEHICLE_TRIPS_ENDPOINT}"
            f"?from={from_date}&to={to_date}"
            f"&route={str(route).lower()}&summary={str(summary).lower()}"
            f"&limit={limit}&offset={offset}"
        )
        return await self.request("GET", endpoint, vin=vin)

    async def get_notifications(self, vin: str) -> dict[str, Any]:
        return await self.request("GET", VEHICLE_NOTIFICATIONS_ENDPOINT, vin=vin)

    async def get_service_history(self, vin: str) -> dict[str, Any]:
        return await self.request("GET", VEHICLE_SERVICE_HISTORY_ENDPOINT, vin=vin)

    async def refresh_vehicle_status(self, vin: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            VEHICLE_REFRESH_STATUS_ENDPOINT,
            vin=vin,
            body={
                "guid": self.auth.uuid,
                "vin": vin,
            },
        )

    async def send_command(self, vin: str, command: str, extra: dict | None = None) -> dict[str, Any]:
        body = {"command": command}
        if extra:
            body.update(extra)
        return await self.request("POST", VEHICLE_COMMAND_ENDPOINT, vin=vin, body=body)

    async def get_account(self) -> dict[str, Any]:
        return await self.request("GET", VEHICLE_ACCOUNT_ENDPOINT)
