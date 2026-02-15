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
    page_title="Runner Detail - Runtix Stats",
    page_icon="👤",
    layout="wide"
)

def get_runner_details(runner_id):
    """Get detailed info for a specific runner"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtix_data.db")
    db = DatabaseManager(db_path)

    try:
        # Convert numpy int64 to regular Python int
        runner_id = int(runner_id)

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
                'Date': event.date,
                'Event': event.name,
                'Distance': f"{race.distance_km}km",
                'Time': race_result.finish_time,
                'Position': race_result.position,
                'Age Group': race_result.age_group
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

# Get runner ID from session state
runner_id = st.session_state.get("selected_runner_id")

if not runner_id:
    st.error("No runner selected. Please go back to the runners list.")
    if st.button("← Back to Runners"):
        st.switch_page("pages/3_👥_Runners.py")
else:
    # Get runner details
    details = get_runner_details(runner_id)

    if not details:
        st.error("Runner not found.")
        if st.button("← Back to Runners"):
            st.switch_page("pages/3_👥_Runners.py")
    else:
        # Navigation
        if st.button("← Back to Runners"):
            st.switch_page("pages/3_👥_Runners.py")

        # Runner header
        st.title(f"👤 {details['name']}")

        # Basic info
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Birth Year", details['birth_year'])
        with col2:
            st.metric("Total Races", details['total_races'])
        with col3:
            st.metric("Current Club", details['current_club'] or "None")

        # Club history
        if len(details['clubs']) > 1:
            st.subheader("🏃‍♂️ Club History")
            st.write(" → ".join(details['clubs']))

        # Race history
        if details['race_history']:
            st.subheader("📅 Complete Race History")
            history_df = pd.DataFrame(details['race_history'])
            st.dataframe(history_df, use_container_width=True, hide_index=True)
        else:
            st.info("No race history found.")