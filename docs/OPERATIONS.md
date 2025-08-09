# Operations Guide

## Env Vars
- DISCORD_TOKEN
- SUPABASE_URL
- SUPABASE_KEY
- DEFAULT_CHANNEL_ID

## Local (Docker)
```bash
docker build --platform=linux/amd64 -t discord-archiver:dev .
export DISCORD_TOKEN=... SUPABASE_URL=... SUPABASE_KEY=... DEFAULT_CHANNEL_ID=...
docker run --rm --platform=linux/amd64 -p 8000:8000 \
  -e DISCORD_TOKEN -e SUPABASE_URL -e SUPABASE_KEY -e DEFAULT_CHANNEL_ID \
  discord-archiver:dev
```

## Endpoints
- GET /health
- POST /exports
- GET /exports/{job_id}
- GET /status
- GET /metrics (Prometheus text)

## Supabase
- Apply migrations in `supabase/migrations/*.sql` using the SQL editor.
- Ensure RLS enabled on `exports` and `messages`.

## Render Deploy (summary)
- Create service from Dockerfile
- Set env vars (above)
- Verify `/health`, then small `/exports` job

## Security
- Do not commit `.env`; rotate any leaked keys
- Logs do not print raw tokens; verify by searching console output
