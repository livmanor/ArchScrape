# ArchScale Intelligence Platform

A company intelligence platform that discovers and collects publicly available business information about architecture firms and interior design companies across India.

---

## Quick Start

### 1. Prerequisites

- Python 3.11 or later (tested on 3.13)
- `pip` (or `py -m pip` on Windows)

### 2. Install Dependencies

```powershell
# Windows — use the py launcher
py -m pip install -r requirements.txt
```

### 3. Prepare Your Approved URL List

Edit `data/seed_urls.csv` with the company websites you want to scrape.
The file must have these columns:

| Column     | Required | Description                                      |
|------------|----------|--------------------------------------------------|
| `url`      | Yes      | Full company website URL (https preferred)       |
| `category` | Yes      | `architecture`, `interior`, or `other`           |
| `notes`    | No       | Human-readable notes (ignored by the scraper)   |

Example:

```csv
url,category,notes
https://www.morphogenesis.org,architecture,Morphogenesis Delhi
https://www.designcafe.com,interior,Design Cafe Bengaluru
```

### 4. Run the Application

```powershell
py -m streamlit run app.py
```

The dashboard will open in your browser at `http://localhost:8501`.

### 5. Run the First Scrape

1. Open the app in your browser.
2. Go to **⚙️ Scrape Control** in the left navigation.
3. Verify the seed URL list.
4. Click **🚀 Start Scrape Run**.
5. Watch the live log for progress.
6. After completion, go to **🔍 Browse Companies** to see results.

---

## Running Tests

```powershell
py -m pytest tests/ -v
```

All tests use synthetic HTML fixtures and temporary databases.
No real company data is embedded in test files.
No network connections are made during testing.

---

## Project Structure

```
ArchScrape/
├── app.py                     # Streamlit dashboard (entry point)
├── requirements.txt
├── conftest.py                # pytest path configuration
├── data/
│   ├── seed_urls.csv          # Approved company URLs (edit this)
│   └── archscale.db           # SQLite database (auto-created)
├── database/
│   ├── db.py                  # Persistence layer (parameterised SQL)
│   └── schema.sql             # Database schema
├── scraper/
│   ├── validator.py           # URL validation + SSRF protection
│   ├── fetcher.py             # Safe HTTP fetching + robots.txt
│   ├── extractor.py           # HTML/JSON-LD extraction pipeline
│   └── discovery.py           # Company URL discovery (seed CSV + future sources)
├── services/
│   └── company_service.py     # Orchestrates scrape pipeline
└── tests/
    ├── test_validator.py
    ├── test_extractor.py
    └── test_database.py
```

---

## Features

### Dashboard
- Summary metrics: companies, evidence rows, review queue, last run status
- Browse, search, and filter companies by name, owner, city, category, verification status
- Company detail view with all extracted fields
- Field-level evidence inspector with source URLs, supporting text, and reviewer controls
- Verification status management per evidence row (Extracted → Source checked → Cross-verified)
- CSV export of filtered results
- Scrape control panel with live log, error display, run history, and error log

### Scraper
- **robots.txt compliance** — checked before every URL
- **SSRF protection** — blocks localhost, private IP ranges, cloud metadata endpoints
- **Redirect re-validation** — SSRF check applied to redirect destinations
- **Rate limiting** — configurable per-domain delay (default 2 seconds)
- **Size limit** — 5 MB response cap to prevent memory issues
- **Sub-page discovery** — automatically finds About, Contact, Team, Leadership pages
- **JSON-LD extraction** — schema.org Organization, LocalBusiness, Person
- **HTML meta extraction** — Open Graph, description tags
- **Heuristic extraction** — phone numbers (Indian patterns), emails, social links, city names

### Data Quality
- Every field retains: extracted value, source URL, supporting text, method, timestamp, status
- **Owner/founder fields marked "Needs review"** — never auto-verified
- Multiple candidates per field stored — the best is not arbitrarily chosen
- Deduplication: repeated scrapes update timestamps, never create duplicate rows
- Honest missing-data reporting: `Not found` status, never fabricated values

---

## Configuration

| Setting              | Location                   | Default                        |
|----------------------|----------------------------|--------------------------------|
| Seed URL list        | `data/seed_urls.csv`       | 10 example architecture firms  |
| Database location    | `data/archscale.db`        | Auto-created                   |
| Request timeout      | `scraper/fetcher.py`       | 15 seconds                     |
| Max response size    | `scraper/fetcher.py`       | 5 MB                           |
| Rate limit (delay)   | `scraper/fetcher.py`       | 2 seconds per domain           |
| Max sub-pages        | `scraper/fetcher.py`       | 10 per company                 |

---

## Limitations

1. **Owner/founder identification** is a high-risk inference. The platform marks all such candidates "Needs review". A human reviewer must confirm ownership before treating the record as verified.

2. **JavaScript-rendered content** cannot be extracted. Many modern websites render their contact and about pages with JavaScript. The scraper only processes server-rendered HTML.

3. **Anti-bot measures** — sites with CAPTCHAs, bot detection, or IP blocking will result in HTTP errors recorded in the error log.

4. **robots.txt** — sites that disallow all crawlers in `robots.txt` are skipped. The URL and reason are logged.

5. **Phone number extraction** uses regex heuristics tuned for Indian formats. International numbers may be missed or mis-classified.

6. **City detection** uses a fixed list of Indian cities. Smaller cities or non-standard spellings may not be detected.

7. **No automatic company discovery** — the MVP relies on the manually approved seed CSV. The `discovery.py` module is designed to accept future directory sources without changing the rest of the pipeline.

---

## Verification Instructions

To demonstrate the platform to stakeholders:

1. Run `py -m streamlit run app.py`
2. Open **⚙️ Scrape Control** and start a scrape
3. Go to **🔍 Browse Companies** — select any company
4. Click through to **🔬 Evidence Inspector**
5. For each field, click the source URL link to verify the value on the live page
6. Use the status dropdown to advance verified values to "Cross-verified"
7. Export results to CSV using the export button

> **Important:** All values displayed originate from publicly accessible web pages. The extraction timestamp and source URL are stored alongside every value. No records are invented, inferred, or fabricated.

---

## Data Retention

To delete all scraped data:
```powershell
Remove-Item data\archscale.db
```
The database will be recreated (empty) on the next application start.

To remove a specific company's data, use the SQLite command line:
```powershell
py -c "import sqlite3; conn=sqlite3.connect('data/archscale.db'); conn.execute('DELETE FROM companies WHERE domain_key=?', ('example.com',)); conn.commit()"
```

---

## Security Notes

- URL validation blocks private IP ranges (RFC 1918), loopback, link-local, and cloud metadata endpoints to prevent SSRF.
- All SQL queries use parameterised statements.
- No credentials or API keys are used or stored.
- The application makes only outbound HTTP GET requests to explicitly approved URLs.
- Response size is capped to prevent memory exhaustion.
