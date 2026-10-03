import pytest

from inland_worker.kit.config import ProviderConfig, load_providers, parse_duration


def test_real_registry_loads_and_every_provider_is_https_and_allowlisted():
    reg = load_providers()
    assert {"firms", "wfigs_current", "nws_forecast"} <= set(reg.providers)
    for cfg in reg.providers.values():
        assert cfg.base_url.startswith("https://")
        if cfg.kind == "data":
            assert cfg.default_limitations, f"{cfg.provider_id} needs default limitations"
            assert cfg.evidence_types
    assert reg.area_bbox("sb_county_bbox") == (-117.8, 33.8, -114.1, 35.9)


@pytest.mark.parametrize(
    ("value", "seconds"), [("30m", 1800), ("1h", 3600), ("900s", 900), ("1d", 86400), (60, 60)]
)
def test_durations(value, seconds):
    assert parse_duration(value) == seconds


def _cfg(**over):
    base = dict(
        provider_id="p",
        display_name="P",
        base_url="https://api.example.com/x",
        allowed_hosts=["api.example.com"],
        ingestion={"class": "on_demand"},
        source_url="https://example.com",
    )
    return ProviderConfig(**{**base, **over})


def test_base_url_must_be_allowlisted():
    with pytest.raises(ValueError, match="not in allowed_hosts"):
        _cfg(allowed_hosts=["other.example.com"])


def test_http_is_refused():
    with pytest.raises(ValueError, match="https"):
        _cfg(base_url="http://api.example.com/x")


def test_auth_needs_env_and_name():
    with pytest.raises(ValueError):
        _cfg(auth={"type": "query_param", "env": "KEY"})


def test_env_refs_cover_auth_and_headers():
    cfg = _cfg(auth={"type": "header", "env": "TOKEN", "name": "X-Api-Key"}, headers={"User-Agent": "${UA}"})
    assert set(cfg.env_refs()) == {"TOKEN", "UA"}
