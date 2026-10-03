-- The supported region. Until S4's county-boundary connector lands this is the coarse bbox from
-- apps/worker/config/providers.yaml (areas.sb_county_bbox). Idempotent: safe to run twice.
INSERT INTO reference_layers (id, name, geometry, source)
VALUES (
    'region',
    'San Bernardino County (coarse bbox, sb_county_bbox)',
    ST_Multi(ST_MakeEnvelope(-117.8, 33.8, -114.1, 35.9, 4326)),
    'providers.yaml areas.sb_county_bbox'
)
ON CONFLICT (id) DO UPDATE SET geometry = EXCLUDED.geometry, name = EXCLUDED.name, updated_at = now();
