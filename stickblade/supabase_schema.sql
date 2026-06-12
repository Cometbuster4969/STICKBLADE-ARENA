-- STICKBLADE ARENA — Supabase schema
-- Run this once in: Supabase Dashboard -> SQL Editor -> New query -> Run
-- Then create a Storage bucket named: replays   (private is fine)

create table if not exists matches (
    id          text primary key,
    created     double precision,
    model_a     text,
    model_b     text,
    sharp       text,
    status      text,            -- queued | running | done | error
    winner_side text,            -- a | b | draw
    method      text,
    turns       integer,
    error       text,
    blind       boolean default true,
    voted       boolean default false
);

create table if not exists votes (
    id        text primary key,
    match_id  text references matches(id),
    created   double precision,
    choice    text               -- a | b | draw
);

create table if not exists elo (
    model   text,
    sharp   text,
    rating  double precision default 1000,
    wins    integer default 0,
    losses  integer default 0,
    draws   integer default 0,
    primary key (model, sharp)
);

create index if not exists idx_matches_created on matches (created desc);
create index if not exists idx_elo_sharp on elo (sharp, rating desc);

-- The backend uses the service_role key (bypasses RLS), so RLS can stay
-- enabled with no public policies = tables are NOT readable by anonymous users.
alter table matches enable row level security;
alter table votes   enable row level security;
alter table elo     enable row level security;
