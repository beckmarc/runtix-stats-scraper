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
    page_title="Best Times - Runtix Stats",
    page_icon="🏆",
    layout="wide"
)

@st.cache_data(ttl=600)  # Cache for 10 minutes
def get_best_times(distance_km, limit=100):
    """Get the fastest times for a specific distance"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtix_data.db")
    db = DatabaseManager(db_path)

    try:
        # Query to get fastest times for the distance
        results = (db.session.query(
            RaceResult.finish_time,
            Runner.name,
            Runner.birth_year,
            Event.name.label('event_name'),
            Event.year.label('event_year'),
            RaceResult.position
        )
        .join(Runner, RaceResult.runner_id == Runner.id)
        .join(Race, RaceResult.race_id == Race.id)
        .join(Event, Race.event_id == Event.id)
        .filter(Race.distance_km == distance_km)
        .filter(RaceResult.finish_time.isnot(None))
        .all())

        # Convert to list and sort by time
        times_data = []
        for result in results:
            finish_time, name, birth_year, event_name, event_year, position = result

            # Convert time to seconds for sorting
            try:
                time_parts = finish_time.split(':')
                if len(time_parts) == 3:  # HH:MM:SS or HH:MM:SS.d
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    # Handle seconds with potential decimal
                    seconds_part = time_parts[2]
                    if '.' in seconds_part:
                        seconds_and_decimal = seconds_part.split('.')
                        seconds_int = int(seconds_and_decimal[0])
                        decimal = float('0.' + seconds_and_decimal[1])
                    else:
                        seconds_int = int(seconds_part)
                        decimal = 0.0

                    seconds = hours * 3600 + minutes * 60 + seconds_int + decimal

                elif len(time_parts) == 2:  # MM:SS or MM:SS.d
                    minutes = int(time_parts[0])
                    # Handle seconds with potential decimal
                    seconds_part = time_parts[1]
                    if '.' in seconds_part:
                        seconds_and_decimal = seconds_part.split('.')
                        seconds_int = int(seconds_and_decimal[0])
                        decimal = float('0.' + seconds_and_decimal[1])
                    else:
                        seconds_int = int(seconds_part)
                        decimal = 0.0

                    seconds = minutes * 60 + seconds_int + decimal
                else:
                    continue
            except:
                continue

            times_data.append({
                'rank': 0,  # Will be set after sorting
                'time': finish_time,
                'time_seconds': seconds,
                'name': name,
                'birth_year': birth_year,
                'event': event_name,
                'year': event_year,
                'position': position
            })

        # Sort by time and assign ranks
        times_data.sort(key=lambda x: x['time_seconds'])
        for i, data in enumerate(times_data[:limit], 1):
            data['rank'] = i

        return times_data[:limit]

    finally:
        db.close()

st.title("🏆 Best Times")
st.markdown("View the fastest times across all distances in the database")

# Distance selector
distance_options = {
    "5K": 5.0,
    "10K": 10.0,
    "Half Marathon": 21.0975,
    "Marathon": 42.195
}

col1, col2 = st.columns([1, 3])

with col1:
    selected_distance = st.selectbox(
        "Select distance:",
        list(distance_options.keys()),
        index=0
    )

with col2:
    st.info(f"Showing the fastest 100 times for {selected_distance}")

if selected_distance:
    distance_km = distance_options[selected_distance]

    with st.spinner(f"Loading best {selected_distance} times..."):
        best_times = get_best_times(distance_km, 100)

    if best_times:
        # Show summary stats first
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Record Time", best_times[0]['time'])
        with col2:
            st.metric("Record Holder", best_times[0]['name'])
        with col3:
            st.metric("Record Year", best_times[0]['year'])
        with col4:
            st.metric("Total Times", len(best_times))

        st.subheader(f"Top 100 {selected_distance} Times")

        # Convert to DataFrame for display
        best_times_df = pd.DataFrame(best_times)
        display_df = best_times_df[['rank', 'time', 'name', 'birth_year', 'event', 'year', 'position']]
        display_df.columns = ['Rank', 'Time', 'Runner', 'Birth Year', 'Event', 'Year', 'Position']

        # Display table
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=600
        )

        # Additional stats
        with st.expander("📊 Additional Statistics"):
            col1, col2 = st.columns(2)

            with col1:
                st.write("**Top 10 Runners:**")
                top_10 = display_df.head(10)
                for i, row in top_10.iterrows():
                    st.write(f"{row['Rank']}. {row['Runner']} - {row['Time']}")

            with col2:
                st.write("**Records by Year:**")
                years = best_times_df['year'].value_counts().head(10)
                st.bar_chart(years)

    else:
        st.warning(f"No {selected_distance} times found in the database.")
else:
    st.info("Please select a distance to view the best times.")