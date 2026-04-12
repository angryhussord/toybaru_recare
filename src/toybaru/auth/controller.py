"""OAuth2 authentication controller for Toyota/Subaru Connected Services.

Implements the 3-stage ForgeRock AM OAuth2 flow:
1. Authenticate: POST credentials via callbacks -> get tokenId
2. Authorize: GET with iPlanetDirectoryPro cookie -> get auth code
3. Token: POST auth code -> get access/refresh/id tokens

"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt

from toybaru.const import CLIENT_VERSION, DATA_DIR, USER_AGENT, RegionConfig
from toybaru.exceptions import AuthenticationError, TokenExpiredError
from toybaru.http import make_client


TOKEN_FILE = DATA_DIR / "tokens.json"


@dataclass
class TokenInfo:
    access_token: str
    refresh_token: str
    uuid: str
    expires_at: float  # UTC timestamp

    @property
    def is_valid(self) -> bool:
        return self.expires_at > datetime.now(timezone.utc).timestamp()


class AuthController:
    """Handles authentication with the Toyota/Subaru connected services backend."""

    def __init__(self, region: RegionConfig, username: str, password: str) -> None:
        self.region = region
        self._username = username
        self._password = password
        self._token_info: TokenInfo | None = None
        self._load_saved_tokens()

    @property
    def token(self) -> str | None:
        return self._token_info.access_token if self._token_info else None

    @property
    def uuid(self) -> str | None:
        return self._token_info.uuid if self._token_info else None

    @property
    def is_authenticated(self) -> bool:
        return self._token_info is not None and self._token_info.is_valid

    async def ensure_token(self) -> str:
        """Ensure we have a valid access token, refreshing or re-authenticating as needed."""
        if self._token_info and self._token_info.is_valid:
            return self._token_info.access_token

        if self._token_info and self._token_info.refresh_token:
            try:
                await self._refresh_tokens()
                return self._token_info.access_token
            except (AuthenticationError, httpx.HTTPError):
                pass  # Fall through to full auth

        await self._authenticate()
        return self._token_info.access_token

    async def _authenticate(self) -> None:
        """Full 3-stage authentication flow."""
        async with make_client(timeout=30, follow_redirects=False) as client:
            # Stage 1: Authenticate
            token_id = await self._perform_authentication(client)

            # Stage 2: Authorize
            auth_code = await self._perform_authorization(client, token_id)

            # Stage 3: Token exchange
            token_data = await self._retrieve_tokens(client, auth_code)

            self._update_tokens(token_data)

    async def _perform_authentication(self, client: httpx.AsyncClient) -> str:
        """Stage 1: Submit credentials via ForgeRock callbacks, get tokenId.

        The callback flow varies by realm but follows this pattern:
        - alliance-subaru (EU): NameCallback("User Name") -> PasswordCallback -> tokenId
        - tme (Toyota EU): locale callbacks -> NameCallback + ChoiceCallback -> PasswordCallback -> tokenId
        We handle all callback types generically.
        """
        auth_url = (
            f"{self.region.auth_realm.replace('oauth2', 'json')}"
            f"/authenticate?authIndexType=service&authIndexValue=oneapp"
        )
        headers = {
            "Accept-API-Version": "resource=2.1, protocol=1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Region": self.region.region,
            "Region": self.region.region,
            "Brand": self.region.brand,
            "X-Brand": self.region.brand,
        }

        data: dict[str, Any] = {}
        password_sent = False
        for _ in range(10):
            if "callbacks" in data:
                for cb in data["callbacks"]:
                    cb_type = cb["type"]
                    prompt = cb["output"][0].get("value", "") if cb.get("output") else ""

                    if cb_type == "NameCallback" and prompt == "User Name":
                        cb["input"][0]["value"] = self._username
                    elif cb_type == "NameCallback" and prompt in ("Market Locale", "Internationalization", "UI Locales"):
                        cb["input"][0]["value"] = "de-DE"
                    elif cb_type == "PasswordCallback":
                        cb["input"][0]["value"] = self._password
                        password_sent = True
                    elif cb_type == "ChoiceCallback":
                        cb["input"][0]["value"] = 0  # "Local" login
                    elif cb_type == "TextOutputCallback" and "Not Found" in str(prompt):
                        raise AuthenticationError(f"User not found: {prompt}")

            resp = await client.post(auth_url, json=data, headers=headers)
            if resp.status_code != 200:
                raise AuthenticationError(f"Authentication failed: {resp.status_code} {resp.text}")

            data = resp.json()
            if "tokenId" in data:
                return data["tokenId"]

        raise AuthenticationError("No tokenId received after multiple callback rounds.")

    async def _perform_authorization(self, client: httpx.AsyncClient, token_id: str) -> str:
        """Stage 2: Exchange tokenId for authorization code via redirect."""
        authorize_url = (
            f"{self.region.auth_realm}/authorize"
            f"?client_id={self.region.client_id}"
            f"&scope=openid+profile+write"
            f"&response_type=code"
            f"&redirect_uri={self.region.redirect_uri}"
            f"&code_challenge=plain"
            f"&code_challenge_method=plain"
        )
        headers = {
            "Accept-API-Version": "resource=2.1, protocol=1.0",
            "Cookie": f"iPlanetDirectoryPro={token_id}",
        }

        resp = await client.get(authorize_url, headers=headers)
        if resp.status_code != 302:
            raise AuthenticationError(f"Authorization failed: {resp.status_code} {resp.text}")

        location = resp.headers.get("location", "")
        parsed = parse_qs(urlparse(location).query)
        if "code" not in parsed:
            raise AuthenticationError(f"No auth code in redirect: {location}")

        return parsed["code"][0]

    async def _retrieve_tokens(self, client: httpx.AsyncClient, auth_code: str) -> dict[str, Any]:
        """Stage 3: Exchange authorization code for access/refresh tokens."""
        token_url = f"{self.region.auth_realm}/access_token"

        resp = await client.post(
            token_url,
            headers={
                "Authorization": f"Basic {self.region.basic_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "client_id": self.region.client_id,
                "code": auth_code,
                "redirect_uri": self.region.redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": "plain",
            },
        )
        if resp.status_code != 200:
            raise AuthenticationError(f"Token exchange failed: {resp.status_code} {resp.text}")

        return resp.json()

    async def _refresh_tokens(self) -> None:
        """Refresh access token using refresh token."""
        token_url = f"{self.region.auth_realm}/access_token"

        async with make_client(timeout=30) as client:
            resp = await client.post(
                token_url,
                headers={
                    "Authorization": f"Basic {self.region.basic_auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "client_id": self.region.client_id,
                    "redirect_uri": self.region.redirect_uri,
                    "grant_type": "refresh_token",
                    "code_verifier": "plain",
                    "refresh_token": self._token_info.refresh_token,
                },
            )
            if resp.status_code != 200:
                raise AuthenticationError(f"Token refresh failed: {resp.status_code}")

            self._update_tokens(resp.json())

    def _update_tokens(self, data: dict[str, Any]) -> None:
        """Parse token response and persist."""
        for field in ("access_token", "id_token", "refresh_token", "expires_in"):
            if field not in data:
                raise AuthenticationError(f"Missing field in token response: {field}")

        uuid = jwt.decode(
            data["id_token"],
            algorithms=["RS256"],
            options={"verify_signature": False},
            audience="oneappsdkclient",
        )["uuid"]

        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])).timestamp()

        self._token_info = TokenInfo(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            uuid=uuid,
            expires_at=expires_at,
        )
        self._save_tokens()

    def _save_tokens(self) -> None:
        """Persist tokens to disk."""
        if not self._token_info:
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps(asdict(self._token_info), indent=2))

    def _load_saved_tokens(self) -> None:
        """Load tokens from disk if available."""
        if TOKEN_FILE.exists():
            try:
                data = json.loads(TOKEN_FILE.read_text())
                self._token_info = TokenInfo(**data)
            except (json.JSONDecodeError, TypeError, KeyError):
                pass  # Corrupted file, ignore

    def clear_tokens(self) -> None:
        """Remove saved tokens."""
        self._token_info = None
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
