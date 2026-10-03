"""Load and validate apps/worker/config/providers.yaml: the single list of providers, endpoints and limits.

Nothing else in the codebase may hard-code a provider URL.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from inland_worker.contracts.models import EvidenceType

DEFAULT_PROVIDERS_FILE = Path(__file__).resolve().parents[3] / "config" / "providers.yaml"
_ENV_REF = re.compile(r"\$\{([A-Z0-9_]+)\}")
_DURATION = re.compile(r"^(\d+)\s*([smhd])$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(value: int | str) -> int:
    """'30m' -> 1800. Plain integers are seconds."""
    if isinstance(value, int):
        return value
    m = _DURATION.match(value.strip())
    if not m:
        raise ValueError(f"invalid duration {value!r}; use e.g. 900s, 30m, 1h, 1d")
    return int(m.group(1)) * _UNITS[m.group(2)]


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["none", "header", "query_param", "path_placeholder"] = "none"
    env: str | None = Field(
        default=None, description="Name of the env var holding the secret. Never the value."
    )
    name: str | None = Field(default=None, description="Header name, query param name, or path placeholder.")

    @model_validator(mode="after")
    def _complete(self) -> AuthConfig:
        if self.type != "none" and (not self.env or not self.name):
            raise ValueError(f"auth type {self.type!r} needs both 'env' and 'name'")
        return self


class RetryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max: int = Field(default=3, ge=0, le=5)
    backoff_s: float = Field(default=0.5, ge=0)
    on_status: list[int] = Field(default_factory=lambda: [429, 500, 502, 503, 504])


class CacheConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: list[str] = Field(default_factory=list, description="Query fields that form the cache key.")
    ttl: int = 900

    @field_validator("ttl", mode="before")
    @classmethod
    def parse_ttl(cls, value: int | str) -> int:
        return parse_duration(value)


class IngestionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    class_: Literal["reference", "near_real_time", "on_demand", "compute"] = Field(alias="class")
    schedule: str | None = None
    default_area: str | None = None


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    kind: Literal["data", "llm"] = "data"  # llm = the agent's model API (no evidence of its own)
    display_name: str
    base_url: str
    allowed_hosts: list[str]
    auth: AuthConfig = Field(default_factory=AuthConfig)
    headers: dict[str, str] = Field(
        default_factory=dict, description="Values may reference env vars as ${NAME}."
    )
    timeout_s: float = Field(default=20, gt=0, le=120)
    max_response_bytes: int = Field(default=10_000_000, gt=0)
    max_follow: int = Field(default=20, ge=0, le=100, description="Max follow-up requests (links or pages).")
    retries: RetryConfig = Field(default_factory=RetryConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    ingestion: IngestionConfig
    evidence_types: list[EvidenceType] = Field(default_factory=list)
    default_limitations: list[str] = Field(default_factory=list)
    source_url: str

    @model_validator(mode="after")
    def _https_and_allowlisted(self) -> ProviderConfig:
        url = urlparse(self.base_url)
        if url.scheme != "https":
            raise ValueError(f"{self.provider_id}: base_url must use https")
        if url.hostname not in self.allowed_hosts:
            raise ValueError(f"{self.provider_id}: base_url host {url.hostname!r} is not in allowed_hosts")
        return self

    def env_refs(self) -> list[str]:
        """Every env var this provider reads (auth + header interpolation)."""
        refs = [self.auth.env] if self.auth.env else []
        for value in self.headers.values():
            refs.extend(_ENV_REF.findall(value))
        return refs

    def resolve_headers(self, env: dict[str, str] | os._Environ[str]) -> dict[str, str]:
        from inland_worker.kit.errors import ProviderAuthMissing

        out: dict[str, str] = {}
        for key, value in self.headers.items():

            def sub(m: re.Match[str]) -> str:
                name = m.group(1)
                if not env.get(name):
                    raise ProviderAuthMissing(self.provider_id, f"environment variable {name} is not set")
                return env[name]

            out[key] = _ENV_REF.sub(sub, value)
        return out


class ProviderRegistry(BaseModel):
    providers: dict[str, ProviderConfig]
    areas: dict[str, tuple[float, float, float, float]] = Field(default_factory=dict)

    def get(self, provider_id: str) -> ProviderConfig:
        try:
            return self.providers[provider_id]
        except KeyError:
            known = ", ".join(sorted(self.providers))
            raise KeyError(f"unknown provider_id {provider_id!r}; known: {known}") from None

    def area_bbox(self, name: str) -> tuple[float, float, float, float]:
        return self.areas[name]


def load_providers_file(path: Path | str) -> ProviderRegistry:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    areas = {name: tuple(spec["bbox"]) for name, spec in (raw.pop("areas", None) or {}).items()}
    providers = {pid: ProviderConfig(provider_id=pid, **spec) for pid, spec in raw.items()}
    return ProviderRegistry(providers=providers, areas=areas)


@lru_cache(maxsize=4)
def _cached(path: str) -> ProviderRegistry:
    return load_providers_file(path)


def load_providers(path: Path | str | None = None) -> ProviderRegistry:
    """Load the registry. INLAND_PROVIDERS_FILE overrides the default path."""
    chosen = path or os.environ.get("INLAND_PROVIDERS_FILE") or DEFAULT_PROVIDERS_FILE
    return _cached(str(chosen))
