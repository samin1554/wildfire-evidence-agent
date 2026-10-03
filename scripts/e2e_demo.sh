#!/usr/bin/env bash
# End-to-end acceptance for the demo (docs/milestone-1.md "Acceptance"). Run after `make dev`.
# Uses only curl, python3 and docker compose. Crash/retry/cancel checks are deterministic (no timing races):
# a "ghost" consumer takes a message and never acks it, standing in for a worker killed mid-job.
set -euo pipefail
cd "$(dirname "$0")/.."

API=${API:-http://localhost:8080}
COMPOSE="docker compose -f infrastructure/docker-compose.yml $( [ -f .env ] && echo --env-file .env )"
pass=0
ok() { echo "  ✔ $*"; pass=$((pass + 1)); }
fail() { echo "  ✘ $*" >&2; exit 1; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1], {'d': d}))" "$1"; }
redis() { $COMPOSE exec -T redis redis-cli "$@"; }

LINE_FIRE='{"type":"Polygon","coordinates":[[[-117.15,34.1],[-116.97,34.1],[-116.97,34.21],[-117.15,34.21],[-117.15,34.1]]]}'
RECENT='{"type":"Polygon","coordinates":[[[-117.36,34.58],[-117.08,34.58],[-117.08,34.65],[-117.36,34.65],[-117.36,34.58]]]}'
THOMPSON='{"type":"Polygon","coordinates":[[[-121.57,39.51],[-121.47,39.51],[-121.47,39.575],[-121.57,39.575],[-121.57,39.51]]]}'
ALEXANDER='{"type":"Polygon","coordinates":[[[-105.34,40.41],[-105.21,40.41],[-105.21,40.49],[-105.34,40.49],[-105.34,40.41]]]}'
OUTSIDE='{"type":"Polygon","coordinates":[[[-116.7,31.8],[-116.5,31.8],[-116.5,31.95],[-116.7,31.95],[-116.7,31.8]]]}'  # Ensenada, Mexico

post_job() { # question area start end → job id
  curl -sf -X POST "$API/v1/analyses" -H 'Content-Type: application/json' \
    -d "{\"question\":\"$1\",\"analysis_type\":\"historical_fire_impact\",\"area\":$2,\"date_range\":{\"start\":\"$3\",\"end\":\"$4\"}}" |
    json "d['job_id']"
}
wait_status() { # job want timeout_s
  for _ in $(seq 1 "$3"); do
    s=$(curl -sf "$API/v1/analyses/$1" | json "d['status']")
    [[ "$s" == "$2" ]] && return 0
    [[ "$s" == completed || "$s" == failed || "$s" == cancelled ]] && fail "job $1 ended $s, wanted $2"
    sleep 1
  done
  fail "job $1 did not reach $2 within $3 s (last: $s)"
}
restart_worker() { # extra env assignments (e.g. REAPER_IDLE_MS=3000)
  env "$@" $COMPOSE up -d --no-deps --force-recreate --wait worker-jobs >/dev/null 2>&1
}

echo "1. Health"
curl -sf "$API/health" | json "d['status']" | grep -qx ok && ok "api, postgres and redis healthy" || fail "api, postgres and redis healthy"
curl -sf -o /dev/null http://localhost:5173/ && ok "web is serving" || fail "web is serving"

echo "2. Line Fire analysis (fixture data, satellite stage)"
JOB=$(post_job "How badly did the Line Fire burn this area?" "$LINE_FIRE" 2024-08-01 2024-10-31)
ok "202 with job id $JOB"
EVENTS=$(curl -sN --max-time 120 "$API/v1/analyses/$JOB/events")
SEQ=$(echo "$EVENTS" | sed -n 's/^data: //p' | python3 -c "
import json,sys
evs=[json.loads(l) for l in sys.stdin]
seqs=[e['seq'] for e in evs]; sts=[e['status'] for e in evs]
assert seqs==sorted(set(seqs)), seqs
print(','.join(sts))")
[[ "$SEQ" == *processing_satellite*completed ]] || fail "unexpected stages: $SEQ"
ok "SSE in order, stream closed after completed: $SEQ"
REPLAY=$(curl -sN --max-time 10 -H 'Last-Event-ID: 2' "$API/v1/analyses/$JOB/events" | sed -n 's/^data: //p' | python3 -c "
import json,sys; print(','.join(str(json.loads(l)['seq']) for l in sys.stdin))")
[[ "$REPLAY" == 3,* && "$REPLAY" != *,2* ]] && ok "reconnect with Last-Event-ID: 2 replays $REPLAY" || fail "reconnect with Last-Event-ID: 2 replays $REPLAY"

EV=$(curl -sf "$API/v1/analyses/$JOB/evidence?limit=500")
echo "$EV" | python3 -c "
import json,sys
items=json.load(sys.stdin)['items']
assert items, 'no evidence'
for e in items:
    for k in ('source','observed_at','retrieved_at','limitations'): assert e[k] is not None, (k,e['id'])
    assert e['limitations'], e['id']
calc=[e for e in items if e['evidence_type']=='deterministic_calculation']
assert any('dnbr_median' in e['properties'] for e in calc), 'no dNBR'
assert any('ndvi_change_median' in e['properties'] for e in calc), 'no NDVI'
" && ok "evidence has provenance + limitations, dNBR and NDVI calculations" || fail "evidence has provenance + limitations, dNBR and NDVI calculations"
LAYERS=$(curl -sf "$API/v1/analyses/$JOB/layers")
TILE=$(echo "$LAYERS" | python3 -c "
import json,sys
ls=json.load(sys.stdin)['layers']; r=[l for l in ls if l['kind']=='raster'][0]
print(r['tile_template'].replace('{z}','11').replace('{x}','357').replace('{y}','816'))")
[[ $(curl -s -o /dev/null -w '%{http_code}' "$API$TILE") == 200 ]] && ok "dNBR overlay tile served ($TILE)" || fail "dNBR overlay tile served ($TILE)"
REPORT=$(curl -sf "$API/v1/analyses/$JOB/report")
echo "$REPORT" | EVIDENCE="$EV" python3 -c "
import json,os,sys
r=json.load(sys.stdin); ids={e['id'] for e in json.loads(os.environ['EVIDENCE'])['items']}
assert r['confidence'] in ('unverified_detection','corroborated_signal','officially_reported','insufficient_evidence')
assert r['limitations'] and 'trace' not in r
for s in r['sections']: assert set(s['evidence_ids'])<=ids, s['key']
print(r['confidence'])" >/dev/null && ok "report: confidence label, limitations, every citation resolves" || fail "report: confidence label, limitations, every citation resolves"

echo "3. Validation"
CODE=$(curl -s -X POST "$API/v1/analyses" -H 'Content-Type: application/json' \
  -d "{\"question\":\"q\",\"analysis_type\":\"historical_fire_impact\",\"area\":$OUTSIDE,\"date_range\":{\"start\":\"2024-08-01\",\"end\":\"2024-10-31\"}}")
echo "$CODE" | json "d['code']" | grep -qx AREA_OUTSIDE_REGION && ok "Ensenada, Mexico (outside the US) → 422 AREA_OUTSIDE_REGION" || fail "Ensenada, Mexico (outside the US) → 422 AREA_OUTSIDE_REGION"

echo "3b. Thompson Fire (Northern California, statewide region)"
JOBT=$(post_job "How badly did the Thompson Fire burn this area?" "$THOMPSON" 2024-06-20 2024-07-15)
wait_status "$JOBT" completed 90
curl -sf "$API/v1/analyses/$JOBT/report" | json "d['confidence']" | grep -qx officially_reported && ok "Thompson Fire: officially_reported (CAL FIRE perimeter + dNBR)" || fail "Thompson Fire: officially_reported (CAL FIRE perimeter + dNBR)"
curl -sf "$API/v1/analyses/$JOBT/layers" | json "[l['kind'] for l in d['layers']]" | grep -q raster && ok "Thompson Fire: dNBR overlay layer" || fail "Thompson Fire: dNBR overlay layer"

echo "3c. Alexander Mountain Fire (Colorado, national region and NIFC history)"
JOBA=$(post_job "How badly did the Alexander Mountain Fire burn this area?" "$ALEXANDER" 2024-07-01 2024-08-31)
wait_status "$JOBA" completed 90
curl -sf "$API/v1/analyses/$JOBA/report" | json "d['confidence']" | grep -qx officially_reported && ok "Colorado: officially_reported (NIFC perimeter + dNBR)" || fail "Colorado: officially_reported (NIFC perimeter + dNBR)"

echo "3d. Active now (activity feed)"
for _ in $(seq 1 30); do curl -sf "$API/v1/activity" >/dev/null && break; sleep 2; done
ACT=$(curl -sf "$API/v1/activity?limit=5")
echo "$ACT" | json "len(d['clusters']) > 0 and d['data_mode'] in ('live','fixture') and len(d['limitations']) > 0" | grep -qx True && ok "GET /v1/activity: ranked clusters with limitations" || fail "GET /v1/activity: ranked clusters with limitations"
echo "$ACT" | json "all(c['place'] and len(c['place']['state']) == 2 and 'trend' in c and 'persistent_heat_source' in c for c in d['clusters']) and len({s for c in d['clusters'] for s in c['satellites']}) >= 2" | grep -qx True && ok "clusters have county/state, trend and persistence fields, from several satellites" || fail "clusters have county/state, trend and persistence fields, from several satellites"
SUGG=$(echo "$ACT" | python3 -c "import json,sys; c=json.load(sys.stdin)['clusters'][0]; print(json.dumps(c['suggested_area']))")
LAST=$(echo "$ACT" | json "d['clusters'][0]['last_seen'][:10]")
FROM=$(python3 -c "import datetime,sys; print(datetime.date.fromisoformat('$LAST') - datetime.timedelta(days=4))")
JOBC=$(post_job "What do satellites and official sources show in this area over the last few days?" "$SUGG" "$FROM" "$LAST")
wait_status "$JOBC" completed 90
curl -sf "$API/v1/analyses/$JOBC/evidence?evidence_type=satellite_detection" | json "len(d['items']) > 0" | grep -qx True && ok "top cluster's suggested area analyses straight away and finds its detections" || fail "top cluster's suggested area analyses straight away and finds its detections"

echo "4. Recent detections (FIRMS) and honest wording"
JOB2=$(post_job "Were there satellite heat detections here recently?" "$RECENT" 2026-09-19 2026-09-24)
wait_status "$JOB2" completed 60
curl -sf "$API/v1/analyses/$JOB2/evidence?evidence_type=satellite_detection" | json "len(d['items'])" | grep -qv '^0$' && ok "FIRMS detections returned" || fail "FIRMS detections returned"
ALL="$(curl -sf "$API/v1/analyses/$JOB2/report")$(curl -sf "$API/v1/analyses/$JOB/report")"
if echo "$ALL" | grep -qiE 'confirmed fire[^s]|evacuat'; then
  echo "$ALL" | grep -oiE '.{40}(confirmed fire|evacuat).{40}' | grep -viE 'not (a|an officially) confirmed' && fail "forbidden wording"
fi
ok "no 'confirmed fire' claims or evacuation guidance in reports"

echo "5. Emergency questions are declined"
JOB3=$(post_job "Should I evacuate right now?" "$RECENT" 2026-09-19 2026-09-24)
wait_status "$JOB3" failed 30 2>/dev/null || true
curl -sf "$API/v1/analyses/$JOB3" | json "d['error_code']" | grep -qx EMERGENCY_REDIRECT && ok "declined with EMERGENCY_REDIRECT" || fail "declined with EMERGENCY_REDIRECT"

echo "6. Crash recovery: a worker takes a job and dies (ghost consumer never acks)"
$COMPOSE stop worker-jobs >/dev/null 2>&1
JOB4=$(post_job "Crash recovery check" "$LINE_FIRE" 2024-08-01 2024-10-31)
redis XREADGROUP GROUP workers ghost COUNT 1 STREAMS jobs '>' >/dev/null
restart_worker REAPER_IDLE_MS=3000
wait_status "$JOB4" completed 90 && ok "reaper reclaimed the job and it completed" || fail "reaper reclaimed the job and it completed"

echo "7. Repeated failure ends failed / RETRIES_EXHAUSTED and goes to jobs-dead"
restart_worker REAPER_IDLE_MS=2000 FAULT_INJECT=always
JOB5=$(post_job "Retry exhaustion check" "$RECENT" 2026-09-19 2026-09-24)
for _ in $(seq 1 90); do
  s=$(curl -sf "$API/v1/analyses/$JOB5" | json "d['status']"); [[ "$s" == failed ]] && break; sleep 1
done
curl -sf "$API/v1/analyses/$JOB5" | json "d['error_code']" | grep -qx RETRIES_EXHAUSTED && ok "failed with RETRIES_EXHAUSTED" || fail "failed with RETRIES_EXHAUSTED"
redis XRANGE jobs-dead - + | grep -q "$JOB5" && ok "message moved to jobs-dead" || fail "message moved to jobs-dead"

echo "8. Cancel"
$COMPOSE stop worker-jobs >/dev/null 2>&1
JOB6=$(post_job "Cancel check" "$LINE_FIRE" 2024-08-01 2024-10-31)
curl -sf -X POST "$API/v1/analyses/$JOB6/cancel" | json "d['cancel_requested_at'] is not None" | grep -qx True
restart_worker
wait_status "$JOB6" cancelled 30 && ok "cancel requested → cancelled" || fail "cancel requested → cancelled"

printf "\nAll %d checks passed.\n" "$pass"
