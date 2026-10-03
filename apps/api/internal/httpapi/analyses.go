package httpapi

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"

	"github.com/samin1554/inland-resilience/apps/api/internal/queue"
	"github.com/samin1554/inland-resilience/apps/api/internal/store"
)

var evidenceTypes = map[string]bool{
	"satellite_detection": true, "satellite_measurement": true, "official_perimeter": true,
	"official_hazard_zone": true, "weather_observation": true, "weather_forecast": true, "weather_alert": true,
	"air_quality_observation": true, "deterministic_calculation": true, "agent_inference": true,
}

// checkArea runs the PostGIS checks: parseable, valid, inside the region, under the size limit.
func (s *Server) checkArea(r *http.Request, area json.RawMessage) *APIError {
	c, err := s.Store.CheckGeometry(r.Context(), area)
	if err != nil {
		slog.Error("geometry check failed", "err", err)
		return &APIError{Status: 500, Code: "INTERNAL", Message: "Could not check the area."}
	}
	switch {
	case c.ParseFailed:
		return invalid("INVALID_GEOMETRY", "The area could not be read as GeoJSON.")
	case !c.Valid:
		e := invalid("INVALID_GEOMETRY", "The polygon is not valid (for example, its edges cross).")
		e.Details = map[string]any{"reason": c.Reason}
		return e
	case !c.InRegion:
		return invalid("AREA_OUTSIDE_REGION", "The area must be inside the United States (the 50 states and DC).")
	case c.AreaKm2 > store.MaxAreaKm2:
		e := invalid("AREA_TOO_LARGE", fmt.Sprintf("Choose an area under %d km².", store.MaxAreaKm2))
		e.Details = map[string]any{"area_km2": int(c.AreaKm2), "max_km2": store.MaxAreaKm2}
		return e
	}
	return nil
}

// POST /v1/analyses: validate, insert `queued`, XADD `jobs`, return 202 at once.
func (s *Server) createAnalysis(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(io.LimitReader(r.Body, 2<<20))
	if err != nil {
		writeError(w, invalid("INVALID_REQUEST", "Could not read the request body."))
		return
	}
	v, apiErr := ValidateCreate(body, s.Now())
	if apiErr != nil {
		writeError(w, apiErr)
		return
	}
	area := v.Area
	if v.AreaID != nil {
		a, err := s.Store.GetArea(r.Context(), *v.AreaID)
		if errors.Is(err, store.ErrNotFound) {
			writeError(w, invalid("INVALID_REQUEST", "area_id does not match a saved area."))
			return
		} else if err != nil {
			internal(w, err)
			return
		}
		area = a.Geometry
	}
	if e := s.checkArea(r, area); e != nil {
		writeError(w, e)
		return
	}
	job, err := s.Store.InsertJob(r.Context(), store.NewJob{
		Question: v.Question, AnalysisType: v.AnalysisType, DateStart: v.Start, DateEnd: v.End, Area: area, AreaID: v.AreaID,
	})
	if err != nil {
		internal(w, err)
		return
	}
	msg := queue.JobMessage{
		SchemaVersion: "1", JobID: job.ID, AnalysisType: v.AnalysisType, Question: v.Question, Area: area,
		DateRange: queue.DateRange{Start: v.Start, End: v.End}, RequestedAt: job.CreatedAt.UTC(),
	}
	if err := s.Queue.Enqueue(r.Context(), msg); err != nil {
		// the job row exists as `queued`; the worker's sweep re-enqueues it, so the API never writes status here
		slog.Warn("could not publish job; the worker sweep will pick it up", "job_id", job.ID, "err", err)
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": job.ID, "status": job.Status, "created_at": job.CreatedAt.UTC()})
}

func (s *Server) getAnalysis(w http.ResponseWriter, r *http.Request) {
	job, err := s.Store.GetJob(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, job)
}

func (s *Server) cancelAnalysis(w http.ResponseWriter, r *http.Request) {
	job, err := s.Store.RequestCancel(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusAccepted, job)
}

func (s *Server) listEvidence(w http.ResponseWriter, r *http.Request) {
	job, err := s.Store.GetJob(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		storeErr(w, err)
		return
	}
	q := r.URL.Query()
	limit := 100
	if l := q.Get("limit"); l != "" {
		n, err := strconv.Atoi(l)
		if err != nil || n < 1 || n > 500 {
			writeError(w, invalid("INVALID_REQUEST", "limit must be an integer from 1 to 500."))
			return
		}
		limit = n
	}
	typ := q.Get("evidence_type")
	if typ != "" && !evidenceTypes[typ] {
		writeError(w, invalid("INVALID_REQUEST", "Unknown evidence_type."))
		return
	}
	page, err := s.Store.ListEvidence(r.Context(), job.ID, q.Get("cursor"), limit, typ)
	if errors.Is(err, store.ErrBadCursor) {
		writeError(w, invalid("INVALID_REQUEST", "cursor is not valid; start again without it."))
		return
	} else if err != nil {
		internal(w, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func (s *Server) listLayers(w http.ResponseWriter, r *http.Request) {
	job, err := s.Store.GetJob(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		storeErr(w, err)
		return
	}
	meta, err := s.Store.Artifact(r.Context(), job.ID, "layer")
	if errors.Is(err, store.ErrNotFound) {
		writeJSON(w, http.StatusOK, map[string]any{"layers": []any{}}) // nothing yet (job still running)
		return
	} else if err != nil {
		internal(w, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write(meta) // stored as {"layers": [...]} by the worker
}

func (s *Server) getReport(w http.ResponseWriter, r *http.Request) {
	job, err := s.Store.GetJob(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		storeErr(w, err)
		return
	}
	if job.Status != "completed" {
		msg := "The analysis hasn't finished yet."
		if queue.Terminal(job.Status) {
			msg = fmt.Sprintf("The analysis ended %s, so there is no report.", job.Status)
		}
		writeError(w, &APIError{Status: http.StatusConflict, Code: "JOB_NOT_COMPLETED", Message: msg,
			Details: map[string]any{"status": job.Status}})
		return
	}
	meta, err := s.Store.Artifact(r.Context(), job.ID, "report")
	if err != nil {
		storeErr(w, err)
		return
	}
	var report map[string]json.RawMessage
	if err := json.Unmarshal(meta, &report); err != nil {
		internal(w, err)
		return
	}
	delete(report, "trace") // the worker's run trace stays server-side (tool_executions has the full record)
	writeJSON(w, http.StatusOK, report)
}
