import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='numpy')

import streamlit as st
import pandas as pd
import sys
import os

# Add parent directory to path to import database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DatabaseManager, Runner, RaceResult, Race, Event

st.set_page_config(
    page_title="Runners - Runtix Stats",
    page_icon="👥",
    layout="wide"
)

@st.cache_data(ttl=600)  # Cache for 10 minutes
def load_runners_simple():
    """Load runners with basic info - simplified and cached"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtix_data.db")
    db = DatabaseManager(db_path)

    try:
        # Get runners with race counts using a simple query
        runners = db.session.query(Runner).all()  # Load all runners

        runners_data = []
        for runner in runners:
            # Count races for this runner
            race_count = db.session.query(RaceResult).filter_by(runner_id=runner.id).count()

            # Skip runners with no races
            if race_count == 0:
                continue

            runners_data.append({
                'id': runner.id,
                'name': runner.name,
                'birth_year': runner.birth_year,
                'current_club': runner.current_club,
                'total_races': race_count
            })

        return pd.DataFrame(runners_data)
    finally:
        db.close()


def get_runner_details(runner_id):
    """Get detailed info for a specific runner"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtix_data.db")
    db = DatabaseManager(db_path)

    try:
        runner = db.session.query(Runner).filter_by(id=runner_id).first()
        if not runner:
            return None

        # Get all race results
        results = (db.session.query(RaceResult, Race, Event)
                  .join(Race, RaceResult.race_id == Race.id)
                  .join(Event, Race.event_id == Event.id)
                  .filter(RaceResult.runner_id == runner_id)
                  .filter(RaceResult.finish_time.isnot(None))
                  .order_by(Event.year.desc())
                  .all())

        race_history = []
        for race_result, race, event in results:
            race_history.append({
                'Year': event.year,
                'Event': event.name,
                'Distance': f"{race.distance_km}km",
                'Time': race_result.finish_time,
                'Position': race_result.position
            })

        return {
            'name': runner.name,
            'birth_year': runner.birth_year,
            'current_club': runner.current_club,
            'clubs': runner.get_clubs(),
            'total_races': len(race_history),
            'race_history': race_history
        }
    finally:
        db.close()


st.title("👥 Runners")

# Load runners data
runners_df = load_runners_simple()

if runners_df.empty:
    st.warning("No runners found in the database.")
else:
    # Simple search
    search_name = st.text_input("🔍 Search by name", placeholder="Enter runner name...")

    # Filter data
    if search_name:
        runners_df = runners_df[runners_df['name'].str.contains(search_name, case=False, na=False)]

    # Show stats
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Showing Runners", len(runners_df))
    with col2:
        total_races = runners_df['total_races'].sum()
        st.metric("Total Races", total_races)

    # Display runners in a clickable table
    display_df = runners_df.copy()
    display_df.columns = ['ID', 'Name', 'Birth Year', 'Current Club', 'Total Races']
    display_df = display_df[['Name', 'Birth Year', 'Current Club', 'Total Races']]

    # Show table with selection
    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=400,
        on_select="rerun",
        selection_mode="single-row"
    )

    # Handle row selection
    if event.selection and event.selection.rows:
        selected_row = event.selection.rows[0]
        selected_runner_id = runners_df.iloc[selected_row]['id']
        selected_runner_name = runners_df.iloc[selected_row]['name']

        # Store runner ID and navigate
        st.session_state.selected_runner_id = selected_runner_id
        st.switch_page("pages/Runner_Detail.py")

