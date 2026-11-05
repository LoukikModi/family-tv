# Family TV

A simple, large-print TV page for each family member, built from the official YouTube channels.

- `/dad/` – Maharashtrachi HasyaJatra, new CID, old CID
- more people can be added in `PROFILES` in `pipeline/build.py`

`pipeline/build.py` reads the YouTube Data API (secret `YT_API_KEY`), keeps `data/library.json`, and writes the static site into `public/`. GitHub Actions rebuilds and deploys it to GitHub Pages.
