package httpapi

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"time"
	"unicode/utf8"
)

// MaxRangeDays is the date-range limit (3 years, leap-safe).
const MaxRangeDays = 3*365 + 1

// APIError is contracts/openapi.yaml#/components/schemas/Error.
type APIError struct {
	Status  int            `json:"-"`
	Code    string         `json:"code"`
	Message string         `json:"message"`
	Details map[string]any `json:"details,omitempty"`
}

func (e *APIError) Error() string { return e.Code + ": " + e.Message }

func invalid(code, msg string) *APIError { return &APIError{Status: 422, Code: code, Message: msg} }

type CreateAnalysisRequest struct {
	Question     *string         `json:"question"`
	AnalysisType *string         `json:"analysis_type"`
	Area         json.RawMessage `json:"area"`
	AreaID       *string         `json:"area_id"`
	DateRange    *struct {
		Start *string `json:"start"`
		End   *string `json:"end"`
	} `json:"date_range"`
}

// Validated is a request that passed every check Go can do without the database.
type Validated struct {
	Question     string
	AnalysisType string
	Start, End   string
	Area         json.RawMessage // nil when AreaID is set
	AreaID       *string
}

// decodeStrict rejects unknown fields and trailing data (CreateAnalysisRequest has additionalProperties: false).
func decodeStrict(r io.Reader, v any) *APIError {
	dec := json.NewDecoder(io.LimitReader(r, 2<<20))
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil {
		return invalid("INVALID_REQUEST", "The request body is not valid JSON for this endpoint: "+err.Error())
	}
	if dec.More() {
		return invalid("INVALID_REQUEST", "Unexpected data after the JSON body.")
	}
	return nil
}

// ValidateCreate checks a POST /v1/analyses body in the documented order: shape, analysis_type, dates, area.
// Geometry validity, region and area size are checked afterwards in PostGIS.
func ValidateCreate(body []byte, today time.Time) (Validated, *APIError) {
	var req CreateAnalysisRequest
	var v Validated
	if err := decodeStrict(bytes.NewReader(body), &req); err != nil {
		return v, err
	}
	if req.Question == nil || utf8.RuneCountInString(*req.Question) < 1 || utf8.RuneCountInString(*req.Question) > 2000 {
		return v, invalid("INVALID_REQUEST", "question is required (1 to 2,000 characters).")
	}
	if req.AnalysisType == nil {
		return v, invalid("INVALID_REQUEST", "analysis_type is required.")
	}
	if *req.AnalysisType != "historical_fire_impact" {
		return v, invalid("UNKNOWN_ANALYSIS_TYPE", fmt.Sprintf("Unknown analysis_type %q. Supported: historical_fire_impact.", *req.AnalysisType))
	}
	if req.DateRange == nil || req.DateRange.Start == nil || req.DateRange.End == nil {
		return v, invalid("INVALID_REQUEST", "date_range with start and end (YYYY-MM-DD) is required.")
	}
	start, err1 := time.Parse(time.DateOnly, *req.DateRange.Start)
	end, err2 := time.Parse(time.DateOnly, *req.DateRange.End)
	if err1 != nil || err2 != nil {
		return v, invalid("INVALID_REQUEST", "date_range.start and date_range.end must be dates (YYYY-MM-DD).")
	}
	if end.Before(start) {
		return v, invalid("INVALID_REQUEST", "date_range.end must be on or after date_range.start.")
	}
	if end.Sub(start) > MaxRangeDays*24*time.Hour {
		return v, invalid("DATE_RANGE_TOO_LONG", "Choose a date range of up to 3 years.")
	}
	if end.After(today.UTC().Truncate(24 * time.Hour).Add(24 * time.Hour)) {
		return v, invalid("INVALID_REQUEST", "Dates must not be in the future.")
	}
	hasArea := len(req.Area) > 0 && string(req.Area) != "null"
	if hasArea == (req.AreaID != nil) {
		return v, invalid("INVALID_REQUEST", "Provide exactly one of area (a drawn polygon) or area_id (a saved area).")
	}
	if hasArea {
		if err := checkGeoJSONShape(req.Area); err != nil {
			return v, err
		}
	}
	return Validated{
		Question: *req.Question, AnalysisType: *req.AnalysisType,
		Start: *req.DateRange.Start, End: *req.DateRange.End, Area: req.Area, AreaID: req.AreaID,
	}, nil
}

// checkGeoJSONShape is a structural check (type, rings, coordinate pairs, closed rings, WGS84 ranges).
func checkGeoJSONShape(raw json.RawMessage) *APIError {
	var g struct {
		Type        string          `json:"type"`
		Coordinates json.RawMessage `json:"coordinates"`
	}
	if err := json.Unmarshal(raw, &g); err != nil {
		return invalid("INVALID_GEOMETRY", "area must be a GeoJSON Polygon or MultiPolygon.")
	}
	var polys [][][][]float64
	switch g.Type {
	case "Polygon":
		var p [][][]float64
		if err := json.Unmarshal(g.Coordinates, &p); err != nil {
			return invalid("INVALID_GEOMETRY", "Polygon coordinates must be [[[lon, lat], ...]].")
		}
		polys = [][][][]float64{p}
	case "MultiPolygon":
		if err := json.Unmarshal(g.Coordinates, &polys); err != nil {
			return invalid("INVALID_GEOMETRY", "MultiPolygon coordinates must be [[[[lon, lat], ...]]].")
		}
	default:
		return invalid("INVALID_GEOMETRY", "area must be a GeoJSON Polygon or MultiPolygon.")
	}
	if len(polys) == 0 {
		return invalid("INVALID_GEOMETRY", "The area has no polygons.")
	}
	for _, p := range polys {
		if len(p) == 0 {
			return invalid("INVALID_GEOMETRY", "A polygon has no rings.")
		}
		for _, ring := range p {
			if len(ring) < 4 {
				return invalid("INVALID_GEOMETRY", "Each ring needs at least 4 positions (a closed triangle).")
			}
			for _, pt := range ring {
				if len(pt) < 2 || pt[0] < -180 || pt[0] > 180 || pt[1] < -90 || pt[1] > 90 {
					return invalid("INVALID_GEOMETRY", "Positions must be [longitude, latitude] in WGS84.")
				}
			}
			first, last := ring[0], ring[len(ring)-1]
			if first[0] != last[0] || first[1] != last[1] {
				return invalid("INVALID_GEOMETRY", "Each ring must be closed (first position equals last).")
			}
		}
	}
	return nil
}
