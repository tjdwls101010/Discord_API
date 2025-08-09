-- PRD 7.1 exports
create table if not exists public.exports (
  job_id uuid primary key,
  channel_id text not null,
  start_at timestamptz not null,
  end_at timestamptz not null,
  status text not null check (status in ('pending','running','completed','failed')),
  message_count integer not null default 0,
  inserted_count integer not null default 0,
  duration_ms integer,
  error text,
  created_at timestamptz not null default now()
);

create index if not exists exports_channel_created_idx on public.exports (channel_id, created_at desc);
create index if not exists exports_status_created_idx on public.exports (status, created_at desc);

-- PRD 7.2 messages
create table if not exists public.messages (
  message_id text primary key,
  channel_id text not null,
  author_id text,
  author_name text,
  content text,
  timestamp timestamptz,
  attachments jsonb,
  embeds jsonb,
  raw jsonb,
  job_id uuid references public.exports(job_id)
);

create index if not exists messages_channel_timestamp_idx on public.messages (channel_id, timestamp desc);
create index if not exists messages_author_timestamp_idx on public.messages (author_id, timestamp desc);


