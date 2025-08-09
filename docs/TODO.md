# Project TODOs

Status legend: [x] done, [ ] pending, [-] in progress

## Backend/API
- [x] FastAPI scaffold with `/health`
- [x] `POST /exports` (202 with `job_id`), `GET /exports/{job_id}`
- [x] Input validation (ISO8601 UTC, range check)
- [-] Background orchestration with integrity check `inserted_count == message_count`
- [x] `/status` recent jobs listing
- [ ] `/metrics` Prometheus text endpoint (basic counters)
- [ ] Rate limiting `POST /exports` (10/min)

## DCE Wrapper
- [x] CLI integration with token masking
- [x] Support `--media`, `--filter` (MVP still Json only)
- [ ] Error classes and richer stderr parsing

## Supabase/DB
- [x] Schema: `exports`, `messages`, indexes
- [x] RLS enabled + permissive policies for service role
- [x] FK index on `messages(job_id)`
- [ ] Add retention/cleanup task (older exports/messages)

## Observability
- [x] Structured logging (basic prints, masked token)
- [x] JSON logging middleware (request/response, correlation id)
- [x] `/metrics` with http counters and export counters

## Security
- [x] `.env.example` sanitized, `.env` gitignored
- [ ] Rotate any leaked keys/tokens immediately
- [ ] Purge leaked secrets from git history (BFG/filter-repo)

## Deployment
- [x] Dockerfile (Python 3.12 + DCE install)
- [x] Local build/run (Apple Silicon via `--platform=linux/amd64`)
- [ ] Render service creation + env vars + first deploy

## Testing & Perf
- [ ] E2E test with real tokens on a small channel
- [ ] Performance check: ≤10k msgs in ≤30s
- [ ] Unit tests for DCE command generation and DAO error paths

## Docs
- [x] Backend README
- [x] This TODO checklist
- [ ] Operations guide (Render env vars, scaling, logs/metrics)
