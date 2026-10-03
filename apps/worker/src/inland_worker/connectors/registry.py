"""provider_id → connector class. `make new-connector` adds new entries at the markers below."""

from __future__ import annotations

from inland_worker.connectors.fire.calfire_historical import CalfireHistoricalConnector
from inland_worker.connectors.fire.firms import FirmsConnector
from inland_worker.connectors.fire.wfigs import WfigsCurrentConnector
from inland_worker.connectors.fire.wfigs_history import WfigsHistoryConnector
from inland_worker.connectors.imagery.earth_search_s2 import EarthSearchS2Connector
from inland_worker.connectors.weather.nws_alerts import NwsAlertsConnector
from inland_worker.connectors.weather.nws_forecast import NwsForecastConnector
from inland_worker.kit.config import ProviderRegistry, load_providers
from inland_worker.kit.connector import BaseConnector

# <new-connector-imports>

CONNECTORS: dict[str, type[BaseConnector]] = {
    FirmsConnector.provider_id: FirmsConnector,
    WfigsCurrentConnector.provider_id: WfigsCurrentConnector,
    NwsForecastConnector.provider_id: NwsForecastConnector,
    EarthSearchS2Connector.provider_id: EarthSearchS2Connector,
    CalfireHistoricalConnector.provider_id: CalfireHistoricalConnector,
    WfigsHistoryConnector.provider_id: WfigsHistoryConnector,
    NwsAlertsConnector.provider_id: NwsAlertsConnector,
    # <new-connector-entries>
}


def get_connector(provider_id: str, registry: ProviderRegistry | None = None) -> BaseConnector:
    registry = registry or load_providers()
    try:
        cls = CONNECTORS[provider_id]
    except KeyError:
        raise KeyError(f"no connector registered for {provider_id!r}; known: {sorted(CONNECTORS)}") from None
    return cls(registry.get(provider_id))
