# TMKOC Tube

A YouTube-style browser for the official *Taarak Mehta Ka Ooltah Chashmah* channel: single episodes and full movies only,
with episode order, character and theme filters, a "Best of" mode and a mixable ranking. Videos play from YouTube's own embedded player.

## How it updates
`.github/workflows/update.yml` runs `pipeline/update.py`:
- every 5 minutes from 20:55 to 22:30 IST, Monday to Saturday (new episodes go live at 21:00 IST)
- every hour otherwise
- Sundays: a full refresh of views and likes

New uploads are labelled by keyword rules in `pipeline/lib.py`, the data in `data/videos.json` is updated, and the site is rebuilt and published to GitHub Pages.

## Setup (one time)
1. Repo settings -> Secrets and variables -> Actions -> new secret `YT_API_KEY` (a YouTube Data API v3 key).
2. Repo settings -> Pages -> Source: **GitHub Actions**.
3. Actions tab -> "Update site" -> Run workflow (mode `full`).

## Change the look or the ranking
Edit `web/template.html` (page, filters, ranking modes) or `pipeline/lib.py` (labels, scores), then commit. The next run rebuilds the site.

## Local run
`YT_KEY=... python pipeline/update.py quick` writes `public/index.html`.
