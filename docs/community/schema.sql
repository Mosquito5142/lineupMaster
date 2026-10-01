-- LineupMaster คอมมูนิตี้ — โครงฐานข้อมูลบน Supabase
-- วิธีใช้: Supabase → SQL Editor → New query → วางทั้งไฟล์นี้ → Run (รันซ้ำได้ ไม่พังของเดิม)
-- ดูขั้นตอนทั้งหมดที่ docs/community-setup.md

-- ไลน์อัพที่แชร์ขึ้นมา (รูปอยู่ใน Storage bucket "lineups" ที่ <owner>/<id>.png)
create table if not exists public.lineups (
  id          uuid primary key default gen_random_uuid(),
  owner       uuid not null default auth.uid() references auth.users(id) on delete cascade,
  owner_name  text not null default '',
  map         text not null,
  side        text not null check (side in ('attack', 'defense')),
  site        text not null default 'a',
  agent       text not null,
  ability     text,
  title       text not null,
  note        text not null default '',
  stand_x     real, stand_y real,
  target_x    real, target_y real,
  image       text not null,             -- path ใน bucket
  sha1        text not null,
  hidden      boolean not null default false,
  created_at  timestamptz not null default now(),
  unique (owner, sha1)                   -- คนเดิมแชร์รูปเดิมซ้ำไม่ได้
);

-- คะแนน "ใช้ได้จริง": คนละ 1 เสียงต่อใบ เปลี่ยนใจได้ (+1 ใช้ได้ / -1 ใช้ไม่ได้)
create table if not exists public.votes (
  lineup_id   uuid not null references public.lineups(id) on delete cascade,
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  value       smallint not null check (value in (-1, 1)),
  note        text not null default '',
  updated_at  timestamptz not null default now(),
  primary key (lineup_id, user_id)
);

alter table public.lineups enable row level security;
alter table public.votes   enable row level security;

-- ล็อกอินแล้วเห็นทุกใบที่ไม่ได้ถูกซ่อน (ของตัวเองเห็นแม้ซ่อน) · แก้/ลบได้เฉพาะของตัวเอง
drop policy if exists "lineups read"   on public.lineups;
drop policy if exists "lineups insert" on public.lineups;
drop policy if exists "lineups update" on public.lineups;
drop policy if exists "lineups delete" on public.lineups;
create policy "lineups read"   on public.lineups for select to authenticated using (not hidden or owner = auth.uid());
create policy "lineups insert" on public.lineups for insert to authenticated with check (owner = auth.uid());
create policy "lineups update" on public.lineups for update to authenticated using (owner = auth.uid());
create policy "lineups delete" on public.lineups for delete to authenticated using (owner = auth.uid());

drop policy if exists "votes read"   on public.votes;
drop policy if exists "votes insert" on public.votes;
drop policy if exists "votes update" on public.votes;
drop policy if exists "votes delete" on public.votes;
create policy "votes read"   on public.votes for select to authenticated using (true);
create policy "votes insert" on public.votes for insert to authenticated with check (user_id = auth.uid());
create policy "votes update" on public.votes for update to authenticated using (user_id = auth.uid());
create policy "votes delete" on public.votes for delete to authenticated using (user_id = auth.uid());

-- รายการที่หน้าเว็บดึงไปโชว์: ไลน์อัพ + จำนวนเสียง + คะแนน Wilson (95%) — 2/2 ไม่ชนะ 45/50
create or replace view public.lineup_feed with (security_invoker = true) as
select l.*,
       coalesce(v.works, 0)  as works,
       coalesce(v.broken, 0) as broken,
       case when coalesce(v.works, 0) + coalesce(v.broken, 0) = 0 then 0
            else ((v.works::float / (v.works + v.broken)) + 1.9208 / (v.works + v.broken)
                  - 1.96 * sqrt(((v.works::float * v.broken) / (v.works + v.broken) + 0.9604)
                                / (v.works + v.broken)) / (v.works + v.broken))
                 / (1 + 3.8416 / (v.works + v.broken))
       end as score
from public.lineups l
left join (
  select lineup_id,
         count(*) filter (where value = 1)  as works,
         count(*) filter (where value = -1) as broken
  from public.votes group by lineup_id
) v on v.lineup_id = l.id;

grant select on public.lineup_feed to authenticated;

-- ที่เก็บรูป: ใครก็เปิดดูรูปได้ (ลิงก์เดาไม่ได้) · อัปโหลด/ลบได้เฉพาะโฟลเดอร์ของตัวเอง <uid>/...
insert into storage.buckets (id, name, public) values ('lineups', 'lineups', true)
on conflict (id) do nothing;

drop policy if exists "lineup images upload" on storage.objects;
drop policy if exists "lineup images delete" on storage.objects;
create policy "lineup images upload" on storage.objects for insert to authenticated
  with check (bucket_id = 'lineups' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "lineup images delete" on storage.objects for delete to authenticated
  using (bucket_id = 'lineups' and (storage.foldername(name))[1] = auth.uid()::text);
