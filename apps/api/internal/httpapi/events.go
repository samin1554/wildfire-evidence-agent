package httpapi

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/samin1554/inland-resilience/apps/api/internal/queue"
	"github.com/samin1554/inland-resilience/apps/api/internal/store"
)

type jobEvent struct {
	SchemaVersion string  `json:"schema_version"`
	JobID         string  `json:"job_id"`
	Seq           int     `json:"seq"`
	Status        string  `json:"status"`
	Progress      int     `json:"progress"`
	Stage         string  `json:"stage"`
	Message       *string `json:"message,omitempty"`
	ErrorCode     *string `json:"error_code,omitempty"`
	At            string  `json:"at"`
}

func snapshotEvent(jobID string, sn store.Snapshot) []byte {
	b, _ := json.Marshal(jobEvent{
		SchemaVersion: "1", JobID: jobID, Seq: sn.Seq, Status: sn.Status, Progress: sn.Progress, Stage: sn.Stage,
		Message: sn.ErrorMessage, ErrorCode: sn.ErrorCode, At: sn.At.UTC().Format(time.RFC3339Nano),
	})
	return b
}

// GET /v1/analyses/{id}/events (ADR-002). Events go out in increasing seq:
//  1. history this client hasn't seen (after Last-Event-ID, older than the DB state) from the job-events stream,
//  2. the current state from the database (always, so a reconnect can never miss the final status),
//  3. live events newer than that state, until a terminal status.
func (s *Server) streamEvents(w http.ResponseWriter, r *http.Request) {
	jobID := chi.URLParam(r, "id")
	flusher, ok := w.(http.Flusher)
	if !ok {
		internal(w, fmt.Errorf("streaming unsupported"))
		return
	}
	live, unsubscribe := s.Queue.Subscribe(jobID) // subscribe before the snapshot so nothing falls in between
	defer unsubscribe()
	sn, err := s.Store.Snapshot(r.Context(), jobID)
	if err != nil {
		storeErr(w, err)
		return
	}
	after := -1
	if id := r.Header.Get("Last-Event-ID"); id != "" {
		if n, err := strconv.Atoi(id); err == nil {
			after = n
		}
	}

	h := w.Header()
	h.Set("Content-Type", "text/event-stream")
	h.Set("Cache-Control", "no-cache")
	h.Set("Connection", "keep-alive")
	h.Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)

	send := func(seq int, data []byte) error {
		_, err := fmt.Fprintf(w, "id: %d\ndata: %s\n\n", seq, data)
		flusher.Flush()
		return err
	}

	if after < sn.Seq {
		history, err := s.Queue.History(r.Context(), jobID, after, sn.Seq)
		if err != nil {
			slog.Warn("event history unavailable", "job_id", jobID, "err", err)
		}
		for _, ev := range history {
			if send(ev.Seq, ev.Raw) != nil {
				return
			}
		}
	}
	if after < sn.Seq || r.Header.Get("Last-Event-ID") == "" {
		if send(sn.Seq, snapshotEvent(jobID, sn)) != nil {
			return
		}
	}
	if queue.Terminal(sn.Status) {
		return
	}
	last := sn.Seq
	tick := time.NewTicker(s.KeepAlive)
	defer tick.Stop()
	for {
		select {
		case <-r.Context().Done():
			return
		case <-tick.C:
			if _, err := fmt.Fprint(w, ": keepalive\n\n"); err != nil {
				return
			}
			flusher.Flush()
		case ev := <-live:
			if ev.Seq <= last {
				continue
			}
			last = ev.Seq
			if send(ev.Seq, ev.Raw) != nil || queue.Terminal(ev.Status) {
				return
			}
		}
	}
}
