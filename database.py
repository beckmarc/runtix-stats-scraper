from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timezone
import json

Base = declarative_base()

class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True)
    event_url = Column(String, unique=True, nullable=False)
    name = Column(String)
    date = Column(String)
    location = Column(String)
    year = Column(Integer)
    scraped_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship to races within this event
    races = relationship("Race", back_populates="event")

class Race(Base):
    __tablename__ = 'races'

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    race_name = Column(String)  # e.g., "5K", "10K", "Half Marathon"
    distance_km = Column(Float)  # Standardized distance in kilometers
    race_type = Column(String)  # e.g., "road", "cross_country", "hill", "trail"
    is_standard_distance = Column(Integer, default=0)  # 1 for 5K, 10K, half, marathon

    # Relationships
    event = relationship("Event", back_populates="races")
    results = relationship("RaceResult", back_populates="race")

class Runner(Base):
    __tablename__ = 'runners'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    club_history = Column(Text)  # JSON string storing list of clubs
    birth_year = Column(Integer)

    # Relationship to race results
    results = relationship("RaceResult", back_populates="runner")

    def __repr__(self):
        clubs = self.get_clubs()
        current_club = clubs[-1] if clubs else "No club"
        return f"<Runner(name='{self.name}', birth_year={self.birth_year}, current_club='{current_club}')>"

    def get_clubs(self):
        """Get list of clubs from JSON string"""
        if not self.club_history:
            return []
        try:
            return json.loads(self.club_history)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_clubs(self, clubs):
        """Set clubs list as JSON string"""
        if clubs:
            self.club_history = json.dumps(clubs)
        else:
            self.club_history = None

    def add_club(self, club):
        """Add a new club to the history if it's not already present"""
        if not club or not club.strip():
            return False

        clubs = self.get_clubs()
        club = club.strip()

        # Only add if not already in history
        if club not in clubs:
            clubs.append(club)
            self.set_clubs(clubs)
            return True
        return False

    @property
    def current_club(self):
        """Get the most recent club"""
        clubs = self.get_clubs()
        return clubs[-1] if clubs else None

class RaceResult(Base):
    __tablename__ = 'race_results'

    id = Column(Integer, primary_key=True)
    race_id = Column(Integer, ForeignKey('races.id'))
    runner_id = Column(Integer, ForeignKey('runners.id'))
    finish_time = Column(String)  # Format: "HH:MM:SS"
    position = Column(Integer)
    age_group = Column(String)
    age_group_position = Column(Integer)
    gender = Column(String)
    bib_number = Column(String)

    # Relationships
    race = relationship("Race", back_populates="results")
    runner = relationship("Runner", back_populates="results")

    def __repr__(self):
        return f"<RaceResult(runner='{self.runner.name if self.runner else 'Unknown'}', time='{self.finish_time}', position={self.position})>"

class DatabaseManager:
    def __init__(self, db_path="runtix_data.db"):
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    def add_event(self, event_url, name=None, date=None, location=None, year=None):
        """Add or update an event in the database with latest information"""
        existing_event = self.session.query(Event).filter_by(event_url=event_url).first()

        if existing_event:
            # Update existing event with latest information
            updated = False
            if name and existing_event.name != name:
                existing_event.name = name
                updated = True
            if date and existing_event.date != date:
                existing_event.date = date
                updated = True
            if location and existing_event.location != location:
                existing_event.location = location
                updated = True
            if year and existing_event.year != year:
                existing_event.year = year
                updated = True

            if updated:
                existing_event.scraped_at = datetime.now(timezone.utc)
                self.session.commit()

            return existing_event

        # Create new event
        event = Event(
            event_url=event_url,
            name=name,
            date=date,
            location=location,
            year=year
        )
        self.session.add(event)
        self.session.commit()
        return event

    def add_race(self, event_id, race_name, distance_km=None, race_type=None):
        """Add or update a race for an event with latest information"""
        # Check if race already exists for this event
        existing_race = self.session.query(Race).filter_by(
            event_id=event_id, race_name=race_name
        ).first()

        # Determine if this is a standard distance
        is_standard = self._is_standard_distance(distance_km, race_name)

        if existing_race:
            # Update existing race with latest information
            updated = False
            if distance_km and existing_race.distance_km != distance_km:
                existing_race.distance_km = distance_km
                updated = True
            if race_type and existing_race.race_type != race_type:
                existing_race.race_type = race_type
                updated = True
            if existing_race.is_standard_distance != is_standard:
                existing_race.is_standard_distance = is_standard
                updated = True

            if updated:
                self.session.commit()

            return existing_race

        # Create new race
        race = Race(
            event_id=event_id,
            race_name=race_name,
            distance_km=distance_km,
            race_type=race_type,
            is_standard_distance=is_standard
        )
        self.session.add(race)
        self.session.commit()
        return race

    def _is_standard_distance(self, distance_km, race_name):
        """Check if this is a standard distance (5K, 10K, half marathon, marathon)"""
        if distance_km:
            # Check by exact distance
            standard_distances = [5.0, 10.0, 21.0975, 42.195]  # 5K, 10K, half, marathon
            return any(abs(distance_km - std) < 0.1 for std in standard_distances)

        if race_name:
            # Check by name patterns - more specific detection
            name_lower = race_name.lower()

            # Check for marathon (full marathon only, not half)
            if 'marathon' in name_lower and 'half' not in name_lower and 'halbmarathon' not in name_lower:
                return True
            # Check for half marathon
            if 'halbmarathon' in name_lower or ('half' in name_lower and 'marathon' in name_lower):
                return True
            # Check for other standard distances
            if any(pattern in name_lower for pattern in ['5k', '5km', '10k', '10km']):
                return True

        return False

    def parse_distance_from_name(self, race_name):
        """Extract distance in km from race name"""
        if not race_name:
            return None

        name_lower = race_name.lower()

        # Standard distances
        if '5k' in name_lower:
            return 5.0
        elif '10k' in name_lower:
            return 10.0
        elif 'halbmarathon' in name_lower or ('half' in name_lower and 'marathon' in name_lower):
            return 21.0975
        elif 'marathon' in name_lower and 'half' not in name_lower and 'halbmarathon' not in name_lower:
            return 42.195

        # Try to extract numeric distance
        import re
        km_match = re.search(r'(\d+(?:\.\d+)?)\s*km', name_lower)
        if km_match:
            return float(km_match.group(1))

        return None

    def add_runner(self, name, club=None, birth_year=None):
        """Add or update a runner with latest information"""
        # Use name and birth_year for unique identification (club is irrelevant for uniqueness)
        existing_runner = self.session.query(Runner).filter_by(name=name, birth_year=birth_year).first()

        if existing_runner:
            # Add new club to history if provided and not already present
            if club:
                club_added = existing_runner.add_club(club)
                if club_added:
                    self.session.commit()
            return existing_runner

        # Create new runner with initial club history
        runner = Runner(name=name, birth_year=birth_year)
        if club:
            runner.set_clubs([club])
        self.session.add(runner)
        self.session.commit()
        return runner

    def add_race_result(self, race_id, runner_id, finish_time=None, position=None,
                       age_group=None, age_group_position=None, gender=None, bib_number=None):
        """Add or update a race result with latest information"""
        # Check if result already exists
        existing_result = self.session.query(RaceResult).filter_by(
            race_id=race_id, runner_id=runner_id
        ).first()

        if existing_result:
            # Update existing result with latest information
            updated = False
            if finish_time and existing_result.finish_time != finish_time:
                existing_result.finish_time = finish_time
                updated = True
            if position and existing_result.position != position:
                existing_result.position = position
                updated = True
            if age_group and existing_result.age_group != age_group:
                existing_result.age_group = age_group
                updated = True
            if age_group_position and existing_result.age_group_position != age_group_position:
                existing_result.age_group_position = age_group_position
                updated = True
            if gender and existing_result.gender != gender:
                existing_result.gender = gender
                updated = True
            if bib_number and existing_result.bib_number != bib_number:
                existing_result.bib_number = bib_number
                updated = True

            if updated:
                self.session.commit()

            return existing_result

        # Create new result
        result = RaceResult(
            race_id=race_id,
            runner_id=runner_id,
            finish_time=finish_time,
            position=position,
            age_group=age_group,
            age_group_position=age_group_position,
            gender=gender,
            bib_number=bib_number
        )
        self.session.add(result)
        self.session.commit()
        return result


    def event_exists(self, event_url):
        """Check if an event already exists in the database"""
        existing_event = self.session.query(Event).filter_by(event_url=event_url).first()
        return existing_event is not None

    def event_fully_processed(self, event_url):
        """Check if an event has been fully processed (has race results)"""
        existing_event = self.session.query(Event).filter_by(event_url=event_url).first()
        if not existing_event:
            return False

        # Check if any races for this event have results
        races_with_results = (self.session.query(Race)
                            .join(RaceResult)
                            .filter(Race.event_id == existing_event.id)
                            .count())

        return races_with_results > 0

    def get_events(self, year=None):
        """Get all events, optionally filtered by year"""
        query = self.session.query(Event)
        if year:
            query = query.filter_by(year=year)
        return query.all()

    def get_races(self, event_id=None, standard_only=False):
        """Get all races, optionally filtered by event or standard distances"""
        query = self.session.query(Race)
        if event_id:
            query = query.filter_by(event_id=event_id)
        if standard_only:
            query = query.filter_by(is_standard_distance=1)
        return query.all()

    def get_runners(self, name_search=None):
        """Get all runners, optionally filtered by name"""
        query = self.session.query(Runner)
        if name_search:
            query = query.filter(Runner.name.ilike(f'%{name_search}%'))
        return query.all()

    def get_runner_results(self, runner_id, standard_distances_only=False):
        """Get all race results for a specific runner"""
        query = self.session.query(RaceResult).filter_by(runner_id=runner_id)
        if standard_distances_only:
            query = query.join(Race).filter(Race.is_standard_distance == 1)
        return query.all()

    def get_race_results(self, race_id):
        """Get all race results for a specific race"""
        return self.session.query(RaceResult).filter_by(race_id=race_id).all()

    def get_results_by_distance(self, distance_km, tolerance=0.1):
        """Get all results for a specific distance"""
        return (self.session.query(RaceResult)
                .join(Race)
                .filter(Race.distance_km.between(distance_km - tolerance, distance_km + tolerance))
                .all())

    def get_standard_distance_results(self):
        """Get all results for standard distances (5K, 10K, half, marathon)"""
        return (self.session.query(RaceResult)
                .join(Race)
                .filter(Race.is_standard_distance == 1)
                .all())

    def close(self):
        """Close the database session"""
        self.session.close()