# Vantage — PMM Intelligence Platform
Vantage is an automated competitive intelligence tool for product marketers. Enter your product and a list of competitors, and Vantage scrapes their websites, mines customer reviews, and uses Claude AI to generate a full strategic report — in minutes.
## What It Does
- **Competitor Research** — Scrapes competitor websites for positioning, value props, features, and pricing
- **Review Mining** — Pulls customer feedback from G2, Capterra, Product Hunt, and Trustpilot
- **Market Intelligence** — Scans Reddit and the web for buyer pain points and market trends
- **Gap Analysis** — Identifies underserved whitespace your product can own
- **Messaging Recommendations** — Generates headlines, proof points, and differentiated positioning
- **Live Progress Feed** — Streams results in real time as the analysis runs
- **Export** — Download the full report as Markdown or copy to clipboard
## Tech Stack
- **Backend:** Python / Flask
- **AI:** Anthropic Claude API
- **Scraping:** Requests + BeautifulSoup
- **Frontend:** HTML/CSS/JS (vanilla)
## Setup
1. Clone the repo
2. Install dependencies:
   ```bash
   pip install -r requirements.txt

Set your Anthropic API key as an environment variable:
export ANTHROPIC_API_KEY=sk-ant-...

Run the app:
python app.py

Open http://localhost:5000 in your browser
Usage
Enter your product name, description, and target market
Add one or more competitor names and URLs
Click Run Analysis
Watch the live feed as Vantage researches and analyzes
Review results across the Competitive, Reviews, Market, Gaps, and Messaging tabs
Export the report when ready
