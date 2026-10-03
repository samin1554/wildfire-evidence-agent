ALTER TABLE activity_clusters
    DROP COLUMN IF EXISTS cells,
    DROP COLUMN IF EXISTS place,
    DROP COLUMN IF EXISTS nearest_official,
    DROP COLUMN IF EXISTS trend,
    DROP COLUMN IF EXISTS persistent_heat_source,
    DROP COLUMN IF EXISTS days_seen;
DROP TABLE IF EXISTS activity_cells;
