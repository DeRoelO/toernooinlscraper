FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir requests beautifulsoup4 icalendar pytz

# Copy app files
COPY scraper.py server.py /app/

# Expose calendar port
EXPOSE 8080

# Run the server
CMD ["python", "-u", "server.py"]
