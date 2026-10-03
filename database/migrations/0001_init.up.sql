-- Spec §10 tables + cancel_requested_at (ADR-003). Status writes: Go inserts `queued`; the worker owns every
-- later transition (ADR-004). Evidence columns mirror contracts/evidence.schema.json.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email       text UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE areas_of_interest (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid REFERENCES users (id) ON DELETE SET NULL,
    name        text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    geometry    geometry(MultiPolygon, 4326) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX areas_of_interest_geom_idx ON areas_of_interest USING gist (geometry);

CREATE TABLE analysis_jobs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid REFERENCES users (id) ON DELETE SET NULL,
    area_id             uuid REFERENCES areas_of_interest (id) ON DELETE SET NULL,
    area                geometry(MultiPolygon, 4326) NOT NULL,
    question            text NOT NULL CHECK (char_length(question) BETWEEN 1 AND 2000),
    analysis_type       text NOT NULL CHECK (analysis_type IN ('historical_fire_impact')),
    date_start          date NOT NULL,
    date_end            date NOT NULL CHECK (date_end >= date_start),
    status              text NOT NULL DEFAULT 'queued' CHECK (status IN (
                            'queued', 'validating', 'retrieving_data', 'processing_satellite',
                            'verifying_evidence', 'generating_report', 'completed', 'failed', 'cancelled')),
    progress            smallint NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    stage               text NOT NULL DEFAULT 'Queued',
    last_event_seq      integer NOT NULL DEFAULT 0,
    attempts            integer NOT NULL DEFAULT 0,
    error_code          text,
    error_message       text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    completed_at        timestamptz,
    cancel_requested_at timestamptz,
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX analysis_jobs_status_idx ON analysis_jobs (status, updated_at);
CREATE INDEX analysis_jobs_area_idx ON analysis_jobs USING gist (area);

CREATE TABLE evidence_items (
    job_id            uuid NOT NULL REFERENCES analysis_jobs (id) ON DELETE CASCADE,
    id                text NOT NULL,
    evidence_type     text NOT NULL CHECK (evidence_type IN (
                          'satellite_detection', 'satellite_measurement', 'official_perimeter',
                          'official_hazard_zone', 'weather_observation', 'weather_forecast', 'weather_alert',
                          'air_quality_observation', 'deterministic_calculation', 'agent_inference')),
    source            text NOT NULL,
    source_record_id  text,
    observed_at       timestamptz NOT NULL,
    retrieved_at      timestamptz NOT NULL,
    geometry          geometry(Geometry, 4326),
    properties        jsonb NOT NULL DEFAULT '{}',
    quality_flags     text[] NOT NULL DEFAULT '{}',
    limitations       text[] NOT NULL DEFAULT '{}',
    source_url        text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    -- ADR-003 keys retries on (job_id, source, source_record_id); computed evidence has no record id, so the
    -- deterministic evidence id (Evidence.stable_id) is the idempotency key here.
    PRIMARY KEY (job_id, id)
);
CREATE INDEX evidence_items_page_idx ON evidence_items (job_id, created_at, id);
CREATE INDEX evidence_items_geom_idx ON evidence_items USING gist (geometry);

CREATE TABLE tool_executions (
    id              bigserial PRIMARY KEY,
    job_id          uuid REFERENCES analysis_jobs (id) ON DELETE CASCADE,
    tool_name       text NOT NULL,
    input           jsonb NOT NULL DEFAULT '{}',
    output_summary  jsonb NOT NULL DEFAULT '{}',
    status          text NOT NULL CHECK (status IN ('ok', 'stale', 'missing', 'error')),
    error_code      text,
    started_at      timestamptz NOT NULL,
    completed_at    timestamptz NOT NULL
);
CREATE INDEX tool_executions_job_idx ON tool_executions (job_id);

CREATE TABLE artifacts (
    id             text PRIMARY KEY,
    job_id         uuid NOT NULL REFERENCES analysis_jobs (id) ON DELETE CASCADE,
    artifact_type  text NOT NULL CHECK (artifact_type IN ('report', 'layer', 'tile_layer', 'chart')),
    storage_key    text,
    mime_type      text NOT NULL,
    metadata       jsonb NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX artifacts_job_idx ON artifacts (job_id, artifact_type);
