import os
import re
import json
import logging
import datetime
import hashlib
import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_dutch_datetime(date_str):
    """
    Parses a date string like "di 7-7-2026 om 19:15" or "ma 7-7-2025".
    Returns a tuple: (datetime_or_date, is_all_day)
    """
    if not date_str:
        return None, True
        
    date_str = date_str.strip()
    
    # Remove day of week prefix (e.g. "di ")
    date_str = re.sub(r'^(ma|di|wo|do|vr|za|zo)\s+', '', date_str, flags=re.IGNORECASE)
    
    tz = pytz.timezone('Europe/Amsterdam')
    
    if ' om ' in date_str:
        # Has time
        parts = date_str.split(' om ')
        date_part = parts[0].strip()
        time_part = parts[1].strip()
        
        d_parts = date_part.split('-')
        t_parts = time_part.split(':')
        
        if len(d_parts) == 3 and len(t_parts) == 2:
            day, month, year = int(d_parts[0]), int(d_parts[1]), int(d_parts[2])
            hour, minute = int(t_parts[0]), int(t_parts[1])
            dt = datetime.datetime(year, month, day, hour, minute)
            return tz.localize(dt), False
    else:
        # Just date
        d_parts = date_str.split('-')
        if len(d_parts) == 3:
            day, month, year = int(d_parts[0]), int(d_parts[1]), int(d_parts[2])
            return datetime.date(year, month, day), True
            
    return None, True

def find_tournament_name(match_node):
    p = match_node.parent
    while p:
        title_el = p.find(class_='media__title')
        if title_el:
            return title_el.text.strip()
        p = p.parent
    return "Tennis Toernooi"

def scrape_homepage(session, username, password, domain="mijnknltb.toernooi.nl"):
    login_url = f"https://{domain}/user/login"
    logging.info(f"Logging in as {username} via {domain}...")
    
    # Step 1: Get login page (and bypass cookiewall)
    r = session.get(login_url)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    form = soup.find('form', action=lambda x: x and '/cookiewall/Save' in x)
    if form:
        data = {inp.get('name'): inp.get('value', '') for inp in form.find_all('input') if inp.get('name')}
        session.post(f"https://{domain}/cookiewall/Save", data=data)
        r = session.get(login_url)
        soup = BeautifulSoup(r.text, 'html.parser')

    # Step 2: Submit login credentials
    login_form = soup.find('form', action=lambda x: x and ('login' in x.lower() or 'user' in x.lower()))
    if not login_form:
        logging.error("Could not find login form.")
        return []

    login_data = {inp.get('name'): inp.get('value', '') for inp in login_form.find_all('input') if inp.get('name')}
    login_data['Login'] = username
    login_data['Password'] = password
    login_data['ReturnUrl'] = '/'

    action = login_form.get('action', '/user')
    action_url = f"https://{domain}{action}" if action.startswith('/') else action
    r_home = session.post(action_url, data=login_data)
    
    if "login" in r_home.url.lower():
        logging.error(f"Login failed for user {username}.")
        return []
        
    logging.info("Login successful. Parsing homepage matches...")
    soup_home = BeautifulSoup(r_home.text, 'html.parser')
    
    # Find all match blocks
    matches = soup_home.find_all('div', class_='match')
    parsed_matches = []
    
    for match in matches:
        t_name = find_tournament_name(match)
        
        players_team1 = []
        players_team2 = []
        rows = match.find_all('div', class_='match__row')
        if len(rows) >= 2:
            for p_link in rows[0].find_all('a', class_='nav-link'):
                players_team1.append(p_link.text.strip())
            for p_link in rows[1].find_all('a', class_='nav-link'):
                players_team2.append(p_link.text.strip())
            if not players_team1:
                players_team1 = [rows[0].text.strip()]
            if not players_team2:
                players_team2 = [rows[1].text.strip()]
                
        match_date_str = ""
        location = ""
        footer_items = match.find_all('li', class_='match__footer-list-item')
        for item in footer_items:
            val = item.find('span', class_='nav-link__value')
            val_text = val.text.strip() if val else ""
            use_tag = item.find('use')
            if use_tag:
                href = use_tag.get('xlink:href', '')
                if 'icon-marker' in href:
                    location = val_text
            else:
                if 'om' in val_text or any(day in val_text for day in ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo']):
                    match_date_str = val_text
                elif val_text:
                    location = val_text
                    
        parsed_matches.append({
            "tournament": t_name,
            "team1": players_team1,
            "team2": players_team2,
            "date_str": match_date_str,
            "location": location
        })
        
    return parsed_matches

def generate_ical(matches, owner_name):
    cal = Calendar()
    cal.add('prodid', '-//Tennis Calendar Scraper//NL')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', f"Tennis Matches - {owner_name}")
    cal.add('x-wr-timezone', 'Europe/Amsterdam')
    
    for match in matches:
        team1_str = " / ".join(match["team1"])
        team2_str = " / ".join(match["team2"])
        
        event = Event()
        
        # Determine summary
        summary = f"Tennis: {team1_str} vs {team2_str}"
        event.add('summary', summary)
        
        # Description
        description = f"Toernooi: {match['tournament']}\nLocatie: {match['location']}"
        event.add('description', description)
        event.add('location', match['location'])
        
        # Parse start datetime or date
        dt_val, is_all_day = parse_dutch_datetime(match["date_str"])
        if dt_val:
            if is_all_day:
                event.add('dtstart', dt_val)
                # For all-day events, dtend should be next day
                event.add('dtend', dt_val + datetime.timedelta(days=1))
            else:
                event.add('dtstart', dt_val)
                # Tennis matches usually take around 1.5 hours
                event.add('dtend', dt_val + datetime.timedelta(hours=1.5))
        else:
            # Fallback to an all-day event if no date is provided
            continue
            
        # Create a stable, unique UID
        uid_raw = f"{summary}_{match['date_str']}_{match['location']}".encode('utf-8')
        uid = hashlib.md5(uid_raw).hexdigest() + "@tennis-calendar-scraper"
        event.add('uid', uid)
        event.add('dtstamp', datetime.datetime.now(pytz.utc))
        
        cal.add_component(event)
        
    return cal.to_ical()

def run_scraper(config_path, output_dir):
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    os.makedirs(output_dir, exist_ok=True)
    
    # Store matches grouped by owner name
    player_matches = {}
    
    for acc in config.get("accounts", []):
        name = acc.get("name")
        if not name:
            continue
        username = acc.get("username")
        password = acc.get("password")
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7',
        })
        
        domain_choice = acc.get("domain", "beide")
        if domain_choice == "beide":
            domains_to_scrape = ["mijnknltb.toernooi.nl", "www.toernooi.nl"]
        elif domain_choice == "toernooi.nl":
            domains_to_scrape = ["www.toernooi.nl"]
        else:
            domains_to_scrape = [domain_choice]
            
        for domain in domains_to_scrape:
            try:
                matches = scrape_homepage(session, username, password, domain)
                logging.info(f"Found {len(matches)} matches for {name} on {domain}.")
                
                if matches:
                    # Filter out Bye matches
                    valid_matches = [m for m in matches if not any("bye" in p.lower() for p in m["team1"] + m["team2"])]
                    
                    key = name.strip()
                    player_matches.setdefault(key, []).extend(valid_matches)
            except Exception as e:
                logging.error(f"Error scraping for {name} on {domain}: {str(e)}", exc_info=True)
            
    # Now, process and write files for each unique player name
    all_matches = []
    
    for name, matches in player_matches.items():
        # Deduplicate matches for this specific player
        unique_player_matches = []
        seen = set()
        for m in matches:
            t1 = tuple(sorted(m['team1']))
            t2 = tuple(sorted(m['team2']))
            teams_key = tuple(sorted([t1, t2]))
            repr_str = f"{teams_key}_{m['date_str']}"
            if repr_str not in seen:
                seen.add(repr_str)
                unique_player_matches.append(m)
                
        ical_data = generate_ical(unique_player_matches, name)
        ical_path = os.path.join(output_dir, f"{name.lower()}.ics")
        with open(ical_path, 'wb') as f_out:
            f_out.write(ical_data)
        logging.info(f"Saved {name.lower()}.ics with {len(unique_player_matches)} matches.")
        
        all_matches.extend(unique_player_matches)
        
    if all_matches:
        # Generate combined calendar
        unique_matches = []
        seen_matches = set()
        for m in all_matches:
            t1 = tuple(sorted(m['team1']))
            t2 = tuple(sorted(m['team2']))
            teams_key = tuple(sorted([t1, t2]))
            repr_str = f"{teams_key}_{m['date_str']}"
            if repr_str not in seen_matches:
                seen_matches.add(repr_str)
                unique_matches.append(m)
                
        combined_ical = generate_ical(unique_matches, "Combined")
        combined_path = os.path.join(output_dir, "tennis.ics")
        with open(combined_path, 'wb') as f_out:
            f_out.write(combined_ical)
        logging.info(f"Saved combined tennis.ics with {len(unique_matches)} matches.")

if __name__ == '__main__':
    # Test script locally
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(script_dir, 'config.json')
    run_scraper(config_file, script_dir)
