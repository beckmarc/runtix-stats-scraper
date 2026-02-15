# Runtix Scraper Project

## Goal
Create database of running times from Runtix.com for analysis across different events and runners.

## Current Status
- Created `runtix_scraper.py` - Python script to extract events and races
- Extracts event names/dates from main events page using `.description .alpha/.omega a`
- Uses CSS selector: `.row.competition .two.columns.omega > a` for event links
- URL pattern: `https://runtix.com/sts/10020/{year}/0` for year-based event listings
- Extracts race distances from `#contest option` elements (5, 10, hm, m)
- Builds race result URLs: `https://runtix.com/sts/10050/{event_id}/{distance}/-/-`
- **Database sync**: Always updates existing records with latest information
- Script includes rate limiting and error handling

## Database Schema (Implemented)
```sql
-- Events (running competitions/meets)
events (id, event_url UNIQUE, name, date, location, year, scraped_at)

-- Races within events (specific distances/types)
races (id, event_id, race_name, distance_km, race_type, is_standard_distance)

-- Runners (unique by name + birth_year)
runners (id, name, club_history, birth_year)

-- Individual race results
race_results (id, race_id, runner_id, finish_time,
              position, age_group, age_group_position, gender, bib_number)
```

**Runner Identification**: Name + Birth Year (Jahrgang) for uniqueness
**Club History**: Stores all clubs a runner has been affiliated with as JSON list
**Standard Distances Focus**: 5K, 10K, Half Marathon (21.0975km), Marathon (42.195km)
**Race Types**: road, cross_country, hill, trail

## Next Steps
1. Test event link extraction
2. Extract individual race results from event pages
3. Parse runner data and times
4. Build database and normalization logic
5. Implement analysis framework

## Setup
Virtual environment exists at `.venv/`
Install dependencies: `pip install -r requirements.txt`

## Tech Stack
Python + BeautifulSoup + Requests + PostgreSQL/SQLite + Pandas