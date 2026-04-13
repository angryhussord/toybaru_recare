# Toybaru ReCare

A self-hosted dashboard for the Subaru Solterra (and Toyota bZ4X) that gives you full access to your own driving data -- the data that Subaru collects but never shows you.

## Why this exists

I built this because Subaru silently deleted all my trip data from 2024. One day it was there, the next it was gone. No warning, no export option, no backup. Almost a year of driving history, just wiped from their servers.

That pissed me off enough to start poking around the SubaruConnect API. What I found was surprising: the API collects far more data than the app ever shows you. For every single trip, Subaru tracks:

- **Overspeed logging** -- every point on your route where you exceeded the speed limit is flagged with `overspeed: true`. Subaru knows exactly where and when you were speeding. This is never shown in the app.
- **Driving behaviour events** -- every hard brake, every aggressive acceleration is logged with GPS coordinates, timestamps, severity scores, and even road gradient. The app shows you a vague "driving score" but never the raw events.
- **Driving mode per route point** -- every few meters, the car records whether you were in Eco, Power, or Regeneration mode. The full route is reconstructed with mode-colored segments.

None of this is visible in the Subaru Care app. Your car is basically a telemetry device on wheels, and you have no access to your own data.

So I built a dashboard around it. Import your trips, store them locally (so Subaru can't delete them again), browse your routes on a map, see where you braked hard, check your efficiency stats, and export everything as CSV or JSON.

## Screenshots

<details>
<summary>Click to expand screenshots</summary>

<img src="screenshots/vehicle.jpg" alt="Vehicle overview" width="700">

<img src="screenshots/trips.jpg" alt="Trip browser" width="700">

<img src="screenshots/trip-detail.jpg" alt="Trip detail" width="500">

<img src="screenshots/route-map.jpg" alt="Route map with driving modes" width="700">

<img src="screenshots/statistics.jpg" alt="Statistics dashboard" width="700">

<img src="screenshots/data-import.jpg" alt="Data import and export" width="700">

</details>

## Features

**Vehicle Overview**
- Battery state of charge, range (with and without climate), charging status
- Door/window/hatch lock status with open/closed indicators
- Last known GPS position on a map
- Remote lock/unlock controls
- Last trip summary with key metrics

**Trip Browser**
- All trips in a sortable, filterable table
- Date range selection
- Score badges (color-coded: green >80, yellow >60, red <60)
- Eco/Regeneration/Power distribution per trip as stacked bar
- Hard braking and acceleration event counts
- Click any trip for the detail view

**Trip Detail View**
- Interactive zoomable map with the driven route
- Route colored by driving mode (green=Eco, blue=Regeneration, red=Power)
- Start and end markers
- Braking and acceleration events as colored dots on the map
- Hover tooltips showing mode, overspeed status, and coordinates
- Score breakdown (overall, acceleration, braking, consistency)
- Driving behaviour event table with timestamps and ratings
- Raw JSON view ("Stats for Nerds")

**Statistics**
- Time range filter (any date range or all-time)
- Total trips, kilometers, hours driven, km per day
- Average and max speed, average scores (overall, acceleration, braking)
- Eco/Regeneration/Power efficiency breakdown with stacked bar
- Monthly km bar chart with score trend
- Trips by weekday and time of day (24h histogram)
- Speed category breakdown (city <40, rural 40-80, highway >80 km/h)
- Score distribution histogram
- Idle time, overspeed km, night trip percentage
- Records: longest trip, top speed, best score, best regeneration, most km in a day

**Data Management**
- Import all historical trips from the Subaru API with live progress log
- Incremental sync (fetch only new trips since last import)
- Export trips as CSV (structured columns) or JSON (including route and behaviour data)
- Re-import from a previously exported JSON file (UPSERT, no duplicates)
- Local SQLite database -- your data stays on your machine

**Multi-language**
- Ships with German (de) and English (en)
- Add more languages by dropping a JSON file into the locales directory
- Language switcher dropdown, preference saved in browser

**Multi-vehicle**
- Vehicle switcher in the top bar
- All data stored per VIN
- Works if your account has multiple vehicles linked

## Installation

### Docker (recommended)

```bash
git clone https://github.com/youruser/toybaru.git
cd toybaru
docker compose up -d
```

Open http://localhost:8099, sign in with your Subaru account credentials.

Your data is stored in a Docker volume (`toybaru-data`). It persists across container restarts and rebuilds.

### Local (Python)

Requires Python 3.10+.

```bash
git clone https://github.com/youruser/toybaru.git
cd toybaru
python -m venv .venv
source .venv/bin/activate
pip install .
toybaru dashboard
```

Open http://127.0.0.1:8099.

Alternatively, you can use the CLI directly:

```bash
toybaru login -r EU
toybaru vehicles
toybaru status <VIN>
toybaru battery <VIN>
toybaru trips <VIN> --from 2025-01-01 --json
toybaru import-trips <VIN> --from 2024-06-01
toybaru trip-stats
toybaru raw GET /v2/vehicle/guid
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `TOYBARU_DATA_DIR` | `~/.config/toybaru` | Directory for databases, tokens, and config |
| `TOYBARU_SESSION_SECRET` | Random per start | Secret for signing session cookies |

## Configuration

### Region config

The tool ships with EU (Europe) and NA (North America) configurations. These are the API endpoints, client IDs, and authentication realms needed to talk to the Subaru/Toyota backend.

To override or add regions, create a `regions.json` file in your data directory:

```bash
# Docker
docker compose cp regions.example.json toybaru:/data/regions.json

# Local
cp regions.example.json ~/.config/toybaru/regions.json
```

Edit the file to change values. You only need to include the fields you want to override -- missing fields fall back to the built-in defaults. See `regions.example.json` for the full structure.

### Adding a language

Create a new JSON file in `src/toybaru/locales/`, for example `fr.json`:

```json
{
  "_meta": {
    "locale": "fr-FR",
    "label": "Francais"
  },
  "app": {
    "name": "Toybaru ReCare",
    ...
  }
}
```

Use `en.json` as a template. The language will appear automatically in the dropdown after restarting the server.

## First steps after installation

1. Open the dashboard and sign in with your Subaru account (same credentials as the SubaruConnect / Subaru Care app)
2. Go to the **Data** tab
3. Set the "From" date to when you got your car and click **Start import**
4. Wait for the import to finish (about 1 minute per 100 trips)
5. Go to **Trips** to browse your data, **Statistics** for the overview

After the initial import, use the **Fetch new trips** button on the Trips tab to pull only the latest data.

## Important notes

- **Tested on a 2023 Subaru Solterra in Germany (EU region) only.** The NA (North America) config is included and should work with the correct auth flow, but has not been fully verified. NA accounts that require OTP/2FA are not yet supported. Feedback from NA users is welcome.
- **Subaru deletes trip data after approximately 12 months.** This is why local storage matters. Import your data regularly.
- **The API does not provide kWh consumption per trip.** The endpoints for energy data exist but return 403 (Forbidden) for the Subaru API client. The estimated consumption shown in debug mode (`?debug` in the URL) is calculated from speed, regeneration ratio, and power ratio using an empirical model.
- **Remote commands (lock/unlock) are fire-and-forget.** The car needs to wake up to process them, which can take 15-60 seconds. The dashboard sends the command and shows cached status.
- **No official API documentation exists.** This project is based on reverse-engineering the SubaruConnect app, the evcc project (github.com/evcc-io/evcc), and the pytoyoda project (github.com/pytoyoda/pytoyoda). The API can change at any time without notice.

## Running tests

```bash
pip install -e ".[test]"
pytest tests/ -v
```

## Contributing

This project is tested with one car in one country. If you have a Solterra or bZ4X in a different region and want to help, contributions are welcome:

- Verify and fix the NA (North America) configuration
- Add region configs for other markets (Japan, Australia, etc.)
- Add translations (just create a new JSON file in `src/toybaru/locales/`)
- Report what works and what doesn't on your vehicle

Open an issue or pull request on GitHub.

## License

This project is licensed under the GNU General Public License.
See [LICENSE](LICENSE) for the full text.

## AI Disclaimer

This project was built with assistance from AI. All code was reviewed by the author.

## Credits

- [evcc](https://github.com/evcc-io/evcc) -- The Subaru EU authentication flow and API endpoints were discovered through their Go implementation
- [pytoyoda](https://github.com/pytoyoda/pytoyoda) -- Toyota Connected Europe API reference and data models
- [SolterraWidget](https://github.com/RossGGG/SolterraWidget) -- North America API endpoints and authentication flow
- OpenStreetMap contributors -- Map tiles
