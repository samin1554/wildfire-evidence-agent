package httpapi

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/go-chi/chi/v5"
)

// ---- areas --------------------------------------------------------------------------------------------------

func (s *Server) createArea(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name     *string         `json:"name"`
		Geometry json.RawMessage `json:"geometry"`
	}
	if e := decodeStrict(io.LimitReader(r.Body, 2<<20), &req); e != nil {
		writeError(w, e)
		return
	}
	if req.Name == nil || utf8.RuneCountInString(*req.Name) < 1 || utf8.RuneCountInString(*req.Name) > 200 {
		writeError(w, invalid("INVALID_REQUEST", "name is required (1 to 200 characters)."))
		return
	}
	if len(req.Geometry) == 0 || string(req.Geometry) == "null" {
		writeError(w, invalid("INVALID_GEOMETRY", "geometry is required."))
		return
	}
	if e := checkGeoJSONShape(req.Geometry); e != nil {
		writeError(w, e)
		return
	}
	if e := s.checkArea(r, req.Geometry); e != nil {
		writeError(w, e)
		return
	}
	a, err := s.Store.InsertArea(r.Context(), *req.Name, req.Geometry)
	if err != nil {
		internal(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, a)
}

func (s *Server) getArea(w http.ResponseWriter, r *http.Request) {
	a, err := s.Store.GetArea(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, a)
}

// ---- tiles --------------------------------------------------------------------------------------------------

var layerID = regexp.MustCompile(`^[A-Za-z0-9_-]{1,100}$`)

// GET /v1/tiles/{layer}/{z}/{x}/{y}.png serves overlay tiles the worker rendered (ADR-005/009). No provider URL
// ever reaches the browser.
func (s *Server) tile(w http.ResponseWriter, r *http.Request) {
	layer := chi.URLParam(r, "layer")
	z, ez := strconv.Atoi(chi.URLParam(r, "z"))
	x, ex := strconv.Atoi(chi.URLParam(r, "x"))
	y, ey := strconv.Atoi(chi.URLParam(r, "y"))
	if !layerID.MatchString(layer) || ez != nil || ex != nil || ey != nil || z < 0 || z > 22 || x < 0 || y < 0 ||
		x >= 1<<z || y >= 1<<z {
		http.NotFound(w, r)
		return
	}
	path := filepath.Join(s.ArtifactsDir, "tiles", layer, strconv.Itoa(z), strconv.Itoa(x), strconv.Itoa(y)+".png")
	f, err := os.Open(path)
	if err != nil {
		w.Header().Set("Cache-Control", "public, max-age=300")
		http.NotFound(w, r) // no burned pixels in this tile, or outside the layer
		return
	}
	defer f.Close()
	w.Header().Set("Content-Type", "image/png")
	w.Header().Set("Cache-Control", "public, max-age=86400")
	_, _ = io.Copy(w, f)
}

// ---- health -------------------------------------------------------------------------------------------------

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	checks := map[string]string{"postgres": "ok", "redis": "ok"}
	if err := s.Store.Pool.Ping(ctx); err != nil {
		checks["postgres"] = "fail"
	}
	if err := s.Queue.R.Ping(ctx).Err(); err != nil {
		checks["redis"] = "fail"
	}
	status, code := "ok", http.StatusOK
	for _, v := range checks {
		if v != "ok" {
			status, code = "degraded", http.StatusServiceUnavailable
		}
	}
	writeJSON(w, code, map[string]any{"status": status, "checks": checks})
}

// ---- rate limiting -----------------------------------------------------------------------------------------

// RateLimiter is a fixed-window limit per client IP for write endpoints (S3-4). In-memory: fine for one instance.
type RateLimiter struct {
	max    int
	window time.Duration
	mu     sync.Mutex
	hits   map[string]*bucket
}

type bucket struct {
	start time.Time
	n     int
}

func NewRateLimiter(max int, window time.Duration) *RateLimiter {
	return &RateLimiter{max: max, window: window, hits: map[string]*bucket{}}
}

func (l *RateLimiter) Allow(key string, now time.Time) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	b := l.hits[key]
	if b == nil || now.Sub(b.start) >= l.window {
		b = &bucket{start: now}
		l.hits[key] = b
	}
	b.n++
	if len(l.hits) > 10000 { // bound memory
		for k, v := range l.hits {
			if now.Sub(v.start) >= l.window {
				delete(l.hits, k)
			}
		}
	}
	return b.n <= l.max
}

func (l *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil {
			host = r.RemoteAddr
		}
		if !l.Allow(host, time.Now()) {
			w.Header().Set("Retry-After", strconv.Itoa(int(l.window.Seconds())))
			writeError(w, &APIError{Status: http.StatusTooManyRequests, Code: "RATE_LIMITED", Message: "Too many requests; try again in a minute."})
			return
		}
		next.ServeHTTP(w, r)
	})
}
