-- Cache + last-known-good snapshots (ADR-006). The worker's PostgresCacheStore reads/writes these.
CREATE TABLE provider_fetches (
    id           bigserial PRIMARY KEY,
    provider_id  text NOT NULL,
    cache_key    text NOT NULL,
    fetched_at   timestamptz NOT NULL,
    expires_at   timestamptz NOT NULL,
    item_count   integer NOT NULL,
    is_last_good boolean NOT NULL DEFAULT true
);
CREATE INDEX provider_fetches_key_idx ON provider_fetches (cache_key, fetched_at DESC);

CREATE TABLE cached_evidence (
    fetch_id  bigint NOT NULL REFERENCES provider_fetches (id) ON DELETE CASCADE,
    ord       integer NOT NULL,
    evidence  jsonb NOT NULL,
    geometry  geometry(Geometry, 4326),
    PRIMARY KEY (fetch_id, ord)
);
CREATE INDEX cached_evidence_geom_idx ON cached_evidence USING gist (geometry);

CREATE TABLE reference_layers (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    geometry    geometry(MultiPolygon, 4326) NOT NULL,
    source      text NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX reference_layers_geom_idx ON reference_layers USING gist (geometry);
