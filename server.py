import os
import time
import datetime
import json
import logging
import threading
import http.server
import socketserver
import urllib.parse
from scraper import run_scraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# Global variables for scheduler control
reload_event = threading.Event()
scrape_now_event = threading.Event()
current_status = "Standby"
last_update_time = "Nog niet uitgevoerd"

def get_config():
    config_file = os.path.join(DIRECTORY, 'config.json')
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Could not read config.json: {str(e)}")
    return {"accounts": [], "update_interval_hours": 6, "port": PORT}

def save_config(config_data):
    config_file = os.path.join(DIRECTORY, 'config.json')
    try:
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        logging.info("Saved updated configuration to config.json.")
        return True
    except Exception as e:
        logging.error(f"Could not write config.json: {str(e)}")
        return False

def render_config_page():
    config = get_config()
    accounts = config.get("accounts", [])
    interval = config.get("update_interval_hours", 6)
    port = config.get("port", PORT)
    
    # List generated ics files
    ics_files = []
    for acc in accounts:
        name = acc.get("name", "").lower()
        if name:
            ics_files.append(f"{name}.ics")
    if accounts:
        ics_files.append("tennis.ics")
        
    ics_links_html = ""
    if ics_files:
        for f in ics_files:
            display_name = "Gecombineerd (Allen)" if f == "tennis.ics" else f.split(".")[0].capitalize()
            ics_links_html += f"""
            <div class="calendar-card">
                <div class="calendar-card__info">
                    <span class="calendar-card__name">{display_name}</span>
                    <span class="calendar-card__file">{f}</span>
                </div>
                <div class="calendar-card__actions">
                    <button class="btn btn--secondary" onclick="copyLink('{f}')">Kopieer Link</button>
                    <a href="/{f}" class="btn btn--primary" download>Download</a>
                </div>
            </div>
            """
    else:
        ics_links_html = "<p class='text-muted'>Nog geen agenda's gegenereerd. Voeg eerst een account toe.</p>"

    accounts_rows_html = ""
    for idx, acc in enumerate(accounts):
        accounts_rows_html += f"""
        <tr>
            <td><strong>{acc.get('name')}</strong></td>
            <td><code>{acc.get('username')}</code></td>
            <td>{acc.get('domain')}</td>
            <td><span class="mask-password">••••••••</span></td>
            <td style="text-align: right;">
                <form action="/config/delete_account" method="post" style="display:inline;">
                    <input type="hidden" name="index" value="{idx}">
                    <button type="submit" class="btn btn--danger btn--small">Verwijder</button>
                </form>
            </td>
        </tr>
        """
        
    if not accounts:
        accounts_rows_html = "<tr><td colspan='5' class='text-center text-muted'>Geen accounts geconfigureerd. Voeg hieronder een account toe.</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MijnKNLTB Scraper Configurator</title>
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 28, 45, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-color: #f3f4f6;
            --text-muted: #9ca3af;
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --secondary: rgba(255, 255, 255, 0.08);
            --secondary-hover: rgba(255, 255, 255, 0.15);
            --danger: #ef4444;
            --danger-hover: #dc2626;
            --success: #10b981;
        }}
        
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}
        
        body {{
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(37, 99, 235, 0.1) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.05) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-color);
            padding: 2rem 1rem;
            min-height: 100vh;
            line-height: 1.5;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        
        header {{
            margin-bottom: 2rem;
            text-align: center;
        }}
        
        h1 {{
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(to right, #60a5fa, #34d399);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}
        
        .status-bar {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            backdrop-filter: blur(10px);
        }}
        
        .status-item {{
            font-size: 0.9rem;
        }}
        
        .status-label {{
            color: var(--text-muted);
            margin-right: 0.5rem;
        }}
        
        .status-value {{
            font-weight: 600;
        }}
        
        .status-value--active {{
            color: var(--success);
        }}
        
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 2rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
        }}
        
        h2 {{
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 0.75rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .calendar-list {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 1rem;
        }}
        
        @media(min-width: 600px) {{
            .calendar-list {{
                grid-template-columns: 1fr 1fr;
            }}
        }}
        
        .calendar-card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 1rem;
        }}
        
        .calendar-card__name {{
            display: block;
            font-weight: 600;
            font-size: 1.05rem;
            color: #f3f4f6;
        }}
        
        .calendar-card__file {{
            display: block;
            font-size: 0.8rem;
            color: var(--text-muted);
            font-family: monospace;
            margin-top: 0.25rem;
        }}
        
        .calendar-card__actions {{
            display: flex;
            gap: 0.5rem;
        }}
        
        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s ease;
            border: none;
            text-decoration: none;
            text-align: center;
        }}
        
        .btn--primary {{
            background-color: var(--primary);
            color: white;
        }}
        
        .btn--primary:hover {{
            background-color: var(--primary-hover);
        }}
        
        .btn--secondary {{
            background-color: var(--secondary);
            color: var(--text-color);
            border: 1px solid var(--border-color);
        }}
        
        .btn--secondary:hover {{
            background-color: var(--secondary-hover);
        }}
        
        .btn--danger {{
            background-color: var(--danger);
            color: white;
        }}
        
        .btn--danger:hover {{
            background-color: var(--danger-hover);
        }}
        
        .btn--small {{
            padding: 0.4rem 0.8rem;
            font-size: 0.8rem;
            border-radius: 6px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 1.5rem;
        }}
        
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        
        th {{
            color: var(--text-muted);
            font-weight: 500;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        td {{
            font-size: 0.95rem;
        }}
        
        .mask-password {{
            font-family: monospace;
            color: var(--text-muted);
        }}
        
        .form-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 1.5rem;
        }}
        
        @media(min-width: 600px) {{
            .form-grid {{
                grid-template-columns: 1fr 1fr;
            }}
        }}
        
        .form-group {{
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}
        
        .form-group--full {{
            grid-column: 1 / -1;
        }}
        
        label {{
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-muted);
        }}
        
        input[type="text"], input[type="password"], input[type="number"], select {{
            background-color: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-size: 0.95rem;
            width: 100%;
            transition: border-color 0.2s;
        }}
        
        input:focus, select:focus {{
            outline: none;
            border-color: var(--primary);
        }}
        
        .text-center {{ text-align: center; }}
        .text-muted {{ color: var(--text-muted); }}
        
        .notification {{
            background-color: var(--success);
            color: white;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            margin-bottom: 1.5rem;
            display: none;
            font-weight: 600;
            font-size: 0.9rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Tennis Kalender Scraper</h1>
            <p class="text-muted">Beheer je MijnKNLTB agenda synchronisatie en download je feeds.</p>
        </header>
        
        <div id="notification" class="notification">Link gekopieerd naar klembord!</div>
        
        <div class="status-bar">
            <div class="status-item">
                <span class="status-label">Status:</span>
                <span class="status-value status-value--active">{current_status}</span>
            </div>
            <div class="status-item">
                <span class="status-label">Laatste update:</span>
                <span class="status-value">{last_update_time}</span>
            </div>
            <form action="/config/scrape" method="post" style="margin: 0;">
                <button type="submit" class="btn btn--primary btn--small">Scrapen Nu Starten</button>
            </form>
        </div>
        
        <!-- Generated Calendars -->
        <div class="card">
            <h2>Beschikbare Agenda's (.ics feeds)</h2>
            <div class="calendar-list">
                {ics_links_html}
            </div>
        </div>
        
        <!-- Configured Accounts -->
        <div class="card">
            <h2>Gekoppelde Accounts</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Naam</th>
                            <th>Gebruikersnaam</th>
                            <th>Domein</th>
                            <th>Wachtwoord</th>
                            <th style="text-align: right;">Actie</th>
                        </tr>
                    </thead>
                    <tbody>
                        {accounts_rows_html}
                    </tbody>
                </table>
            </div>
            
            <h2 style="margin-top: 2rem; border-top: none; padding-bottom: 0;">Nieuw Account Toevoegen</h2>
            <form action="/config/add_account" method="post">
                <div class="form-grid">
                    <div class="form-group">
                        <label for="name">Naam (bijv. Roel of Ella)</label>
                        <input type="text" id="name" name="name" required placeholder="Naam">
                    </div>
                    <div class="form-group">
                        <label for="domain">Toernooi.nl Domein</label>
                        <select id="domain" name="domain" required>
                            <option value="mijnknltb.toernooi.nl" selected>mijnknltb.toernooi.nl (KNLTB Tennis/Padel)</option>
                            <option value="www.toernooi.nl">www.toernooi.nl (Standaard)</option>
                            <option value="knltb.toernooi.nl">knltb.toernooi.nl</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="username">Gebruikersnaam / Bondsnummer</label>
                        <input type="text" id="username" name="username" required placeholder="Bondsnummer of e-mail">
                    </div>
                    <div class="form-group">
                        <label for="password">Wachtwoord</label>
                        <input type="password" id="password" name="password" required placeholder="••••••••">
                    </div>
                    <div class="form-group form-group--full">
                        <button type="submit" class="btn btn--primary" style="margin-top: 0.5rem;">Account Toevoegen</button>
                    </div>
                </div>
            </form>
        </div>
        
        <!-- General Settings -->
        <div class="card">
            <h2>Algemene Instellingen</h2>
            <form action="/config/save_settings" method="post">
                <div class="form-grid">
                    <div class="form-group">
                        <label for="update_interval_hours">Update Interval (uren)</label>
                        <input type="number" id="update_interval_hours" name="update_interval_hours" value="{interval}" min="1" max="24" required>
                    </div>
                    <div class="form-group">
                        <label for="port">Poort</label>
                        <input type="number" id="port" name="port" value="{port}" min="80" max="65535" required>
                    </div>
                    <div class="form-group form-group--full">
                        <button type="submit" class="btn btn--secondary">Instellingen Opslaan</button>
                    </div>
                </div>
            </form>
        </div>
    </div>

    <script>
        function copyLink(filename) {{
            const link = window.location.protocol + "//" + window.location.host + "/" + filename;
            navigator.clipboard.writeText(link).then(function() {{
                const notif = document.getElementById('notification');
                notif.style.display = 'block';
                setTimeout(function() {{
                    notif.style.display = 'none';
                }}, 3000);
            }});
        }}
    </script>
</body>
</html>
"""
    return html

class CalendarHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Prevent favicon errors logging
        if self.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
            
        path = self.path.split('?')[0]
        if path == '/' or path == '/config':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            html = render_config_page()
            self.wfile.write(html.encode('utf-8'))
        else:
            # Serve static files (.ics files)
            # Make sure files are read from current directory
            file_path = os.path.join(DIRECTORY, path.lstrip('/'))
            if os.path.exists(file_path) and path.endswith('.ics'):
                self.send_response(200)
                self.send_header('Content-Type', 'text/calendar; charset=utf-8')
                # Disable caching
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"404 Not Found")

    def do_POST(self):
        path = self.path.split('?')[0]
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = urllib.parse.parse_qs(post_data)
        
        # Clean parameter values (parse_qs wraps them in list)
        data = {{k: v[0] for k, v in params.items()}}
        
        config = get_config()
        
        if path == '/config/add_account':
            new_acc = {{
                "name": data.get("name"),
                "username": data.get("username"),
                "password": data.get("password"),
                "domain": data.get("domain", "mijnknltb.toernooi.nl")
            }}
            config.setdefault("accounts", []).append(new_acc)
            save_config(config)
            reload_event.set() # Trigger immediate reload & scrape
            
        elif path == '/config/delete_account':
            idx = int(data.get("index", -1))
            if idx >= 0 and idx < len(config.get("accounts", [])):
                config["accounts"].pop(idx)
                save_config(config)
                reload_event.set() # Trigger reload
                
        elif path == '/config/save_settings':
            config["update_interval_hours"] = int(data.get("update_interval_hours", 6))
            config["port"] = int(data.get("port", PORT))
            save_config(config)
            reload_event.set() # Trigger reload
            
        elif path == '/config/scrape':
            scrape_now_event.set() # Trigger immediate scrape
            
        # Redirect back to home config page
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

def run_http_server(port):
    # Try different ports if default is blocked, or retry on startup
    socketserver.TCPServer.allow_reuse_address = True
    while True:
        try:
            with socketserver.TCPServer(("", port), CalendarHTTPRequestHandler) as httpd:
                logging.info(f"Serving calendar feeds and GUI on http://localhost:{port}...")
                httpd.serve_forever()
        except Exception as e:
            logging.error(f"Error starting server on port {port}: {str(e)}")
            time.sleep(10)

def scheduler_loop():
    global current_status, last_update_time
    
    while True:
        config = get_config()
        config_file = os.path.join(DIRECTORY, 'config.json')
        interval_hours = config.get("update_interval_hours", 6)
        
        # Scrape
        current_status = "Scraping..."
        logging.info("Starting scrape...")
        try:
            run_scraper(config_file, DIRECTORY)
            last_update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            current_status = "Standby"
        except Exception as e:
            logging.error(f"Error in scheduler scraper: {str(e)}", exc_info=True)
            current_status = f"Fout: {str(e)}"
            
        # Sleep loop that can be interrupted by events
        sleep_time = interval_hours * 3600
        steps = int(sleep_time / 10)  # Check every 10 seconds
        for _ in range(max(1, steps)):
            # Check if interrupted
            if reload_event.is_set():
                logging.info("Config reload requested. Restarting scraping loop...")
                reload_event.clear()
                break
            if scrape_now_event.is_set():
                logging.info("Manual scrape requested. Triggering scrape...")
                scrape_now_event.clear()
                break
            time.sleep(10)
        else:
            # Completed the normal sleep time without interruption
            pass

if __name__ == '__main__':
    # Start scheduler thread
    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    
    # Read config for port
    config = get_config()
    port = config.get("port", PORT)
    
    # Run HTTP server (blocks main thread)
    run_http_server(port)
