import requests
from bs4 import BeautifulSoup
import time
from urllib.parse import urljoin
from typing import List, Dict
import logging
from database import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RuntixScraper:
    def __init__(self, delay: float = 1.0, db_path: str = "runtix_data.db"):
        """
        Initialize the Runtix scraper.

        Args:
            delay: Delay between requests in seconds to be respectful to the server
            db_path: Path to the SQLite database file
        """
        self.base_url = "https://runtix.com"
        self.delay = delay
        self.db = DatabaseManager(db_path)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def _time_to_seconds_for_validation(self, time_str):
        """Convert time string to seconds for validation purposes only"""
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

    def get_event_links(self, year: int) -> List[Dict[str, str]]:
        """
        Extract all event links for a given year.

        Args:
            year: The year to scrape events for

        Returns:
            List of dictionaries containing event information
        """
        url = f"{self.base_url}/sts/10020/{year}/0"
        logger.info(f"Fetching events for year {year} from: {url}")

        try:
            response = self.session.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find all competition rows
            competition_rows = soup.select('.row.competition')

            events = []
            for row in competition_rows:
                # Extract event link from .two.columns.omega > a
                link_element = row.select_one('.two.columns.omega > a')
                if not link_element:
                    continue

                href = link_element.get('href')
                if not href:
                    continue

                # Convert relative URLs to absolute URLs
                full_url = urljoin(self.base_url, href)

                # Extract event date from .description .alpha a
                date_element = row.select_one('.description .alpha a')
                event_date = date_element.get_text(strip=True) if date_element else None

                # Extract event name from .description .omega a
                name_element = row.select_one('.description .omega a')
                event_name = name_element.get_text(strip=True) if name_element else link_element.get_text(strip=True)

                # Store event in database
                event_obj = self.db.add_event(
                    event_url=full_url,
                    name=event_name,
                    date=event_date,
                    year=year
                )

                events.append({
                    'name': event_name,
                    'date': event_date,
                    'url': full_url,
                    'year': year,
                    'db_id': event_obj.id
                })

                logger.info(f"Found event: {event_name} on {event_date}")

            logger.info(f"Found {len(events)} events for year {year}")
            return events

        except requests.RequestException as e:
            logger.error(f"Error fetching events for year {year}: {e}")
            return []

        except Exception as e:
            logger.error(f"Unexpected error while parsing events for year {year}: {e}")
            return []

    def get_events_multiple_years(self, years: List[int]) -> List[Dict[str, str]]:
        """
        Extract event links for multiple years.

        Args:
            years: List of years to scrape

        Returns:
            Combined list of all events across the specified years
        """
        all_events = []

        for year in years:
            events = self.get_event_links(year)
            all_events.extend(events)

            # Be respectful to the server
            if len(years) > 1:
                time.sleep(self.delay)

        return all_events


    def extract_race_options(self, event_url):
        """
        Extract available race distances from an event page.

        Args:
            event_url: URL of the event page

        Returns:
            Dictionary mapping race values to race info
        """
        logger.info(f"Extracting race options from: {event_url}")

        try:
            response = self.session.get(event_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find the contest select element
            contest_select = soup.select_one('#contest')
            if not contest_select:
                logger.warning(f"No #contest element found on {event_url}")
                return {}

            # Extract option values for standard distances
            standard_distance_map = {
                '5': {'name': '5K', 'distance_km': 5.0},
                '10': {'name': '10K', 'distance_km': 10.0},
                'hm': {'name': 'Half Marathon', 'distance_km': 21.0975},
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
                    logger.info(f"Found standard distance: {race_info['name']} (value: {value})")

            logger.info(f"Found {len(available_races)} standard distance races")
            return available_races

        except requests.RequestException as e:
            logger.error(f"Error fetching race options from {event_url}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error parsing race options from {event_url}: {e}")
            return {}

    def build_race_result_url(self, event_url, race_value):
        """
        Build the race result URL for a specific distance.

        Args:
            event_url: Original event URL (e.g., https://runtix.com/sts/10050/2882)
            race_value: Race distance value ('5', '10', 'hm', 'm')

        Returns:
            URL for the race results page
        """
        # Extract event ID from the URL
        # Expected format: https://runtix.com/sts/10050/2882
        try:
            url_parts = event_url.rstrip('/').split('/')
            event_id = url_parts[-1]

            # Build result URL: https://runtix.com/sts/10050/2882/{val}/-/-
            result_url = f"https://runtix.com/sts/10050/{event_id}/{race_value}/-/-"
            return result_url
        except (IndexError, ValueError) as e:
            logger.error(f"Failed to parse event ID from URL {event_url}: {e}")
            return None

    def scrape_event_races(self, event_url, event_db_id, test_mode=True):
        """
        Scrape all standard distance races for a specific event.

        Args:
            event_url: URL of the event page
            event_db_id: Database ID of the event
            test_mode: If True, only log URLs without scraping results

        Returns:
            List of race information dictionaries
        """
        logger.info(f"Scraping races for event: {event_url}")

        # Extract available race options
        race_options = self.extract_race_options(event_url)
        if not race_options:
            logger.warning(f"No standard distance races found for event: {event_url}")
            return []

        races_data = []

        for race_value, race_info in race_options.items():
            # Add race to database
            race_obj = self.db.add_race(
                event_id=event_db_id,
                race_name=race_info['name'],
                distance_km=race_info['distance_km'],
                race_type='road'  # Default to road, can be updated later
            )

            # Build race result URL
            result_url = self.build_race_result_url(event_url, race_value)
            if result_url:
                race_data = {
                    'race_db_id': race_obj.id,
                    'race_name': race_info['name'],
                    'distance_km': race_info['distance_km'],
                    'race_value': race_value,
                    'result_url': result_url
                }
                races_data.append(race_data)

                if test_mode:
                    logger.info(f"Race result URL: {result_url}")
                else:
                    # Extract actual race results
                    race_results = self.extract_race_results(result_url, race_obj.id)
                    race_data['results_count'] = len(race_results)
                    logger.info(f"Extracted {len(race_results)} results from {result_url}")

            # Be respectful to the server
            time.sleep(self.delay)

        return races_data

    def extract_race_results(self, result_url, race_db_id):
        """
        Extract race results from a race result URL.

        Args:
            result_url: URL of the race results page
            race_db_id: Database ID of the race

        Returns:
            List of race result dictionaries
        """
        logger.info(f"Extracting race results from: {result_url}")

        try:
            response = self.session.get(result_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find the results table
            results_table = soup.select_one('table.results')
            if not results_table:
                logger.warning(f"No results table found on {result_url}")
                return []

            # Find all result rows (skip header row)
            result_rows = results_table.select('tr')[1:]  # Skip header row

            results_data = []
            previous_time_seconds = 0  # Track previous time to detect incomplete laps

            for row in result_rows:
                try:
                    # Extract data using specific CSS class selectors

                    # Extract position (overall)
                    position_cell = row.select_one('.col-place-total div')
                    position = int(position_cell.get_text(strip=True)) if position_cell else None

                    # Extract gender position (not currently used but kept for future use)
                    # gender_position_cell = row.select_one('.col-place-sex div')
                    # gender_position = int(gender_position_cell.get_text(strip=True)) if gender_position_cell else None

                    # Extract age group position
                    age_group_position_cell = row.select_one('.col-place-ageclass div')
                    age_group_position = int(age_group_position_cell.get_text(strip=True)) if age_group_position_cell else None

                    # Extract bib number
                    bib_cell = row.select_one('.col-number .number')
                    bib_number = bib_cell.get_text(strip=True) if bib_cell else None

                    # Extract runner name
                    name_cell = row.select_one('.col-competitor div')
                    runner_name = name_cell.get_text(strip=True) if name_cell else None

                    # Extract team/club
                    team_cell = row.select_one('.col-team div')
                    club = team_cell.get_text(strip=True) if team_cell else None

                    # Extract birth year
                    birth_cell = row.select_one('.col-birth a')
                    birth_year = None
                    if birth_cell:
                        try:
                            birth_year = int(birth_cell.get_text(strip=True))
                        except ValueError:
                            pass

                    # Extract age group
                    age_group_cell = row.select_one('.col-ageclass a')
                    age_group = age_group_cell.get_text(strip=True) if age_group_cell else None

                    # Extract nationality (not currently used but kept for future use)
                    # nationality_cell = row.select_one('.col-nationality a')
                    # nationality = nationality_cell.get_text(strip=True) if nationality_cell else None

                    # Extract finish time (can be .col-time or .col-net-time)
                    time_cell = row.select_one('.col-time a') or row.select_one('.col-net-time a')
                    finish_time = time_cell.get_text(strip=True) if time_cell else None

                    # Validate time to detect incomplete laps (DNF cases)
                    if finish_time:
                        current_time_seconds = self._time_to_seconds_for_validation(finish_time)
                        # If current time is significantly less than previous time, stop processing
                        # This indicates incomplete laps or DNF runners at the end
                        if current_time_seconds < previous_time_seconds * 0.8:  # 20% threshold
                            logger.info(f"Detected incomplete lap or DNF at position {position}. "
                                      f"Current time: {finish_time}, Previous time seconds: {previous_time_seconds}. "
                                      f"Stopping result extraction.")
                            break
                        previous_time_seconds = current_time_seconds

                    # Determine gender from age group (M40 -> M, W35 -> W)
                    gender = None
                    if age_group:
                        if age_group.startswith('M'):
                            gender = 'M'
                        elif age_group.startswith('W') or age_group.startswith('F'):
                            gender = 'W'

                    # Skip invalid entries
                    if not runner_name or not position:
                        continue

                    # Add runner to database
                    runner = self.db.add_runner(
                        name=runner_name,
                        club=club,
                        birth_year=birth_year
                    )

                    # Add race result to database
                    self.db.add_race_result(
                        race_id=race_db_id,
                        runner_id=runner.id,
                        finish_time=finish_time,
                        position=position,
                        age_group=age_group,
                        age_group_position=age_group_position,
                        gender=gender,
                        bib_number=bib_number
                    )

                    results_data.append({
                        'runner_name': runner_name,
                        'club': club,
                        'birth_year': birth_year,
                        'position': position,
                        'finish_time': finish_time,
                        'age_group': age_group,
                        'gender': gender,
                        'bib_number': bib_number
                    })

                except Exception as e:
                    logger.error(f"Error parsing result row: {e}")
                    continue

            logger.info(f"Extracted {len(results_data)} race results")
            return results_data

        except requests.RequestException as e:
            logger.error(f"Error fetching race results from {result_url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing race results from {result_url}: {e}")
            return []

    def scrape_events_with_races(self, year, max_events=3):
        """
        Scrape events and their races for a given year (limited for testing).

        Args:
            year: Year to scrape
            max_events: Maximum number of events to process (for testing)

        Returns:
            Dictionary with events and races data
        """
        logger.info(f"Scraping events with races for year {year} (max {max_events} events)")

        # Get all events for the year
        events = self.get_event_links(year)

        if not events:
            logger.warning(f"No events found for year {year}")
            return {'events': [], 'races': []}

        # Limit to max_events for testing
        events_to_process = events[:max_events]
        logger.info(f"Processing {len(events_to_process)} out of {len(events)} events")

        all_races_data = []

        for i, event in enumerate(events_to_process, 1):
            logger.info(f"Processing event {i}/{len(events_to_process)}: {event['name']} on {event.get('date', 'Unknown date')}")

            races_data = self.scrape_event_races(
                event_url=event['url'],
                event_db_id=event['db_id'],
                test_mode=True  # Just testing URLs for now
            )

            all_races_data.extend(races_data)

            # Be respectful to the server between events
            if i < len(events_to_process):
                time.sleep(self.delay * 2)  # Longer delay between events

        return {
            'events': events_to_process,
            'races': all_races_data
        }

    def scrape_full_results(self, year, max_events=1, start_from_event=1):
        """
        Scrape events, races, and full race results for a given year.

        Args:
            year: Year to scrape
            max_events: Maximum number of events to process
            start_from_event: Event number to start from (1-based index)

        Returns:
            Dictionary with events, races, and total results count
        """
        logger.info(f"Scraping FULL results for year {year} (max {max_events} events, starting from event {start_from_event})")

        # Get all events for the year
        events = self.get_event_links(year)

        if not events:
            logger.warning(f"No events found for year {year}")
            return {'events': [], 'races': [], 'total_results': 0}

        # Calculate start and end indices (convert 1-based to 0-based)
        start_index = max(0, start_from_event - 1)
        end_index = min(len(events), start_index + max_events)

        events_to_process = events[start_index:end_index]
        logger.info(f"Processing events {start_from_event} to {start_index + len(events_to_process)} ({len(events_to_process)} events) out of {len(events)} total events")

        all_races_data = []
        total_results = 0

        for i, event in enumerate(events_to_process, start_from_event):
            logger.info(f"Processing event {i}/{start_index + len(events_to_process)}: {event['name']} on {event.get('date', 'Unknown date')}")

            # Check if event has been fully processed (has race results)
            if self.db.event_fully_processed(event['url']):
                logger.info(f"Event already fully processed, skipping: {event['name']}")
                continue

            races_data = self.scrape_event_races(
                event_url=event['url'],
                event_db_id=event['db_id'],
                test_mode=False  # Extract full results
            )

            # Count total results
            for race in races_data:
                if 'results_count' in race:
                    total_results += race['results_count']

            all_races_data.extend(races_data)

            # Be respectful to the server between events
            if i < start_index + len(events_to_process):
                time.sleep(self.delay * 3)  # Longer delay for full scraping

        return {
            'events': events_to_process,
            'races': all_races_data,
            'total_results': total_results
        }

def main():
    """Example usage of the scraper"""
    scraper = RuntixScraper(delay=1.0)

    # Test the full race results extraction pipeline
    year = 2026
    print(f"Testing FULL race results extraction for {year} (starting from event 1, max 1000 events)...")

    result = scraper.scrape_full_results(year, max_events=1000, start_from_event=1)

    print(f"\nProcessed {len(result['events'])} events:")
    for event in result['events']:
        date_info = f" on {event['date']}" if event.get('date') else ""
        print(f"- {event['name']}{date_info}")

    print(f"\nFound {len(result['races'])} races with results:")
    for race in result['races']:
        results_count = race.get('results_count', 0)
        print(f"- {race['race_name']} ({race['distance_km']}km): {results_count} runners")

    print(f"\nTotal race results extracted: {result['total_results']}")

    # Show database summary
    print(f"\nDatabase contains:")
    events = scraper.db.get_events()
    races = scraper.db.get_races()
    runners = scraper.db.get_runners()
    print(f"- {len(events)} events")
    print(f"- {len(races)} races")
    print(f"- {len(runners)} unique runners")

    # Show sample runners with club history
    if runners:
        print(f"\nSample runners with club history:")
        for runner in runners[:5]:
            clubs = runner.get_clubs()
            if len(clubs) > 1:
                clubs_str = " → ".join(clubs)
                print(f"- {runner.name} ({runner.birth_year}) - Club history: {clubs_str}")
            else:
                current_club = clubs[0] if clubs else "No club"
                print(f"- {runner.name} ({runner.birth_year}) - Club: {current_club}")

    scraper.db.close()

if __name__ == "__main__":
    main()