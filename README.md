# roomnl-stats

Statistics and forecasting dashboard for [roommatch.nl](https://www.roommatch.nl/en/recently-rented) student housing registration times in the Netherlands.

A Playwright scraper collects the "recently rented" table, a Gaussian Process model fits seasonal patterns and predicts future registration times with confidence intervals, and a static SvelteKit site visualises it all.

## Architecture

```
pipeline/
  scraper.py          # Headless Playwright scraper for roommatch.nl
  roomnl_model.py     # GP regression model (sklearn) with calendar features
  generate.py         # Orchestrates scrape -> model fit -> JSON export

site/                 # SvelteKit + Tailwind CSS static site
  src/lib/components/
    ForecastChart.svelte   # D3 interactive chart (zoom, pan, tooltips)
    DataTable.svelte       # Sortable, filterable data table
    Filters.svelte         # City/room-type filter controls

data/
  recently_rented.parquet  # Unified historical dataset

.github/workflows/
  ci.yaml             # Lint, type-check, test (Python 3.12/3.13 + Node 22)
  deploy.yaml          # Bi-weekly scrape + rebuild + GitHub Pages deploy
```

## Model

The forecast uses a Gaussian Process with an RBF + WhiteNoise kernel, trained on weekly-aggregated registration times. Calendar features encode:

- **Yearly seasonality** -- Fourier terms (sin/cos, 1st and 2nd harmonics)
- **Semester bumps** -- Gaussian bumps around 1 Sep and 1 Feb intake dates
- **Exam windows** -- Gaussian bumps around late Jan and late Jun
- **Holiday flags** -- Summer (Jul-Aug) and winter break (Dec 20 - Jan 7)

An optional Google Trends monthly multiplier can modulate predictions to capture year-over-year demand shifts.

## Setup

### Prerequisites

- Python >= 3.12
- Node.js >= 22
- [Poetry](https://python-poetry.org/)

### Install

```bash
# Python dependencies
poetry install

# Playwright browser (for scraping)
poetry run python -m playwright install --with-deps chromium

# Frontend dependencies
cd site && npm install
```

## Usage

### Generate data

Scrapes roommatch.nl, fits the model, and writes JSON to `site/static/data/`:

```bash
poetry run python -m pipeline.generate
```

### Run the site locally

```bash
cd site
npm run dev
```

### Run checks

```bash
# Python
poetry run ruff check pipeline/ tests/
poetry run ruff format --check pipeline/ tests/
poetry run mypy pipeline/
poetry run pytest tests/ -x -q

# Frontend
cd site
npm run lint
npm run check
npm run build
```

## CI/CD

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| **CI** | Push / PR to `main` | Ruff, mypy, pytest, radon (Python 3.12 + 3.13), ESLint, svelte-check, build |
| **Scrape & Deploy** | Bi-weekly cron (1st & 15th) or manual | Scrapes fresh data, regenerates predictions, commits updated parquet, builds and deploys to GitHub Pages |

## License

MIT
