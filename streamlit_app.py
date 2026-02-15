import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='numpy')

import streamlit as st
import pandas as pd
import plotly.express as px
from database import DatabaseManager, Event, Race, Runner, RaceResult

st.set_page_config(
    page_title="Runtix Stats Dashboard",
    page_icon="🏃‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def load_data():
    """Load data from the database with caching"""
    db = DatabaseManager()

    # Convert to DataFrames for easier manipulation
    events_data = []
    races_data = []
    results_data = []

    try:
        # Load events
        events = db.session.query(Event).all()
        for event in events:
            events_data.append({
                'id': event.id,
                'name': event.name,
                'year': event.year,
                'date': event.date,
                'location': event.location,
                'url': event.event_url,
                'scraped_at': event.scraped_at
            })

        # Load races
        races = db.session.query(Race).join(Event).all()
        for race in races:
            races_data.append({
                'race_id': race.id,
                'event_id': race.event_id,
                'event_name': race.event.name,
                'event_year': race.event.year,
                'race_name': race.race_name,
                'distance_km': race.distance_km,
                'race_type': race.race_type,
                'is_standard_distance': race.is_standard_distance
            })

        # Load race results
        results = db.session.query(RaceResult).join(Runner).join(Race).join(Event).all()
        for result in results:
            results_data.append({
                'result_id': result.id,
                'runner_name': result.runner.name,
                'runner_club': result.runner.current_club,
                'runner_club_history': " → ".join(result.runner.get_clubs()) if result.runner.get_clubs() else "",
                'runner_birth_year': result.runner.birth_year,
                'race_name': result.race.race_name,
                'distance_km': result.race.distance_km,
                'race_type': result.race.race_type,
                'is_standard_distance': result.race.is_standard_distance,
                'event_name': result.race.event.name,
                'event_year': result.race.event.year,
                'finish_time': result.finish_time,
                'position': result.position,
                'age_group': result.age_group,
                'age_group_position': result.age_group_position,
                'gender': result.gender,
                'bib_number': result.bib_number
            })
    except Exception as e:
        st.error(f"Error loading data: {e}")
    finally:
        db.close()

    return pd.DataFrame(events_data), pd.DataFrame(races_data), pd.DataFrame(results_data)

def show_overview(events_df, races_df, results_df):
    st.header("📊 Overview")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Total Events", len(events_df))

    with col2:
        st.metric("Total Races", len(races_df))

    with col3:
        standard_races = len(races_df[races_df['is_standard_distance'] == 1]) if not races_df.empty else 0
        st.metric("Standard Distances", standard_races)

    with col4:
        st.metric("Total Results", len(results_df))

    with col5:
        unique_runners = len(results_df['runner_name'].unique()) if not results_df.empty else 0
        st.metric("Unique Runners", unique_runners)

    # Events by Year
    if not events_df.empty:
        st.subheader("Events by Year")
        year_counts = events_df['year'].value_counts().sort_index()
        fig = px.bar(x=year_counts.index, y=year_counts.values,
                     labels={'x': 'Year', 'y': 'Number of Events'},
                     title="Events Distribution by Year")
        st.plotly_chart(fig, use_container_width=True)

    # Race Distances Distribution
    if not races_df.empty:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Race Distance Distribution")
            distance_counts = races_df['distance_km'].value_counts().sort_index()
            if not distance_counts.empty:
                fig = px.bar(x=distance_counts.index, y=distance_counts.values,
                           labels={'x': 'Distance (km)', 'y': 'Number of Races'},
                           title="Races by Distance")
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Race Types")
            type_counts = races_df['race_type'].value_counts()
            if not type_counts.empty:
                fig = px.pie(values=type_counts.values, names=type_counts.index,
                           title="Distribution of Race Types")
                st.plotly_chart(fig, use_container_width=True)

def main():
    st.title("🏃‍♂️ Runtix Running Stats Dashboard")
    st.markdown("---")

    # Load data
    events_df, races_df, results_df = load_data()

    # Navigation
    st.sidebar.header("Navigation")

    # Always show overview as main page
    show_overview(events_df, races_df, results_df)

if __name__ == "__main__":
    main()