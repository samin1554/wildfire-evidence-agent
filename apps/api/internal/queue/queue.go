// Package queue is the API's side of Redis Streams (ADR-002/004):
// XADD to `jobs` for new analyses, and one shared XREAD loop on `job-events` fanned out to SSE subscribers.
package queue

import (
	"context"
	"encoding/json"
	"log/slog"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	JobsStream   = "jobs"
	EventsStream = "job-events"
)

// JobMessage is contracts/analysis-job.schema.json.
type JobMessage struct {
	SchemaVersion string          `json:"schema_version"`
	JobID         string          `json:"job_id"`
	AnalysisType  string          `json:"analysis_type"`
	Question      string          `json:"question"`
	Area          json.RawMessage `json:"area"`
	DateRange     DateRange       `json:"date_range"`
	RequestedAt   time.Time       `json:"requested_at"`
}

type DateRange struct {
	Start string `json:"start"`
	End   string `json:"end"`
}

// Event is one job-event; Raw is the exact payload the worker published (forwarded to the browser unchanged).
type Event struct {
	JobID  string `json:"job_id"`
	Seq    int    `json:"seq"`
	Status string `json:"status"`
	Raw    []byte `json:"-"`
}

func Terminal(status string) bool {
	return status == "completed" || status == "failed" || status == "cancelled"
}

type Queue struct {
	R *redis.Client

	mu   sync.Mutex
	subs map[string]map[chan Event]struct{}
}

func New(url string) (*Queue, error) {
	opt, err := redis.ParseURL(url)
	if err != nil {
		return nil, err
	}
	return &Queue{R: redis.NewClient(opt), subs: map[string]map[chan Event]struct{}{}}, nil
}

func (q *Queue) Enqueue(ctx context.Context, m JobMessage) error {
	b, err := json.Marshal(m)
	if err != nil {
		return err
	}
	return q.R.XAdd(ctx, &redis.XAddArgs{Stream: JobsStream, Values: map[string]any{"payload": string(b)}}).Err()
}

// Subscribe returns a channel of live events for one job. Call the returned func to unsubscribe.
func (q *Queue) Subscribe(jobID string) (<-chan Event, func()) {
	ch := make(chan Event, 64)
	q.mu.Lock()
	if q.subs[jobID] == nil {
		q.subs[jobID] = map[chan Event]struct{}{}
	}
	q.subs[jobID][ch] = struct{}{}
	q.mu.Unlock()
	return ch, func() {
		q.mu.Lock()
		delete(q.subs[jobID], ch)
		if len(q.subs[jobID]) == 0 {
			delete(q.subs, jobID)
		}
		q.mu.Unlock()
	}
}

func (q *Queue) dispatch(ev Event) {
	q.mu.Lock()
	defer q.mu.Unlock()
	for ch := range q.subs[ev.JobID] {
		select {
		case ch <- ev:
		default: // slow client: it reconciles from the DB snapshot when it reconnects
		}
	}
}

// Run is the single XREAD loop (plain XREAD, no consumer group: every API instance sees every event).
func (q *Queue) Run(ctx context.Context) {
	last := "$"
	for ctx.Err() == nil {
		res, err := q.R.XRead(ctx, &redis.XReadArgs{Streams: []string{EventsStream, last}, Block: 5 * time.Second, Count: 100}).Result()
		if err == redis.Nil {
			continue
		}
		if err != nil {
			if ctx.Err() == nil {
				slog.Warn("job-events read failed; retrying", "err", err)
				time.Sleep(time.Second)
			}
			continue
		}
		for _, s := range res {
			for _, m := range s.Messages {
				last = m.ID
				if ev, ok := parse(m); ok {
					q.dispatch(ev)
				}
			}
		}
	}
}

func parse(m redis.XMessage) (Event, bool) {
	payload, _ := m.Values["payload"].(string)
	var ev Event
	if err := json.Unmarshal([]byte(payload), &ev); err != nil || ev.JobID == "" {
		return ev, false
	}
	ev.Raw = []byte(payload)
	return ev, true
}

// History returns a job's events with after < seq < before, oldest first, from the (trimmed) stream.
func (q *Queue) History(ctx context.Context, jobID string, after, before int) ([]Event, error) {
	msgs, err := q.R.XRevRangeN(ctx, EventsStream, "+", "-", 5000).Result()
	if err != nil {
		return nil, err
	}
	var out []Event
	for i := len(msgs) - 1; i >= 0; i-- {
		if ev, ok := parse(msgs[i]); ok && ev.JobID == jobID && ev.Seq > after && ev.Seq < before {
			out = append(out, ev)
		}
	}
	return out, nil
}
