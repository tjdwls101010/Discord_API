# Discord Message Archiver API (FastAPI)

## Quickstart (Local Docker)

```bash
# Build (Apple Silicon ok)
docker build --platform=linux/amd64 -t discord-archiver:dev .

# Run
export DISCORD_TOKEN=...  # do not commit
export SUPABASE_URL=...
export SUPABASE_KEY=...
export DEFAULT_CHANNEL_ID=...

docker run --rm --platform=linux/amd64 -p 8000:8000 \
  -e DISCORD_TOKEN -e SUPABASE_URL -e SUPABASE_KEY -e DEFAULT_CHANNEL_ID \
  discord-archiver:dev
```

## Endpoints
- GET `/health`
- POST `/exports` → `{ job_id }`
- GET `/exports/{job_id}` → export status row

## Env Vars
- `DISCORD_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`, `DEFAULT_CHANNEL_ID`

## Migrations
Apply SQL in `supabase/migrations/*.sql` in Supabase SQL editor.

