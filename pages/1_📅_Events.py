import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='numpy')

import streamlit as st
import pandas as pd
import sys
import os

# Add parent directory to path to import database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DatabaseManager, Event, Race

st.set_page_config(
    page_title="Events - Runtix Stats",
    page_icon="📅",
    layout="wide"
)

def load_events_data():
    """Load events and race counts from database"""
    # Use absolute path to database file
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtix_data.db")
    db = DatabaseManager(db_path)

    events_data = []

    try:
        events = db.session.query(Event).all()
        for event in events:
            # Count races for this event
            race_count = db.session.query(Race).filter_by(event_id=event.id).count()

            events_data.append({
                'id': event.id,
                'name': event.name,
                'year': event.year,
                'date': event.date,
                'location': event.location,
                'url': event.event_url,
                'race_count': race_count,
                'scraped_at': event.scraped_at
            })
    except Exception as e:
        st.error(f"Error loading events: {e}")
    finally:
        db.close()

    return pd.DataFrame(events_data)

st.title("📅 Events")
st.markdown("All running events in the database")

# Load data
events_df = load_events_data()

if events_df.empty:
    st.warning("No events found in the database. Run the scraper to collect event data.")
else:
    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        years = sorted(events_df['year'].unique()) if not events_df.empty else []
        selected_year = st.selectbox("Filter by Year", ["All"] + list(years))

    with col2:
        search_term = st.text_input("Search Events", placeholder="Enter event name...")

    with col3:
        min_races = st.number_input("Minimum Races", min_value=0, value=0,
                                   help="Show only events with at least this many races")

    # Filter data
    filtered_events = events_df.copy()

    if selected_year != "All":
        filtered_events = filtered_events[filtered_events['year'] == selected_year]

    if search_term:
        filtered_events = filtered_events[
            filtered_events['name'].str.contains(search_term, case=False, na=False)
        ]

    if min_races > 0:
        filtered_events = filtered_events[filtered_events['race_count'] >= min_races]

    # Sort by year and date
    filtered_events = filtered_events.sort_values(['year', 'date'], ascending=[False, False])

    # Display metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Events", len(filtered_events))
    with col2:
        total_races = filtered_events['race_count'].sum()
        st.metric("Total Races", total_races)
    with col3:
        avg_races = filtered_events['race_count'].mean() if not filtered_events.empty else 0
        st.metric("Avg Races per Event", f"{avg_races:.1f}")

    # Display events table
    display_columns = ['name', 'date', 'year', 'location', 'race_count']
    available_columns = [col for col in display_columns if col in filtered_events.columns]

    # Rename columns for better display
    display_df = filtered_events[available_columns].copy()
    display_df.columns = ['Event Name', 'Date', 'Year', 'Location', 'Races']

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    # Event details expander
    if not filtered_events.empty:
        st.subheader("Event Details")
        selected_event = st.selectbox(
            "Select an event for details:",
            options=filtered_events['name'].tolist(),
            index=0
        )

        if selected_event:
            event_info = filtered_events[filtered_events['name'] == selected_event].iloc[0]

            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Event:** {event_info['name']}")
                st.write(f"**Date:** {event_info['date']}")
                st.write(f"**Year:** {event_info['year']}")
                st.write(f"**Location:** {event_info['location']}")

            with col2:
                st.write(f"**Number of Races:** {event_info['race_count']}")
                st.write(f"**Event URL:** {event_info['url']}")
                st.write(f"**Last Scraped:** {event_info['scraped_at']}")