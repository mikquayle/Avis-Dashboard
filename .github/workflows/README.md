# Avis Rating Dashboard

A lightweight dashboard that tracks your Avis location's Google rating over time — scraped every 30 minutes via GitHub Actions and displayed as a live chart.

## Project structure

```
avis-dashboard/
├── index.html                    ← the dashboard (open in browser or host on GitHub Pages)
├── scraper.py                    ← pulls Google rating and writes to data/ratings.json
├── data/
│   └── ratings.json              ← auto-updated by the scraper
└── .github/
    └── workflows/
        └── scrape.yml            ← runs automatically every 30 min
```

## Setup

### 1. Set your Google Maps URL

Open `scraper.py` and paste your specific Avis location's Google Maps URL into the `GOOGLE_MAPS_URL` fallback value (line ~21):

```python
GOOGLE_MAPS_URL = os.environ.get(
    "GOOGLE_MAPS_URL",
    "https://www.google.com/maps/place/YOUR+LOCATION+HERE"   # ← edit this
)
```

Or, for flexibility, add a **repository secret** named `GOOGLE_MAPS_URL` in:
> GitHub repo → Settings → Secrets and variables → Actions → New repository secret

### 2. Enable GitHub Actions

The workflow in `.github/workflows/scrape.yml` will run automatically once pushed.
To trigger it manually: **Actions → Scrape Google Rating → Run workflow**

### 3. Enable GitHub Pages (optional — to view dashboard online)

> GitHub repo → Settings → Pages → Source: Deploy from branch → Branch: `main` → Folder: `/ (root)`

Your dashboard will be live at: `https://<your-username>.github.io/Avis-Dashboard/`

## Local development

```bash
# Install dependencies
pip install requests beautifulsoup4

# Run the scraper manually
python scraper.py

# View the dashboard — open index.html in a browser
# (use a local server if fetch() throws CORS errors)
python -m http.server 8080
# then visit http://localhost:8080
```

## Notes

- The scraper uses lightweight HTML parsing. If Google changes their page structure, the selectors in `scraper.py` may need updating.
- Ratings history is capped at 500 data points in `ratings.json` to keep the file small.
- The dashboard auto-refreshes every 5 minutes when left open in a browser tab.
