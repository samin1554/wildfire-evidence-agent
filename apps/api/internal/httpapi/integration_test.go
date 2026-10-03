package httpapi

// Integration tests against real Postgres/PostGIS + Redis (the `make dev` stack). They skip unless
// TEST_DATABASE_URL and TEST_REDIS_URL are set; `make test-api` sets them when the stack is running.
// A fake worker writes status/events the way the Python job runtime does, so the API is tested on its own.

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/samin1554/inland-resilience/apps/api/internal/queue"
	"github.com/samin1554/inland-resilience/apps/api/internal/store"
)

type stack struct {
	srv *httptest.Server
	st  *store.Store
	q   *queue.Queue
	dir string
}

func setup(t *testing.T) *stack {
	t.Helper()
	dsn, rurl := os.Getenv("TEST_DATABASE_URL"), os.Getenv("TEST_REDIS_URL")
	if dsn == "" || rurl == "" {
		t.Skip("TEST_DATABASE_URL / TEST_REDIS_URL not set (run `make dev` then `make test-api`)")
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	st, err := store.New(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	q, err := queue.New(rurl)
	if err != nil {
		t.Fatal(err)
	}
	q.R.Del(ctx, queue.JobsStream, queue.EventsStream)
	// test jobs never reach the real worker (separate Redis db); delete them so its sweep can't pick them up
	t.Cleanup(func() {
		_, _ = st.Pool.Exec(context.Background(), `DELETE FROM analysis_jobs WHERE question LIKE '[api-test]%'`)
	})
	go q.Run(ctx)
	time.Sleep(200 * time.Millisecond) // let XREAD start at "$"
	dir := t.TempDir()
	s := &Server{Store: st, Queue: q, ArtifactsDir: dir, Now: func() time.Time { return today }, KeepAlive: time.Second}
	srv := httptest.NewServer(s.Routes())
	t.Cleanup(srv.Close)
	return &stack{srv: srv, st: st, q: q, dir: dir}
}

func (s *stack) post(t *testing.T, path, body string) (int, map[string]any) {
	t.Helper()
	res, err := http.Post(s.srv.URL+path, "application/json", strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	var out map[string]any
	_ = json.NewDecoder(res.Body).Decode(&out)
	return res.StatusCode, out
}

func (s *stack) get(t *testing.T, path string) (int, []byte) {
	t.Helper()
	res, err := http.Get(s.srv.URL + path)
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	b, _ := io.ReadAll(res.Body)
	return res.StatusCode, b
}

func create(q, area string) string {
	q = "[api-test] " + q
	return fmt.Sprintf(`{"question":%q,"analysis_type":"historical_fire_impact","date_range":{"start":"2024-08-01","end":"2024-10-31"},"area":%s}`, q, area)
}

// fakeWorker moves a job one step like inland_worker.jobs.store.transition + events.publish.
func fakeWorker(t *testing.T, s *stack, jobID, status string, progress int) {
	t.Helper()
	ctx := context.Background()
	var seq int
	if err := s.st.Pool.QueryRow(ctx, `UPDATE analysis_jobs SET status=$2, progress=$3, stage=$2,
		last_event_seq = last_event_seq + 1, updated_at = now() WHERE id=$1 RETURNING last_event_seq`,
		jobID, status, progress).Scan(&seq); err != nil {
		t.Fatal(err)
	}
	payload, _ := json.Marshal(map[string]any{"schema_version": "1", "job_id": jobID, "seq": seq, "status": status,
		"progress": progress, "stage": status, "at": time.Now().UTC().Format(time.RFC3339Nano)})
	if err := s.q.R.XAdd(ctx, &redis.XAddArgs{Stream: queue.EventsStream, Values: map[string]any{"payload": string(payload)}}).Err(); err != nil {
		t.Fatal(err)
	}
}

func TestCreateValidatesInPostGISAndEnqueues(t *testing.T) {
	s := setup(t)
	code, out := s.post(t, "/v1/analyses", create("How badly did it burn?", area))
	if code != 202 || out["status"] != "queued" {
		t.Fatalf("create: %d %v", code, out)
	}
	jobID := out["job_id"].(string)
	msgs, err := s.q.R.XRange(context.Background(), queue.JobsStream, "-", "+").Result()
	if err != nil || len(msgs) != 1 {
		t.Fatalf("expected one jobs message, got %v %v", msgs, err)
	}
	var m map[string]any
	_ = json.Unmarshal([]byte(msgs[0].Values["payload"].(string)), &m)
	for _, k := range []string{"schema_version", "job_id", "analysis_type", "question", "area", "date_range", "requested_at"} {
		if _, ok := m[k]; !ok {
			t.Fatalf("message missing %s: %v", k, m)
		}
	}
	if m["job_id"] != jobID || m["schema_version"] != "1" || len(m) != 7 {
		t.Fatalf("message does not match analysis-job.schema.json: %v", m)
	}
	code, b := s.get(t, "/v1/analyses/"+jobID)
	if code != 200 || !strings.Contains(string(b), `"status":"queued"`) {
		t.Fatalf("get: %d %s", code, b)
	}
}

func TestCreateRejectsAreasInPostGIS(t *testing.T) {
	s := setup(t)
	cases := map[string]string{
		// Reno, NV: inside California's bounding box, outside its outline (the seeded region polygon decides)
		"AREA_OUTSIDE_REGION": `{"type":"Polygon","coordinates":[[[-119.9,39.45],[-119.7,39.45],[-119.7,39.6],[-119.9,39.6],[-119.9,39.45]]]}`,
		// Central Valley, fully inside California, ~37,000 km²
		"AREA_TOO_LARGE":   `{"type":"Polygon","coordinates":[[[-121.5,36.0],[-119.0,36.0],[-119.0,37.5],[-121.5,37.5],[-121.5,36.0]]]}`,
		"INVALID_GEOMETRY": `{"type":"Polygon","coordinates":[[[-117,34],[-116.9,34.1],[-116.9,34],[-117,34.1],[-117,34]]]}`,
	}
	for want, a := range cases {
		code, out := s.post(t, "/v1/analyses", create("q", a))
		if code != 422 || out["code"] != want {
			t.Errorf("%s: got %d %v", want, code, out)
		}
	}
	// Los Angeles and Oroville are in scope statewide (ADR-011)
	for _, a := range []string{
		`{"type":"Polygon","coordinates":[[[-118.4,34.0],[-118.2,34.0],[-118.2,34.1],[-118.4,34.1],[-118.4,34.0]]]}`,
		`{"type":"Polygon","coordinates":[[[-121.57,39.51],[-121.47,39.51],[-121.47,39.575],[-121.57,39.575],[-121.57,39.51]]]}`,
	} {
		if code, out := s.post(t, "/v1/analyses", create("in scope", a)); code != 202 {
			t.Errorf("in-scope area rejected: %d %v", code, out)
		}
	}
	s.q.R.Del(context.Background(), queue.JobsStream)
	if n, _ := s.q.R.XLen(context.Background(), queue.JobsStream).Result(); n != 0 {
		t.Fatalf("rejected requests must not enqueue (got %d)", n)
	}
}

func TestReportIs409UntilCompletedAndCancelSetsFlag(t *testing.T) {
	s := setup(t)
	_, out := s.post(t, "/v1/analyses", create("q", area))
	jobID := out["job_id"].(string)
	if code, b := s.get(t, "/v1/analyses/"+jobID+"/report"); code != 409 || !strings.Contains(string(b), "JOB_NOT_COMPLETED") {
		t.Fatalf("report before completion: %d %s", code, b)
	}
	if code, b := s.get(t, "/v1/analyses/"+jobID+"/layers"); code != 200 || string(b) != "{\"layers\":[]}\n" {
		t.Fatalf("layers before completion: %d %s", code, b)
	}
	code, c := s.post(t, "/v1/analyses/"+jobID+"/cancel", "")
	if code != 202 || c["cancel_requested_at"] == nil || c["status"] != "queued" {
		t.Fatalf("cancel: %d %v", code, c)
	}
	if code, _ := s.get(t, "/v1/analyses/00000000-0000-0000-0000-000000000000"); code != 404 {
		t.Fatalf("unknown job: %d", code)
	}
	if code, _ := s.get(t, "/v1/analyses/not-a-uuid/evidence"); code != 404 {
		t.Fatalf("malformed id: %d", code)
	}
}

func readEvents(t *testing.T, body io.Reader, n int) []map[string]any {
	t.Helper()
	sc := bufio.NewScanner(body)
	var out []map[string]any
	for sc.Scan() && len(out) < n {
		line := sc.Text()
		if strings.HasPrefix(line, "data: ") {
			var ev map[string]any
			if err := json.Unmarshal([]byte(line[6:]), &ev); err != nil {
				t.Fatal(err)
			}
			out = append(out, ev)
		}
	}
	return out
}

func TestSSEStreamsInOrderReplaysAndClosesOnTerminal(t *testing.T) {
	s := setup(t)
	_, out := s.post(t, "/v1/analyses", create("q", area))
	jobID := out["job_id"].(string)

	res, err := http.Get(s.srv.URL + "/v1/analyses/" + jobID + "/events")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if ct := res.Header.Get("Content-Type"); ct != "text/event-stream" {
		t.Fatalf("content type %q", ct)
	}
	go func() {
		time.Sleep(300 * time.Millisecond)
		fakeWorker(t, s, jobID, "validating", 5)
		fakeWorker(t, s, jobID, "retrieving_data", 20)
		fakeWorker(t, s, jobID, "completed", 100)
	}()
	evs := readEvents(t, res.Body, 4)
	got := []string{}
	for _, e := range evs {
		got = append(got, fmt.Sprint(e["seq"], ":", e["status"]))
	}
	if strings.Join(got, ",") != "0:queued,1:validating,2:retrieving_data,3:completed" {
		t.Fatalf("events: %v", got)
	}
	if _, err := io.ReadAll(res.Body); err != nil { // the server closes the stream after `completed`
		t.Fatal(err)
	}

	// reconnect after seq 1: the missed history, then the DB state; nothing older, then the stream ends
	req, _ := http.NewRequest("GET", s.srv.URL+"/v1/analyses/"+jobID+"/events", nil)
	req.Header.Set("Last-Event-ID", "1")
	res2, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer res2.Body.Close()
	evs = readEvents(t, res2.Body, 10)
	got = got[:0]
	for _, e := range evs {
		got = append(got, fmt.Sprint(e["seq"], ":", e["status"]))
	}
	if strings.Join(got, ",") != "2:retrieving_data,3:completed" {
		t.Fatalf("replay: %v", got)
	}
}

func TestEvidencePagingAndTiles(t *testing.T) {
	s := setup(t)
	_, out := s.post(t, "/v1/analyses", create("q", area))
	jobID := out["job_id"].(string)
	ctx := context.Background()
	for i := 0; i < 3; i++ {
		_, err := s.st.Pool.Exec(ctx, `INSERT INTO evidence_items (job_id, id, evidence_type, source, observed_at,
			retrieved_at, geometry, properties, quality_flags, limitations, source_url)
			VALUES ($1, $2, 'satellite_detection', 'NASA FIRMS', now(), now(), ST_SetSRID(ST_MakePoint(-117, 34.1), 4326),
			'{"confidence":"nominal"}', '{}', '{"A thermal anomaly is not an officially confirmed wildfire."}', 'https://firms.modaps.eosdis.nasa.gov/')`,
			jobID, fmt.Sprintf("ev-%d", i))
		if err != nil {
			t.Fatal(err)
		}
	}
	code, b := s.get(t, "/v1/analyses/"+jobID+"/evidence?limit=2")
	var page struct {
		Items []map[string]any `json:"items"`
		Next  *string          `json:"next_cursor"`
	}
	_ = json.Unmarshal(b, &page)
	if code != 200 || len(page.Items) != 2 || page.Next == nil {
		t.Fatalf("page 1: %d %s", code, b)
	}
	if page.Items[0]["geometry"].(map[string]any)["type"] != "Point" || page.Items[0]["limitations"] == nil {
		t.Fatalf("evidence shape: %v", page.Items[0])
	}
	_, b = s.get(t, "/v1/analyses/"+jobID+"/evidence?limit=2&cursor="+*page.Next)
	_ = json.Unmarshal(b, &page)
	if len(page.Items) != 1 || page.Next != nil {
		t.Fatalf("page 2: %s", b)
	}
	if code, _ := s.get(t, "/v1/analyses/"+jobID+"/evidence?evidence_type=official_perimeter"); code != 200 {
		t.Fatalf("filter: %d", code)
	}
	if code, _ := s.get(t, "/v1/analyses/"+jobID+"/evidence?cursor=garbage"); code != 422 {
		t.Fatalf("bad cursor: %d", code)
	}
	// tiles
	path := s.dir + "/tiles/dnbr-x/12/714/1633.png"
	_ = os.MkdirAll(path[:strings.LastIndex(path, "/")], 0o755)
	_ = os.WriteFile(path, []byte("\x89PNG"), 0o644)
	if code, _ := s.get(t, "/v1/tiles/dnbr-x/12/714/1633.png"); code != 200 {
		t.Fatalf("tile: %d", code)
	}
	for _, p := range []string{"/v1/tiles/dnbr-x/12/714/9999.png", "/v1/tiles/..%2f..%2fetc/1/0/0.png", "/v1/tiles/dnbr-x/30/0/0.png"} {
		if code, _ := s.get(t, p); code != 404 {
			t.Fatalf("%s: %d", p, code)
		}
	}
	if code, b := s.get(t, "/health"); code != 200 || !strings.Contains(string(b), `"status":"ok"`) {
		t.Fatalf("health: %d %s", code, b)
	}
}
