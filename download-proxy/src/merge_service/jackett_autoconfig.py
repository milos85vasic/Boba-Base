"""Jackett auto-configuration at proxy startup.

Discovers <NAME>_USERNAME/_PASSWORD/_COOKIES env triples and
idempotently configures matching indexers in Jackett. Failure
never raises out of autoconfigure_jackett(); all errors are
captured in AutoconfigResult.errors.

See docs/superpowers/specs/2026-04-26-jackett-autoconfig-clean-rebuild-design.md
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

import aiohttp
import Levenshtein
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Captures: <NAME>_USERNAME, <NAME>_PASSWORD, <NAME>_COOKIES
_CRED_RE = re.compile(r"^([A-Z][A-Z0-9_]+?)_(USERNAME|PASSWORD|COOKIES)$")

DEFAULT_EXCLUDE = frozenset(
    {"QBITTORRENT", "JACKETT", "WEBUI", "PROXY", "MERGE", "BRIDGE"}
)
FUZZY_THRESHOLD = 0.85
TOTAL_TIMEOUT_SECONDS = 60.0


class AmbiguousMatch(BaseModel):
    env_name: str
    candidates: list[str]


class AutoconfigResult(BaseModel):
    ran_at: datetime
    discovered_credentials: list[str] = Field(default_factory=list)
    matched_indexers: dict[str, str] = Field(default_factory=dict)
    configured_now: list[str] = Field(default_factory=list)
    already_present: list[str] = Field(default_factory=list)
    skipped_no_match: list[str] = Field(default_factory=list)
    skipped_ambiguous: list[AmbiguousMatch] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "serialize_by_alias": True}

    def __repr__(self) -> str:
        return (
            f"AutoconfigResult(ran_at={self.ran_at.isoformat()}, "
            f"discovered={len(self.discovered_credentials)}, "
            f"configured_now={len(self.configured_now)}, "
            f"errors={len(self.errors)})"
        )


def _scan_env_credentials(
    env: Mapping[str, str],
    exclude: frozenset[str] | set[str],
) -> dict[str, dict[str, str]]:
    """Scan env for tracker credential triples.

    Returns a dict keyed by tracker name; each value contains
    {"username", "password"} or {"cookies"}. Incomplete bundles
    are dropped.
    """
    grouped: dict[str, dict[str, str]] = {}
    for key, value in env.items():
        m = _CRED_RE.match(key)
        if not m:
            continue
        name, kind = m.group(1), m.group(2)
        if name in exclude:
            continue
        bucket = grouped.setdefault(name, {})
        bucket[kind.lower()] = value

    complete: dict[str, dict[str, str]] = {}
    for name, fields in grouped.items():
        has_userpass = "username" in fields and "password" in fields
        has_cookies = "cookies" in fields
        if has_userpass or has_cookies:
            complete[name] = fields
    return complete


def _match_indexers(
    bundles: dict[str, dict[str, str]],
    catalog: list[dict[str, Any]],
    override: dict[str, str],
) -> tuple[dict[str, str], list[AmbiguousMatch], list[str]]:
    """Map env tracker names to Jackett indexer ids.

    Returns (matched, ambiguous, unmatched). Override precedes fuzzy match.
    """
    catalog_ids = {entry["id"] for entry in catalog}
    matched: dict[str, str] = {}
    ambiguous: list[AmbiguousMatch] = []
    unmatched: list[str] = []

    for env_name in bundles:
        target = override.get(env_name)
        if target and target in catalog_ids:
            matched[env_name] = target
            continue

        scored: list[tuple[str, float]] = []
        needle = env_name.lower()
        for entry in catalog:
            id_score = Levenshtein.ratio(needle, entry["id"].lower())
            name_score = Levenshtein.ratio(needle, entry["name"].lower())
            best = max(id_score, name_score)
            if best >= FUZZY_THRESHOLD:
                scored.append((entry["id"], best))

        if not scored:
            unmatched.append(env_name)
            continue

        scored.sort(key=lambda t: (-t[1], t[0]))
        top_score = scored[0][1]
        ties = [sid for sid, sc in scored if sc == top_score]
        if len(ties) == 1:
            matched[env_name] = ties[0]
        else:
            ambiguous.append(AmbiguousMatch(env_name=env_name, candidates=ties))

    return matched, ambiguous, unmatched


async def _configure_one(
    session: aiohttp.ClientSession,
    *,
    jackett_url: str,
    api_key: str,
    indexer_id: str,
    creds: dict[str, str],
    already_configured: set[str],
) -> tuple[Literal["configured", "already_present", "error"], str | None]:
    """Configure a single Jackett indexer. Never raises out of its boundary."""
    if indexer_id in already_configured:
        return ("already_present", None)

    headers = {"Accept": "application/json"}
    params = {"apikey": api_key}

    cfg_url = f"{jackett_url}/api/v2.0/indexers/{indexer_id}/config"
    try:
        async with session.get(cfg_url, params=params, headers=headers) as resp:
            if resp.status >= 400:
                return ("error", f"template fetch HTTP {resp.status}")
            template = await resp.json()
    except (TimeoutError, aiohttp.ClientError) as e:
        return ("error", f"template fetch network error: {type(e).__name__}")

    # Jackett's template comes back as either a bare list of field
    # descriptors OR a {"config": [...]} envelope, depending on version.
    if isinstance(template, list):
        config_fields = template
    elif isinstance(template, dict):
        config_fields = template.get("config", [])
    else:
        config_fields = []

    field_map = {
        "username": creds.get("username"),
        "password": creds.get("password"),
        # Jackett uses different keys for cookie-based auth across indexers.
        "cookie": creds.get("cookies"),
        "cookies": creds.get("cookies"),
        "cookieheader": creds.get("cookies"),
    }
    # Preserve ALL fields verbatim from the template (id, type, name, etc.)
    # — Jackett rejects POSTs that drop schema fields. Only mutate `value`.
    populated: list[dict[str, Any]] = []
    fields_we_filled = 0
    for field in config_fields:
        new_field = dict(field) if isinstance(field, dict) else field
        fid = new_field.get("id") if isinstance(new_field, dict) else None
        if fid in field_map and field_map[fid] is not None:
            new_field["value"] = field_map[fid]
            fields_we_filled += 1
        populated.append(new_field)

    # If the indexer's template requires a kind of credential we don't
    # have (e.g. iptorrents needs `cookie` but we only supply user/pass),
    # skip cleanly rather than POST a half-empty config Jackett will 500 on.
    if fields_we_filled == 0:
        return ("error", "no_compatible_credential_fields_for_indexer")

    # POST body matches GET shape: bare list when the template was a list.
    body: Any = populated if isinstance(template, list) else {"config": populated}
    for attempt in (1, 2):
        try:
            async with session.post(
                cfg_url, params=params, headers=headers, json=body
            ) as resp:
                if resp.status >= 500 and attempt == 1:
                    await asyncio.sleep(2.0)
                    continue
                if resp.status >= 400:
                    return ("error", f"config POST HTTP {resp.status}")
                return ("configured", None)
        except (TimeoutError, aiohttp.ClientError) as e:
            if attempt == 1:
                await asyncio.sleep(2.0)
                continue
            return ("error", f"config POST network error: {type(e).__name__}")
    return ("error", "config POST exhausted retries")


def _parse_indexer_map(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        key, value = pair.split(":", 1)
        key, value = key.strip().upper(), value.strip()
        if key and value:
            out[key] = value
    return out


def _parse_exclude(raw: str | None) -> frozenset[str]:
    if raw is None:
        return DEFAULT_EXCLUDE
    parts = {p.strip().upper() for p in raw.split(",") if p.strip()}
    return frozenset(parts) if parts else DEFAULT_EXCLUDE


async def autoconfigure_jackett(
    jackett_url: str,
    api_key: str,
    env: Mapping[str, str],
    indexer_map_override: dict[str, str] | None = None,
    timeout: float = 10.0,  # noqa: ASYNC109 — per-request aiohttp timeout; outer asyncio.timeout caps total
) -> AutoconfigResult:
    """Discover env credentials, fuzzy-match to Jackett indexers, configure them.

    Never raises. All failures land in AutoconfigResult.errors.
    """
    started = datetime.now(UTC)
    override = (
        indexer_map_override
        if indexer_map_override is not None
        else _parse_indexer_map(env.get("JACKETT_INDEXER_MAP"))
    )
    exclude = _parse_exclude(env.get("JACKETT_AUTOCONFIG_EXCLUDE"))

    bundles = _scan_env_credentials(env, exclude=exclude)
    discovered = sorted(bundles.keys())

    if not bundles:
        return AutoconfigResult(ran_at=started, discovered_credentials=[])

    if not api_key:
        return AutoconfigResult(
            ran_at=started,
            discovered_credentials=discovered,
            errors=["jackett_auth_missing_key"],
        )

    headers = {"Accept": "application/json"}
    params = {"apikey": api_key}
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    try:
        async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                # Session warmup: Jackett's admin API redirects to /UI/TestCookie
                # on first hit. POSTing to /UI/Dashboard with empty password
                # establishes the session (Jackett accepts empty when no
                # AdminPassword is set in ServerConfig.json). Failure is
                # tolerated — the next API call will report the real error.
                try:
                    async with session.post(
                        f"{jackett_url}/UI/Dashboard",
                        data={"password": ""},
                        allow_redirects=True,
                    ):
                        pass
                except (TimeoutError, aiohttp.ClientError):
                    pass

                catalog: list[dict[str, Any]] = []
                catalog_err: str | None = None
                try:
                    # /api/v2.0/indexers?configured=false returns ALL available
                    # indexers (configured + unconfigured) as JSON. Requires
                    # admin session (warmed up above).
                    cat_url = f"{jackett_url}/api/v2.0/indexers"
                    async with session.get(
                        cat_url,
                        params={**params, "configured": "false"},
                        headers=headers,
                    ) as r:
                        if r.status == 401:
                            catalog_err = "jackett_auth_failed"
                        elif r.status >= 400:
                            catalog_err = f"jackett_catalog_http_{r.status}"
                        else:
                            try:
                                data = await r.json()
                                if isinstance(data, list):
                                    catalog = data
                                elif isinstance(data, dict):
                                    catalog = data.get("Indexers", [])
                                if not isinstance(catalog, list):
                                    catalog = []
                                    catalog_err = "catalog_parse_failed"
                            except (aiohttp.ContentTypeError, ValueError):
                                catalog_err = "catalog_parse_failed"
                except aiohttp.ClientConnectorError:
                    catalog_err = "jackett_unreachable"
                except (TimeoutError, aiohttp.ClientError) as e:
                    catalog_err = f"network: {type(e).__name__}"

                if catalog_err:
                    return AutoconfigResult(
                        ran_at=started,
                        discovered_credentials=discovered,
                        errors=[catalog_err],
                    )

                # Already-configured set. The catalog above already includes a
                # "configured" boolean per indexer — use that instead of a
                # second request.
                already: set[str] = {
                    entry["id"]
                    for entry in catalog
                    if entry.get("id") and entry.get("configured") is True
                }

                matched, ambiguous, unmatched = _match_indexers(
                    bundles, catalog, override
                )

                configured_now: list[str] = []
                already_present: list[str] = []
                errors: list[str] = []
                for env_name, indexer_id in matched.items():
                    status, err = await _configure_one(
                        session,
                        jackett_url=jackett_url,
                        api_key=api_key,
                        indexer_id=indexer_id,
                        creds=bundles[env_name],
                        already_configured=already,
                    )
                    if status == "configured":
                        configured_now.append(indexer_id)
                    elif status == "already_present":
                        already_present.append(indexer_id)
                    else:
                        errors.append(f"indexer_config_failed:{indexer_id}:{err}")

                return AutoconfigResult(
                    ran_at=started,
                    discovered_credentials=discovered,
                    matched_indexers=matched,
                    configured_now=configured_now,
                    already_present=already_present,
                    skipped_no_match=unmatched,
                    skipped_ambiguous=ambiguous,
                    errors=errors,
                )
    except TimeoutError:
        return AutoconfigResult(
            ran_at=started,
            discovered_credentials=discovered,
            errors=["jackett_total_timeout_60s"],
        )
    except Exception as e:
        logger.exception("Unexpected autoconfig failure")
        return AutoconfigResult(
            ran_at=started,
            discovered_credentials=discovered,
            errors=[f"unexpected: {type(e).__name__}"],
        )
