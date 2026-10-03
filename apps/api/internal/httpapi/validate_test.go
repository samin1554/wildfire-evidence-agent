package httpapi

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

var today = time.Date(2026, 9, 24, 12, 0, 0, 0, time.UTC)

const area = `{"type":"Polygon","coordinates":[[[-117.2,34.1],[-116.95,34.1],[-116.95,34.25],[-117.2,34.25],[-117.2,34.1]]]}`

func body(fields ...string) []byte { return []byte("{" + strings.Join(fields, ",") + "}") }

const (
	q   = `"question":"How badly did it burn?"`
	typ = `"analysis_type":"historical_fire_impact"`
	dr  = `"date_range":{"start":"2024-08-01","end":"2024-10-31"}`
	ar  = `"area":` + area
)

func TestValidateCreateAcceptsTheContractExample(t *testing.T) {
	b, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "contracts", "examples", "openapi", "CreateAnalysisRequest.line-fire.json"))
	if err != nil {
		t.Fatal(err)
	}
	v, e := ValidateCreate(b, today)
	if e != nil {
		t.Fatalf("contract example rejected: %v", e)
	}
	if v.AnalysisType != "historical_fire_impact" || v.Start != "2024-01-01" || len(v.Area) == 0 {
		t.Fatalf("unexpected parse: %+v", v)
	}
}

func TestValidateCreateRejections(t *testing.T) {
	cases := []struct {
		name, code string
		body       []byte
	}{
		{"unknown field", "INVALID_REQUEST", body(q, typ, dr, ar, `"extra":1`)},
		{"not json", "INVALID_REQUEST", []byte("{")},
		{"missing question", "INVALID_REQUEST", body(typ, dr, ar)},
		{"empty question", "INVALID_REQUEST", body(`"question":""`, typ, dr, ar)},
		{"too long question", "INVALID_REQUEST", body(`"question":"`+strings.Repeat("x", 2001)+`"`, typ, dr, ar)},
		{"unknown type", "UNKNOWN_ANALYSIS_TYPE", body(q, `"analysis_type":"flood"`, dr, ar)},
		{"bad date", "INVALID_REQUEST", body(q, typ, `"date_range":{"start":"2024-13-01","end":"2024-10-31"}`, ar)},
		{"end before start", "INVALID_REQUEST", body(q, typ, `"date_range":{"start":"2024-10-01","end":"2024-09-01"}`, ar)},
		{"range too long", "DATE_RANGE_TOO_LONG", body(q, typ, `"date_range":{"start":"2020-01-01","end":"2024-10-31"}`, ar)},
		{"future", "INVALID_REQUEST", body(q, typ, `"date_range":{"start":"2026-09-01","end":"2026-12-31"}`, ar)},
		{"no area", "INVALID_REQUEST", body(q, typ, dr)},
		{"both area and id", "INVALID_REQUEST", body(q, typ, dr, ar, `"area_id":"x"`)},
		{"point", "INVALID_GEOMETRY", body(q, typ, dr, `"area":{"type":"Point","coordinates":[-117,34]}`)},
		{"open ring", "INVALID_GEOMETRY", body(q, typ, dr, `"area":{"type":"Polygon","coordinates":[[[-117,34],[-116.9,34],[-116.9,34.1],[-117,34.1]]]}`)},
		{"lat out of range", "INVALID_GEOMETRY", body(q, typ, dr, `"area":{"type":"Polygon","coordinates":[[[-117,34],[-116.9,95],[-116.9,34.1],[-117,34]]]}`)},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, e := ValidateCreate(c.body, today)
			if e == nil {
				t.Fatal("expected a validation error")
			}
			if e.Code != c.code || e.Status != 422 {
				t.Fatalf("got %d %s (%s), want 422 %s", e.Status, e.Code, e.Message, c.code)
			}
		})
	}
}

func TestRateLimiter(t *testing.T) {
	l := NewRateLimiter(2, time.Minute)
	now := time.Now()
	if !l.Allow("a", now) || !l.Allow("a", now) || l.Allow("a", now) {
		t.Fatal("third request in the window should be refused")
	}
	if !l.Allow("b", now) {
		t.Fatal("other clients are independent")
	}
	if !l.Allow("a", now.Add(time.Minute)) {
		t.Fatal("a new window allows again")
	}
}
