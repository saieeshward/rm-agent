-- Semantic views for Phase 2. The five required tools read from THESE, never
-- from reservations_hackathon directly. Apply after every load:
--   docker compose exec -T postgres psql -U hackathon -d hotel_hackathon -f - < sql/views.sql
--
-- NOTE (Option D): the rate_plan FK on reservations_hackathon is intentionally
-- relaxed at load time (etl/load.py) because the live data uses more granular
-- commercial rate codes than the 8-row rate_plan_lookup, and the dataset
-- changelog says the commercial code IS rate_plan_code. No tool reads
-- rate_plan_code, so this does not affect any view below. See ARCHITECTURE.md.

-- Default on-the-books universe: Posted + non-cancelled, stay-night grain.
create or replace view public.vw_stay_night_base as
select
  r.*
from public.reservations_hackathon r
where r.reservation_status <> 'Cancelled'
  and r.financial_status = 'Posted';

-- Segment view: base + market_name + stay-date-effective macro_group.
-- macro_group is effective-dated (e.g. PROM: Retail -> Leisure Group at
-- 2025-06-01), so we resolve it against market_macro_group_history on stay_date
-- and fall back to the static lookup only when no history row matches.
create or replace view public.vw_segment_stay_night as
select
  b.*,
  coalesce(h.macro_group, m.macro_group) as effective_macro_group,
  m.market_name
from public.vw_stay_night_base b
join public.market_code_lookup m on m.market_code = b.market_code
left join lateral (
  select h.macro_group
  from public.market_macro_group_history h
  where h.market_code = b.market_code
    and b.stay_date >= h.valid_from
    and (h.valid_to is null or b.stay_date < h.valid_to)
  order by h.valid_from desc
  limit 1
) h on true;
