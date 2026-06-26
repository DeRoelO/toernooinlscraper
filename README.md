# MijnKNLTB / Toernooi.nl Agenda Scraper

Dit project scrapet automatisch de tenniswedstrijden van geconfigureerde MijnKNLTB- (en Toernooi.nl) accounts en stelt deze beschikbaar als iCal-agenda's (.ics). De scraper draait in een lichte Docker-container en heeft een ingebouwde configuratie-GUI.

## Functionaliteiten

- **Volledige match-details**: Scrapet wedstrijden rechtstreeks van het spelersdashboard (inclusief exacte datum, starttijd, tegenstanders en speellocatie).
- **Deduplicatie**: Voorkomt dubbele vermeldingen in de gecombineerde agenda als beide spelers in dezelfde (gemengd) dubbelpartij spelen.
- **Web-GUI**: Beheer accounts en instellingen eenvoudig via een browser.
- **Automatische updates**: Draait periodiek op de achtergrond om wijzigingen in de planning op te halen.
- **iCal feeds**: Genereert individuele agenda's per speler en een gecombineerde agenda.

## Installatie & Gebruik

### Docker Compose (Aanbevolen)

1. Maak een `docker-compose.yml` aan:
   ```yaml
   version: '3.8'
   services:
     tennis-calendar:
       image: ghcr.io/deroelo/toernooinlscraper:latest
       container_name: tennis-calendar-scraper
       restart: unless-stopped
       ports:
         - "8080:8080"
       volumes:
         - ./config.json:/app/config.json
   ```

2. Start de container:
   ```bash
   docker compose up -d
   ```

3. Open de configuratiepagina via `http://<SERVER_IP>:8080` in je browser en voeg je accounts toe.

### Handmatige installatie (lokaal testen)

1. Installeer de vereiste Python-bibliotheken:
   ```bash
   pip install requests beautifulsoup4 icalendar pytz
   ```

2. Start de applicatie:
   ```bash
   python server.py
   ```

3. Bezoek `http://localhost:8080` om de configuratie te beheren.

## Configuratie (config.json)

De configuratie wordt opgeslagen in `config.json` in de hoofdmap. Dit bestand wordt automatisch aangemaakt en bijgewerkt via de GUI, maar kan ook handmatig worden bewerkt:

```json
{
  "accounts": [
    {
      "name": "Speler1",
      "username": "GEBRUIKERSNAAM",
      "password": "WACHTWOORD",
      "domain": "mijnknltb.toernooi.nl"
    }
  ],
  "update_interval_hours": 6,
  "port": 8080
}
```

## Agenda's toevoegen aan Google Agenda / Outlook

Abonneren op de feeds kan via de volgende URL's:

- **Gecombineerde agenda**: `http://<SERVER_IP>:<PORT>/tennis.ics`
- **Speler 1**: `http://<SERVER_IP>:<PORT>/speler1.ics`

Plak deze URL in je agenda-applicatie bij "Abonneren via URL" of "Agenda toevoegen via web". De agenda-applicatie haalt periodiek de nieuwste gegevens op.
