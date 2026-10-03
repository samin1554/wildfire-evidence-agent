-- Activity history (ADR-013 amendment): where heat was seen on which days, for "new / growing / persistent".
CREATE TABLE activity_cells (
    cell_x            integer NOT NULL,
    cell_y            integer NOT NULL,
    first_seen        timestamptz NOT NULL,
    last_seen         timestamptz NOT NULL,
    days              date[] NOT NULL DEFAULT '{}',   -- distinct UTC days with detections, last 14 days only
    detections_total  bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (cell_x, cell_y)
);
CREATE INDEX activity_cells_last_seen_idx ON activity_cells (last_seen);

ALTER TABLE activity_clusters
    ADD COLUMN cells text[] NOT NULL DEFAULT '{}',
    ADD COLUMN place jsonb,
    ADD COLUMN nearest_official jsonb,
    ADD COLUMN trend jsonb,
    ADD COLUMN persistent_heat_source boolean NOT NULL DEFAULT false,
    ADD COLUMN days_seen integer NOT NULL DEFAULT 0;
CREATE INDEX activity_clusters_cells_idx ON activity_clusters USING gin (cells);
