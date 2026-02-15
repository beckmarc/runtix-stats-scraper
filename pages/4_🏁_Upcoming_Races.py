import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='numpy')

import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import sys
import os
from typing import Dict, List

# Add parent directory to path to import database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DatabaseManager, Runner

st.set_page_config(
    page_title="Upcoming Races - Runtix Stats",
    page_icon="🏁",
    layout="wide"
)

def extract_event_id_from_url(event_url: str) -> str:
    """Extract event ID from Runtix event URL"""
    try:
        url_parts = event_url.rstrip('/').split('/')
        return url_parts[-1]
    except (IndexError, ValueError):
        return None

def get_race_options(event_url: str) -> Dict[str, Dict]:
    """Extract available race distances from an event page"""
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        response = session.get(event_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the contest select element
        contest_select = soup.select_one('#contest')
        if not contest_select:
            return {}

        # Standard distance mapping
        standard_distance_map = {
            '5': {'name': '5K', 'distance_km': 5.0},
            '10': {'name': '10K', 'distance_km': 10.0},
            'hm': {'name': 'Half Marathon', 'distance_km': 21.0975},
            '21': {'name': 'Half Marathon', 'distance_km': 21.0975},
            'm': {'name': 'Marathon', 'distance_km': 42.195}
        }

        available_races = {}
        options = contest_select.find_all('option')

        for option in options:
            value = option.get('value', '').strip()
            if value in standard_distance_map:
                race_info = standard_distance_map[value].copy()
                race_info['option_value'] = value
                race_info['option_text'] = option.get_text(strip=True)
                available_races[value] = race_info

        return available_races

    except Exception as e:
        st.error(f"Error fetching race options: {e}")
        return {}

def build_participant_url(event_url: str, race_value: str) -> str:
    """Build URL for participant list page"""
    event_id = extract_event_id_from_url(event_url)
    if not event_id:
        return None

    # Build participant URL: https://runtix.com/sts/10040/{event_id}/{race_value}
    return f"https://runtix.com/sts/10040/{event_id}/{race_value}"

def scrape_participants(participant_url: str) -> List[Dict]:
    """Scrape participant data from the participants page"""
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        response = session.get(participant_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the competitors table
        competitors_table = soup.select_one('.competitors')
        if not competitors_table:
            return []

        participants = []
        rows = competitors_table.find_all('tr')

        for row in rows:
            # Skip header rows or rows without proper structure
            cols = row.find_all('td')

            # Participant registration pages have 3 columns: number, competitor, nationality
            # Race results pages have 5+ columns including birth_year and age_class
            if len(cols) < 3:
                continue

            try:
                # Extract participant data - registration page structure
                number_cell = cols[0].select_one('.number')
                number = number_cell.get_text(strip=True) if number_cell else ""

                competitor_cell = cols[1]
                name_div = competitor_cell.find('div', recursive=False)
                name = name_div.get_text(strip=True) if name_div else ""

                team_div = competitor_cell.select_one('.team')
                team = team_div.get_text(strip=True) if team_div else ""

                # For registration pages: no birth_year or age_class data available
                # For results pages: these would be in cols[2] and cols[3]
                if len(cols) >= 5:
                    # Results page format
                    birth_year = cols[2].get_text(strip=True)
                    age_class = cols[3].get_text(strip=True)
                    nationality = cols[4].get_text(strip=True)
                else:
                    # Registration page format (only 3 columns)
                    birth_year = ""
                    age_class = ""
                    nationality = cols[2].get_text(strip=True) if len(cols) > 2 else ""

                if name:  # Only add if we have a name
                    participants.append({
                        'number': number,
                        'name': name,
                        'team': team,
                        'birth_year': birth_year,
                        'age_class': age_class,
                        'nationality': nationality
                    })

            except Exception as e:
                st.warning(f"Error parsing participant row: {e}")
                continue

        return participants

    except Exception as e:
        st.error(f"Error scraping participants: {e}")
        return []

def get_runner_pb_info(runner_name: str, birth_year: str, race_distance: float) -> Dict:
    """Get personal best information for a runner from the database using multiple matching strategies"""
    try:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtix_data.db")
        db = DatabaseManager(db_path)

        from database import RaceResult, Race

        runner = None

        # Try exact match with birth year if available
        if birth_year and birth_year.isdigit():
            birth_year_int = int(birth_year)
            runner = db.session.query(Runner).filter_by(
                name=runner_name,
                birth_year=birth_year_int
            ).first()
        else:
            # If no birth year (e.g., from registration page), try name-only match
            # This might match multiple runners, so we take the first one
            runner = db.session.query(Runner).filter_by(
                name=runner_name
            ).first()

        if not runner:
            return {
                'pb_time': 'No data',
                'pb_position': 'No data',
                'races_count': 0,
                'match_type': 'No match (name not in DB)'
            }

        # Get race results for this distance
        results = db.session.query(RaceResult).join(Race).filter(
            RaceResult.runner_id == runner.id,
            Race.distance_km == race_distance,
            RaceResult.finish_time.isnot(None)
        ).all()

        # Sort results by time (convert to seconds for sorting)
        def time_to_seconds_for_sorting(time_str):
            if not time_str:
                return float('inf')
            try:
                time_str = time_str.strip()
                if '.' in time_str:
                    time_str = time_str.split('.')[0]
                parts = time_str.split(':')
                if len(parts) == 3:  # HH:MM:SS
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                elif len(parts) == 2:  # MM:SS
                    return int(parts[0]) * 60 + int(parts[1])
                return float('inf')
            except (ValueError, IndexError):
                return float('inf')

        # Sort by time (fastest first)
        results = sorted(results, key=lambda r: time_to_seconds_for_sorting(r.finish_time))

        if not results:
            return {
                'pb_time': 'No races',
                'pb_position': 'No races',
                'races_count': 0,
                'match_type': 'Found runner, no races at this distance',
                'db_name': runner.name,
                'db_birth_year': runner.birth_year
            }

        # Get personal best (fastest time)
        pb_result = results[0]

        # Determine match type based on whether birth year was used
        if birth_year and birth_year.isdigit():
            match_type = 'Exact match (name + birth year)'
        else:
            match_type = 'Name-only match (no birth year in registration)'

        db.close()

        return {
            'pb_time': pb_result.finish_time,
            'pb_position': pb_result.position,
            'races_count': len(results),
            'match_type': match_type,
            'db_name': runner.name,
            'db_birth_year': runner.birth_year,
            'pb_time_seconds': time_to_seconds_for_sorting(pb_result.finish_time)  # For sorting
        }

    except Exception as e:
        return {
            'pb_time': 'Error',
            'pb_position': 'Error',
            'races_count': 0,
            'match_type': 'Error'
        }

st.title("🏁 Upcoming Races")
st.markdown("View participants and their personal bests for upcoming races")

# URL input
st.subheader("Event Information")
event_url = st.text_input(
    "Event URL",
    value="https://runtix.com/sts/10040/3024",
    help="Enter the Runtix event URL to fetch race information"
)

if event_url:
    # Extract and display event ID
    event_id = extract_event_id_from_url(event_url)

    if event_id:
        st.success(f"Event ID: {event_id}")

        # Fetch race options
        with st.spinner("Fetching race options..."):
            race_options = get_race_options(event_url)

        if race_options:
            st.subheader("Available Races")

            # Create race selection dropdown
            race_choices = {}
            for value, info in race_options.items():
                race_choices[f"{info['name']} ({info['distance_km']}km)"] = value

            if race_choices:
                selected_race_display = st.selectbox(
                    "Select a race distance:",
                    options=list(race_choices.keys())
                )

                if selected_race_display:
                    selected_race_value = race_choices[selected_race_display]
                    selected_race_info = race_options[selected_race_value]

                    st.info(f"Selected: {selected_race_info['name']} - {selected_race_info['distance_km']}km")

                    # Build participant URL and fetch data
                    participant_url = build_participant_url(event_url, selected_race_value)

                    if participant_url:
                        st.subheader("Participants")


                        if st.button("Fetch Participants", type="primary"):
                            with st.spinner("Fetching participant data..."):
                                participants = scrape_participants(participant_url)

                            if participants:
                                st.success(f"Found {len(participants)} participants")

                                # Enhance participant data with PB information
                                enhanced_participants = []
                                progress_bar = st.progress(0)
                                match_stats = {'exact': 0, 'name_only': 0, 'no_match': 0, 'no_races': 0}

                                for i, participant in enumerate(participants):
                                    pb_info = get_runner_pb_info(
                                        participant['name'],
                                        participant['birth_year'],
                                        selected_race_info['distance_km']
                                    )

                                    # Track match statistics
                                    match_type = pb_info.get('match_type', 'No match')
                                    if 'Exact match' in match_type:
                                        match_stats['exact'] += 1
                                    elif 'Name-only match' in match_type:
                                        match_stats['name_only'] += 1
                                    elif 'No match' in match_type:
                                        match_stats['no_match'] += 1
                                    elif 'no races' in match_type.lower():
                                        match_stats['no_races'] += 1

                                    # Create match info tooltip
                                    match_info = ""
                                    if 'db_name' in pb_info:
                                        match_info = f"DB: {pb_info['db_name']} ({pb_info['db_birth_year']})"

                                    enhanced_participant = {
                                        'Number': participant['number'],
                                        'Name': participant['name'],
                                        'Team': participant['team'],
                                        'Birth Year': participant['birth_year'],
                                        'Age Class': participant['age_class'],
                                        'Nationality': participant['nationality'],
                                        'Personal Best': pb_info['pb_time'],
                                        'Best Position': pb_info['pb_position'],
                                        'Races Count': pb_info['races_count'],
                                        'Match Type': match_type,
                                        'DB Info': match_info,
                                        'pb_seconds': pb_info.get('pb_time_seconds', float('inf'))  # For sorting
                                    }
                                    enhanced_participants.append(enhanced_participant)

                                    # Update progress
                                    progress_bar.progress((i + 1) / len(participants))

                                progress_bar.empty()

                                # Sort participants by personal best time
                                # Fastest times first, then participants without PB data
                                enhanced_participants.sort(key=lambda x: x['pb_seconds'])

                                # Create dataframe and remove the sorting column
                                df = pd.DataFrame(enhanced_participants)
                                df = df.drop('pb_seconds', axis=1)  # Remove sorting helper column

                                st.dataframe(
                                    df,
                                    use_container_width=True,
                                    hide_index=True
                                )

                                # Show summary statistics
                                st.subheader("📊 Matching Statistics")

                                col1, col2, col3, col4, col5 = st.columns(5)
                                with col1:
                                    st.metric("Total Participants", len(participants))
                                with col2:
                                    st.metric("Exact Matches", match_stats['exact'])
                                with col3:
                                    st.metric("Name-Only", match_stats['name_only'])
                                with col4:
                                    st.metric("Found, No Races", match_stats['no_races'])
                                with col5:
                                    st.metric("No Match", match_stats['no_match'])

                                # Data quality summary
                                runners_with_pb = match_stats['exact'] + match_stats['name_only']
                                if len(participants) > 0:
                                    match_rate = (runners_with_pb / len(participants)) * 100
                                    st.success(f"🎯 {match_rate:.1f}% of participants have personal best data")

                                # Show detailed breakdown in expandable section
                                with st.expander("📋 View Match Details"):
                                    st.write("**Match Types Explanation:**")
                                    st.write("- **Exact Match**: Name and birth year match exactly")
                                    st.write("- **Name-Only Match**: Birth year not available (registration page), matched by name only")
                                    st.write("- **Found, No Races**: Runner found in database but no races at this distance")
                                    st.write("- **No Match**: No matching runner found in database")

                                    no_races = df[df['Match Type'].str.contains('no races', case=False, na=False)]
                                    if not no_races.empty:
                                        st.write("**Runners Found But No Race Data at This Distance:**")
                                        for _, row in no_races.iterrows():
                                            st.write(f"- {row['Name']} ({row['DB Info']})")

                            else:
                                st.warning("No participants found. The race might not have any registered participants yet.")

                        st.caption(f"Participant URL: {participant_url}")
            else:
                st.warning("No standard distance races found for this event.")
        else:
            st.error("Could not fetch race options. Please check the event URL.")
    else:
        st.error("Could not extract event ID from the URL. Please check the URL format.")
else:
    st.info("Please enter an event URL to get started.")