-- Data-test / exploration queries for the loaded hackathon DB.
-- Run any block with:
--   docker compose exec -T postgres psql -U hackathon -d hotel_hackathon -c "<query>"
-- or open a shell: docker compose exec postgres psql -U hackathon -d hotel_hackathon
-- Apply sql/views.sql first.

-- ======================================================================
-- A. SANITY / GRAIN
-- ======================================================================

-- rows vs reservations vs room nights (row != reservation != room night)
select count(*) rows, count(distinct reservation_id) reservations, sum(number_of_spaces) room_nights
from reservations_hackathon;

-- no duplicate (reservation_id, stay_date) — fact grain
select count(*) - count(distinct (reservation_id, stay_date)) as dup_pairs
from reservations_hackathon;

-- status / financial mix
select reservation_status, financial_status, count(*)
from reservations_hackathon group by 1,2 order by 1,2;

-- ======================================================================
-- B. /verify RECONCILIATION (exact oracles for the anchor day)
-- ======================================================================

-- lookup counts: expect 3 / 8 / 10 / 11 / 4
select 'room_type' t, count(*) n from room_type_lookup
union all select 'rate_plan', count(*) from rate_plan_lookup
union all select 'market', count(*) from market_code_lookup
union all select 'macro_history', count(*) from market_macro_group_history
union all select 'channel', count(*) from channel_code_lookup order by 1;

-- verify: total_stay_rows 542, total_reservations 254, cancelled 22,
--         provisional_row_count 5, property_date_mismatch_count 3
select
  (select count(*) from reservations_hackathon) total_stay_rows,
  (select count(distinct reservation_id) from reservations_hackathon) total_reservations,
  (select count(distinct reservation_id) from reservations_hackathon where reservation_status='Cancelled') cancelled_res,
  (select count(*) from reservations_hackathon where financial_status='Provisional') provisional_rows,
  (select count(*) from reservations_hackathon where property_date <> stay_date) property_date_mismatch;

-- verify: POSTED OTB (stay_date >= today) -> room_nights 642, room_rev 114567, total_rev 123297
select sum(number_of_spaces) room_nights,
       round(sum(daily_room_revenue_before_tax),0) room_revenue,
       round(sum(daily_total_revenue_before_tax),0) total_revenue
from vw_stay_night_base where stay_date >= current_date;

-- verify: otb_room_nights_by_market (stay_date >= today)
select market_code, sum(number_of_spaces) room_nights
from vw_stay_night_base where stay_date >= current_date
group by market_code order by market_code;

-- ======================================================================
-- C. TOOL PREVIEWS (what the 5 tools will compute)
-- ======================================================================

-- get_otb_summary: OTB by stay month (Posted, non-cancelled)
select to_char(stay_date,'YYYY-MM') stay_month,
       count(*) row_count,
       count(distinct reservation_id) reservation_count,
       sum(number_of_spaces) room_nights,
       round(sum(daily_room_revenue_before_tax),2) room_revenue,
       round(sum(daily_total_revenue_before_tax),2) total_revenue
from vw_stay_night_base group by 1 order by 1;

-- get_segment_mix: segment shares for a month using EFFECTIVE macro group
-- (shares use one shared denominator = all segments in the month)
with seg as (
  select market_code, market_name, effective_macro_group,
         sum(number_of_spaces) room_nights,
         sum(daily_total_revenue_before_tax) total_revenue
  from vw_segment_stay_night
  where to_char(stay_date,'YYYY-MM') = '2026-07'
  group by 1,2,3
)
select *,
       round(room_nights::numeric / sum(room_nights) over (),4) share_of_room_nights,
       round(total_revenue / sum(total_revenue) over (),4) share_of_revenue
from seg order by total_revenue desc;

-- OTA dependency: OTA share of revenue for a month (Tier D question)
select round(
  sum(daily_total_revenue_before_tax) filter (where market_code='OTA')
  / nullif(sum(daily_total_revenue_before_tax),0), 4) as ota_share_of_revenue
from vw_stay_night_base where to_char(stay_date,'YYYY-MM')='2026-08';

-- get_block_vs_transient_mix: block vs transient + top companies for a month
select is_block,
       sum(number_of_spaces) room_nights,
       round(sum(daily_total_revenue_before_tax),2) total_revenue
from vw_stay_night_base where to_char(stay_date,'YYYY-MM')='2026-09'
group by is_block;

select coalesce(company_name,'Transient') company,
       round(sum(daily_total_revenue_before_tax),2) revenue
from vw_stay_night_base where to_char(stay_date,'YYYY-MM')='2026-09'
group by 1 order by revenue desc limit 5;

-- get_pickup_delta: bookings CREATED in a window (booking date, not stay date)
select count(distinct reservation_id) new_reservations,
       sum(number_of_spaces) new_room_nights,
       round(sum(daily_total_revenue_before_tax),2) new_total_revenue
from vw_stay_night_base
where create_datetime >= (current_date - interval '30 days')
  and stay_date >= current_date;

-- get_as_of_otb: point-in-time OTB (what was on the books as of a past moment)
-- include rows known & live at as_of; cancelled-after-as_of still count
select sum(number_of_spaces) room_nights_as_of
from reservations_hackathon
where to_char(stay_date,'YYYY-MM')='2026-08'
  and create_datetime <= timestamptz '2026-05-01T12:00:00Z'
  and (reservation_status <> 'Cancelled' or cancellation_datetime > timestamptz '2026-05-01T12:00:00Z')
  and financial_status = 'Posted';

-- ======================================================================
-- D. TRAP CHECKS
-- ======================================================================

-- PROM reclassification: effective macro group must flip with stay_date
-- (Retail before 2025-06-01, Leisure Group on/after) -- DO NOT use static lookup
select min(stay_date) first_stay, max(stay_date) last_stay, effective_macro_group, count(*)
from vw_segment_stay_night where market_code='PROM' group by effective_macro_group order by 1;

-- property_date != stay_date rows (audit/night-boundary) -- expect 3
select reservation_id, stay_date, property_date
from reservations_hackathon where property_date <> stay_date order by 1;

-- rate codes present in data but NOT in rate_plan_lookup (Option D: FK relaxed)
select distinct rate_plan_code from reservations_hackathon
where rate_plan_code not in (select rate_plan_code from rate_plan_lookup) order by 1;
