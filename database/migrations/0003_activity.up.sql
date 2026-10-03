-- Activity feed (ADR-013): clustered recent heat detections, refreshed by the worker; the API serves the latest.
CREATE TABLE activity_snapshots (
    id                    bigserial PRIMARY KEY,
    generated_at          timestamptz NOT NULL,
    data_mode             text NOT NULL CHECK (data_mode IN ('live', 'fixture')),
    window_days           smallint NOT NULL,
    detections_considered integer NOT NULL,
    sources               jsonb NOT NULL DEFAULT '[]',
    limitations           text[] NOT NULL DEFAULT '{}',
    cluster_count         integer NOT NULL
);
CREATE INDEX activity_snapshots_time_idx ON activity_snapshots (generated_at DESC);

CREATE TABLE activity_clusters (
    snapshot_id      bigint NOT NULL REFERENCES activity_snapshots (id) ON DELETE CASCADE,
    id               text NOT NULL,
    rank             integer NOT NULL,
    label            text NOT NULL CHECK (label IN ('unverified_detection', 'officially_reported')),
    centroid         geometry(Point, 4326) NOT NULL,
    footprint        geometry(Geometry, 4326) NOT NULL,
    suggested_area   geometry(Polygon, 4326) NOT NULL,
    detections       integer NOT NULL,
    high_confidence  integer NOT NULL,
    max_frp          double precision NOT NULL,
    total_frp        double precision NOT NULL,
    first_seen       timestamptz NOT NULL,
    last_seen        timestamptz NOT NULL,
    satellites       text[] NOT NULL DEFAULT '{}',
    official         jsonb,
    PRIMARY KEY (snapshot_id, id)
);
CREATE INDEX activity_clusters_rank_idx ON activity_clusters (snapshot_id, rank);
CREATE INDEX activity_clusters_geom_idx ON activity_clusters USING gist (centroid);
