package httpapi

import (
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/samin1554/inland-resilience/apps/api/internal/store"
)

// parseBBox reads "west,south,east,north" (WGS84). An empty string means no filter.
func parseBBox(s string) (*[4]float64, *APIError) {
	if s == "" {
		return nil, nil
	}
	parts := strings.Split(s, ",")
	if len(parts) != 4 {
		return nil, invalid("INVALID_REQUEST", "bbox must be west,south,east,north.")
	}
	var b [4]float64
	for i, p := range parts {
		v, err := strconv.ParseFloat(strings.TrimSpace(p), 64)
		if err != nil {
			return nil, invalid("INVALID_REQUEST", "bbox values must be numbers.")
		}
		b[i] = v
	}
	if b[0] < -180 || b[2] > 180 || b[1] < -90 || b[3] > 90 || b[0] >= b[2] || b[1] >= b[3] {
		return nil, invalid("INVALID_REQUEST", "bbox must be west<east and south<north in WGS84.")
	}
	return &b, nil
}

// GET /v1/activity: the worker's latest clustered heat-detection snapshot (ADR-013). Read-only; no provider calls.
func (s *Server) activity(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	bbox, e := parseBBox(q.Get("bbox"))
	if e != nil {
		writeError(w, e)
		return
	}
	limit := 20
	if l := q.Get("limit"); l != "" {
		n, err := strconv.Atoi(l)
		if err != nil || n < 1 || n > 50 {
			writeError(w, invalid("INVALID_REQUEST", "limit must be an integer from 1 to 50."))
			return
		}
		limit = n
	}
	snap, err := s.Store.LatestActivity(r.Context(), bbox, limit)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, &APIError{Status: http.StatusServiceUnavailable, Code: "ACTIVITY_NOT_READY",
			Message: "The activity feed hasn't been built yet; it refreshes every 30 minutes."})
		return
	} else if err != nil {
		internal(w, err)
		return
	}
	w.Header().Set("Cache-Control", "public, max-age=60")
	writeJSON(w, http.StatusOK, snap)
}
