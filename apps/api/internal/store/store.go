// Package store holds every SQL query the API runs (PostgreSQL + PostGIS).
//
// The API writes exactly one job status: the initial `queued` row. Every later transition belongs to the
// worker (ADR-004). Geometry checks run in PostGIS so the database is the single source of spatial truth.
package store

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("not found")

// Limits (docs/sections/03-go-api.md: proposed, confirmed for the demo).
const (
	MaxAreaKm2 = 5000
	// RegionFallback is providers.yaml areas.sb_county_bbox, used if the seed hasn't run.
	RegionFallback = "ST_MakeEnvelope(-117.8, 33.8, -114.1, 35.9, 4326)"
)

type Store struct{ Pool *pgxpool.Pool }

func New(ctx context.Context, dsn string) (*Store, error) {
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return nil, err
	}
	return &Store{Pool: pool}, nil
}

// ---- geometry -------------------------------------------------------------------------------------------

type GeometryCheck struct {
	Valid       bool
	Reason      string
	InRegion    bool
	AreaKm2     float64
	ParseFailed bool
}

// CheckGeometry asks PostGIS whether a GeoJSON polygon is valid, inside the supported region, and how big it is.
func (s *Store) CheckGeometry(ctx context.Context, geojson []byte) (GeometryCheck, error) {
	var c GeometryCheck
	err := s.Pool.QueryRow(ctx, `
		WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON($1), 4326) AS geom),
		     r AS (SELECT coalesce((SELECT geometry FROM reference_layers WHERE id = 'region'), `+RegionFallback+`) AS geom)
		SELECT ST_IsValid(g.geom), ST_IsValidReason(g.geom), ST_Within(g.geom, r.geom),
		       ST_Area(g.geom::geography) / 1e6
		FROM g, r`, string(geojson)).Scan(&c.Valid, &c.Reason, &c.InRegion, &c.AreaKm2)
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) {
		// ST_GeomFromGeoJSON rejects malformed input with a data exception
		return GeometryCheck{ParseFailed: true, Reason: pgErr.Message}, nil
	}
	return c, err
}

// ---- jobs -------------------------------------------------------------------------------------------------

type NewJob struct {
	Question     string
	AnalysisType string
	DateStart    string
	DateEnd      string
	Area         json.RawMessage // GeoJSON Polygon/MultiPolygon (already checked)
	AreaID       *string
}

type Job struct {
	ID                string     `json:"id"`
	AreaID            *string    `json:"area_id"`
	Question          string     `json:"question"`
	AnalysisType      string     `json:"analysis_type"`
	Status            string     `json:"status"`
	Progress          int        `json:"progress"`
	ErrorCode         *string    `json:"error_code"`
	ErrorMessage      *string    `json:"error_message"`
	CreatedAt         time.Time  `json:"created_at"`
	StartedAt         *time.Time `json:"started_at"`
	CompletedAt       *time.Time `json:"completed_at"`
	CancelRequestedAt *time.Time `json:"cancel_requested_at"`
}

const jobColumns = `id::text, area_id::text, question, analysis_type, status, progress, error_code, error_message,
	created_at, started_at, completed_at, cancel_requested_at`

func scanJob(row pgx.Row) (Job, error) {
	var j Job
	err := row.Scan(&j.ID, &j.AreaID, &j.Question, &j.AnalysisType, &j.Status, &j.Progress, &j.ErrorCode,
		&j.ErrorMessage, &j.CreatedAt, &j.StartedAt, &j.CompletedAt, &j.CancelRequestedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return j, ErrNotFound
	}
	return j, err
}

// InsertJob stores the job as `queued` (the API's only status write).
func (s *Store) InsertJob(ctx context.Context, n NewJob) (Job, error) {
	return scanJob(s.Pool.QueryRow(ctx, `
		INSERT INTO analysis_jobs (area_id, area, question, analysis_type, date_start, date_end)
		VALUES ($1::uuid, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON($2), 4326)), $3, $4, $5::date, $6::date)
		RETURNING `+jobColumns, n.AreaID, string(n.Area), n.Question, n.AnalysisType, n.DateStart, n.DateEnd))
}

func (s *Store) GetJob(ctx context.Context, id string) (Job, error) {
	if !IsUUID(id) {
		return Job{}, ErrNotFound
	}
	return scanJob(s.Pool.QueryRow(ctx, `SELECT `+jobColumns+` FROM analysis_jobs WHERE id = $1`, id))
}

// RequestCancel sets cancel_requested_at once; finished jobs are left untouched (ADR-003).
func (s *Store) RequestCancel(ctx context.Context, id string) (Job, error) {
	if !IsUUID(id) {
		return Job{}, ErrNotFound
	}
	if _, err := s.Pool.Exec(ctx, `
		UPDATE analysis_jobs SET cancel_requested_at = coalesce(cancel_requested_at, now())
		WHERE id = $1 AND status NOT IN ('completed', 'failed', 'cancelled')`, id); err != nil {
		return Job{}, err
	}
	return s.GetJob(ctx, id)
}

// Snapshot is the job's current state as a job-event (for SSE).
type Snapshot struct {
	Seq          int
	Status       string
	Progress     int
	Stage        string
	ErrorCode    *string
	ErrorMessage *string
	At           time.Time
}

func (s *Store) Snapshot(ctx context.Context, id string) (Snapshot, error) {
	var sn Snapshot
	if !IsUUID(id) {
		return sn, ErrNotFound
	}
	err := s.Pool.QueryRow(ctx, `
		SELECT last_event_seq, status, progress, stage, error_code, error_message, updated_at
		FROM analysis_jobs WHERE id = $1`, id).
		Scan(&sn.Seq, &sn.Status, &sn.Progress, &sn.Stage, &sn.ErrorCode, &sn.ErrorMessage, &sn.At)
	if errors.Is(err, pgx.ErrNoRows) {
		return sn, ErrNotFound
	}
	return sn, err
}

// ---- evidence ---------------------------------------------------------------------------------------------

type Evidence struct {
	ID             string          `json:"id"`
	JobID          *string         `json:"job_id"`
	EvidenceType   string          `json:"evidence_type"`
	Source         string          `json:"source"`
	SourceRecordID *string         `json:"source_record_id"`
	ObservedAt     time.Time       `json:"observed_at"`
	RetrievedAt    time.Time       `json:"retrieved_at"`
	Geometry       json.RawMessage `json:"geometry"`
	Properties     json.RawMessage `json:"properties"`
	QualityFlags   []string        `json:"quality_flags"`
	Limitations    []string        `json:"limitations"`
	SourceURL      string          `json:"source_url"`
}

type EvidencePage struct {
	Items      []Evidence `json:"items"`
	NextCursor *string    `json:"next_cursor"`
}

type cursor struct {
	CreatedAt time.Time `json:"c"`
	ID        string    `json:"i"`
}

func encodeCursor(c cursor) string {
	b, _ := json.Marshal(c)
	return base64.RawURLEncoding.EncodeToString(b)
}

func decodeCursor(s string) (*cursor, error) {
	if s == "" {
		return nil, nil
	}
	b, err := base64.RawURLEncoding.DecodeString(s)
	if err != nil {
		return nil, fmt.Errorf("bad cursor")
	}
	var c cursor
	if err := json.Unmarshal(b, &c); err != nil || c.ID == "" {
		return nil, fmt.Errorf("bad cursor")
	}
	return &c, nil
}

var ErrBadCursor = errors.New("bad cursor")

// ListEvidence pages a job's evidence with a keyset cursor on (created_at, id).
func (s *Store) ListEvidence(ctx context.Context, jobID, cursorStr string, limit int, evidenceType string) (EvidencePage, error) {
	page := EvidencePage{Items: []Evidence{}}
	cur, err := decodeCursor(cursorStr)
	if err != nil {
		return page, ErrBadCursor
	}
	var curAt *time.Time
	var curID *string
	if cur != nil {
		curAt, curID = &cur.CreatedAt, &cur.ID
	}
	var typ *string
	if evidenceType != "" {
		typ = &evidenceType
	}
	rows, err := s.Pool.Query(ctx, `
		SELECT id, job_id::text, evidence_type, source, source_record_id, observed_at, retrieved_at,
		       ST_AsGeoJSON(geometry)::text, properties::text, quality_flags, limitations, source_url, created_at
		FROM evidence_items
		WHERE job_id = $1
		  AND ($2::text IS NULL OR evidence_type = $2)
		  AND ($3::timestamptz IS NULL OR (created_at, id) > ($3, $4::text))
		ORDER BY created_at, id
		LIMIT $5`, jobID, typ, curAt, curID, limit+1)
	if err != nil {
		return page, err
	}
	defer rows.Close()
	var lastAt []time.Time
	for rows.Next() {
		var e Evidence
		var geom *string
		var props string
		var created time.Time
		if err := rows.Scan(&e.ID, &e.JobID, &e.EvidenceType, &e.Source, &e.SourceRecordID, &e.ObservedAt,
			&e.RetrievedAt, &geom, &props, &e.QualityFlags, &e.Limitations, &e.SourceURL, &created); err != nil {
			return page, err
		}
		e.Geometry = json.RawMessage("null")
		if geom != nil {
			e.Geometry = json.RawMessage(*geom)
		}
		e.Properties = json.RawMessage(props)
		e.ObservedAt, e.RetrievedAt = e.ObservedAt.UTC(), e.RetrievedAt.UTC()
		page.Items = append(page.Items, e)
		lastAt = append(lastAt, created)
	}
	if err := rows.Err(); err != nil {
		return page, err
	}
	if len(page.Items) > limit {
		page.Items = page.Items[:limit]
		next := encodeCursor(cursor{CreatedAt: lastAt[limit-1], ID: page.Items[limit-1].ID})
		page.NextCursor = &next
	}
	return page, nil
}

// ---- artifacts --------------------------------------------------------------------------------------------

// Artifact returns the metadata JSON of a job's artifact of a type ('report', 'layer'), or ErrNotFound.
func (s *Store) Artifact(ctx context.Context, jobID, artifactType string) (json.RawMessage, error) {
	var meta string
	err := s.Pool.QueryRow(ctx, `
		SELECT metadata::text FROM artifacts WHERE job_id = $1 AND artifact_type = $2
		ORDER BY created_at DESC LIMIT 1`, jobID, artifactType).Scan(&meta)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return json.RawMessage(meta), err
}

// ---- areas ------------------------------------------------------------------------------------------------

type Area struct {
	ID        string          `json:"id"`
	Name      string          `json:"name"`
	Geometry  json.RawMessage `json:"geometry"`
	CreatedAt time.Time       `json:"created_at"`
}

func (s *Store) InsertArea(ctx context.Context, name string, geojson []byte) (Area, error) {
	var a Area
	var geom string
	err := s.Pool.QueryRow(ctx, `
		INSERT INTO areas_of_interest (name, geometry) VALUES ($1, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON($2), 4326)))
		RETURNING id::text, name, ST_AsGeoJSON(geometry)::text, created_at`, name, string(geojson)).
		Scan(&a.ID, &a.Name, &geom, &a.CreatedAt)
	a.Geometry = json.RawMessage(geom)
	return a, err
}

func (s *Store) GetArea(ctx context.Context, id string) (Area, error) {
	var a Area
	if !IsUUID(id) {
		return a, ErrNotFound
	}
	var geom string
	err := s.Pool.QueryRow(ctx, `
		SELECT id::text, name, ST_AsGeoJSON(geometry)::text, created_at FROM areas_of_interest WHERE id = $1`, id).
		Scan(&a.ID, &a.Name, &geom, &a.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return a, ErrNotFound
	}
	a.Geometry = json.RawMessage(geom)
	return a, err
}

// IsUUID is a cheap shape check so malformed ids are 404s, not database cast errors.
func IsUUID(s string) bool {
	if len(s) != 36 {
		return false
	}
	for i, r := range s {
		switch i {
		case 8, 13, 18, 23:
			if r != '-' {
				return false
			}
		default:
			if !strings.ContainsRune("0123456789abcdefABCDEF", r) {
				return false
			}
		}
	}
	return true
}
