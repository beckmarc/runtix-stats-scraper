import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='numpy')

import streamlit as st
import pandas as pd
import sys
import os

# Add parent directory to path to import database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DatabaseManager, Event, Race, RaceResult

st.set_page_config(
    page_title="Races - Runtix Stats",
    page_icon="🏃",
    layout="wide"
)

def load_races_data():
    """Load races with event information and result counts"""
    # Use absolute path to database file
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtix_data.db")
    db = DatabaseManager(db_path)

    races_data = []

    try:
        races = db.session.query(Race).join(Event).all()
        for race in races:
            # Count results for this race
            result_count = db.session.query(RaceResult).filter_by(race_id=race.id).count()

            races_data.append({
                'race_id': race.id,
                'race_name': race.race_name,
                'distance_km': race.distance_km,
                'race_type': race.race_type,
                'is_standard_distance': race.is_standard_distance,
                'event_id': race.event_id,
                'event_name': race.event.name,
                'event_date': race.event.date,
                'event_year': race.event.year,
                'event_location': race.event.location,
                'result_count': result_count
            })
    except Exception as e:
        st.error(f"Error loading races: {e}")
    finally:
        db.close()

    return pd.DataFrame(races_data)

st.title("🏃 Races")
st.markdown("All race distances from events in the database")

# Load data
races_df = load_races_data()

if races_df.empty:
    st.warning("No races found in the database. Run the scraper to collect race data.")
else:
    # Get unique event names for filtering
    event_names = sorted(races_df['event_name'].unique())

    # Filters
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        selected_event = st.selectbox("Filter by Event", ["All"] + event_names)

    with col2:
        distances = sorted(races_df['distance_km'].unique())
        distance_options = ["All"] + [f"{d}km" for d in distances if pd.notna(d)]
        selected_distance = st.selectbox("Filter by Distance", distance_options)

    with col3:
        race_types = races_df['race_type'].unique()
        race_types = [t for t in race_types if pd.notna(t)]
        selected_type = st.selectbox("Filter by Type", ["All"] + sorted(race_types))

    with col4:
        standard_only = st.checkbox("Standard Distances Only",
                                   help="Show only 5K, 10K, Half Marathon, and Marathon")

    # Filter data
    filtered_races = races_df.copy()

    if selected_event != "All":
        filtered_races = filtered_races[filtered_races['event_name'] == selected_event]

    if selected_distance != "All":
        distance_km = float(selected_distance.replace('km', ''))
        filtered_races = filtered_races[filtered_races['distance_km'] == distance_km]

    if selected_type != "All":
        filtered_races = filtered_races[filtered_races['race_type'] == selected_type]

    if standard_only:
        filtered_races = filtered_races[filtered_races['is_standard_distance'] == 1]

    # Sort by event year and distance
    filtered_races = filtered_races.sort_values(['event_year', 'distance_km'], ascending=[False, True])

    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Races", len(filtered_races))
    with col2:
        total_results = filtered_races['result_count'].sum()
        st.metric("Total Results", total_results)
    with col3:
        unique_events = len(filtered_races['event_name'].unique()) if not filtered_races.empty else 0
        st.metric("Unique Events", unique_events)
    with col4:
        avg_results = filtered_races['result_count'].mean() if not filtered_races.empty else 0
        st.metric("Avg Results per Race", f"{avg_results:.1f}")

    # Display races table
    display_columns = [
        'race_name', 'distance_km', 'race_type', 'event_name',
        'event_date', 'event_year', 'result_count'
    ]
    available_columns = [col for col in display_columns if col in filtered_races.columns]

    # Rename columns for better display
    display_df = filtered_races[available_columns].copy()
    display_df.columns = [
        'Race', 'Distance (km)', 'Type', 'Event',
        'Date', 'Year', 'Results'
    ]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    # Race statistics
    if not filtered_races.empty:
        st.subheader("Race Statistics")

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Most Popular Distances:**")
            distance_counts = filtered_races['distance_km'].value_counts().head(5)
            for distance, count in distance_counts.items():
                st.write(f"- {distance}km: {count} races")

        with col2:
            st.write("**Events with Most Races:**")
            event_counts = filtered_races['event_name'].value_counts().head(5)
            for event, count in event_counts.items():
                st.write(f"- {event}: {count} races")

        # Race details expander
        if len(filtered_races) > 0:
            st.subheader("Race Details")
            race_options = [
                f"{row['race_name']} - {row['event_name']} ({row['event_year']})"
                for _, row in filtered_races.iterrows()
            ]

            selected_race_idx = st.selectbox(
                "Select a race for details:",
                options=range(len(race_options)),
                format_func=lambda x: race_options[x]
            )

            if selected_race_idx is not None:
                race_info = filtered_races.iloc[selected_race_idx]

                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Race:** {race_info['race_name']}")
                    st.write(f"**Distance:** {race_info['distance_km']}km")
                    st.write(f"**Type:** {race_info['race_type']}")
                    st.write(f"**Standard Distance:** {'Yes' if race_info['is_standard_distance'] else 'No'}")

                with col2:
                    st.write(f"**Event:** {race_info['event_name']}")
                    st.write(f"**Date:** {race_info['event_date']}")
                    st.write(f"**Location:** {race_info['event_location']}")
                    st.write(f"**Number of Results:** {race_info['result_count']}")