// Package httpapi implements contracts/openapi.yaml. Presentation and validation only: no scientific
// calculations, no provider calls (AGENTS.md). The worker owns every job status after `queued`.
package httpapi

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"github.com/samin1554/inland-resilience/apps/api/internal/queue"
	"github.com/samin1554/inland-resilience/apps/api/internal/store"
)

type Server struct {
	Store        *store.Store
	Queue        *queue.Queue
	ArtifactsDir string
	Now          func() time.Time
	Limiter      *RateLimiter
	KeepAlive    time.Duration
}

func (s *Server) Routes() http.Handler {
	if s.Now == nil {
		s.Now = time.Now
	}
	if s.Limiter == nil {
		s.Limiter = NewRateLimiter(30, time.Minute)
	}
	if s.KeepAlive == 0 {
		s.KeepAlive = 15 * time.Second
	}
	r := chi.NewRouter()
	r.Use(middleware.RequestID, middleware.RealIP, middleware.Recoverer, requestLog)
	r.Get("/health", s.health)
	r.Route("/v1", func(r chi.Router) {
		r.With(s.Limiter.Middleware).Post("/analyses", s.createAnalysis)
		r.Get("/analyses/{id}", s.getAnalysis)
		r.Get("/analyses/{id}/events", s.streamEvents)
		r.Get("/analyses/{id}/evidence", s.listEvidence)
		r.Get("/analyses/{id}/layers", s.listLayers)
		r.Get("/analyses/{id}/report", s.getReport)
		r.Post("/analyses/{id}/cancel", s.cancelAnalysis)
		r.With(s.Limiter.Middleware).Post("/areas", s.createArea)
		r.Get("/areas/{id}", s.getArea)
		r.Get("/tiles/{layer}/{z}/{x}/{y}.png", s.tile)
		r.Get("/activity", s.activity)
	})
	r.NotFound(func(w http.ResponseWriter, _ *http.Request) {
		writeError(w, &APIError{Status: 404, Code: "NOT_FOUND", Message: "No such endpoint."})
	})
	return r
}

func requestLog(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ww := middleware.NewWrapResponseWriter(w, r.ProtoMajor)
		start := time.Now()
		next.ServeHTTP(ww, r)
		slog.Info("request", "method", r.Method, "path", r.URL.Path, "status", ww.Status(), "ms", time.Since(start).Milliseconds())
	})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, e *APIError) {
	writeJSON(w, e.Status, e)
}

var notFound = &APIError{Status: 404, Code: "NOT_FOUND", Message: "Not found."}

// internal logs the cause and returns a generic 500 (no internals leak to the client).
func internal(w http.ResponseWriter, err error) {
	slog.Error("internal error", "err", err)
	writeError(w, &APIError{Status: 500, Code: "INTERNAL", Message: "Something went wrong on our side."})
}

func storeErr(w http.ResponseWriter, err error) {
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, notFound)
		return
	}
	internal(w, err)
}
