-- Enable RLS on public tables
alter table public.exports enable row level security;
alter table public.messages enable row level security;

-- Simple permissive policies for server-side service role (PostgREST uses anon/service roles).
-- Adjust as needed if exposing to anon in the future. For now, allow all for service role.
create policy if not exists exports_service_rw on public.exports
  for all
  using (true)
  with check (true);

create policy if not exists messages_service_rw on public.messages
  for all
  using (true)
  with check (true);

-- Performance: index on FK job_id
create index if not exists messages_job_id_idx on public.messages (job_id);

