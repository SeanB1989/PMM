"""
Vantage — PMM Intelligence Platform
Flask backend: competitive analysis, review mining, gap identification, messaging.
"""

import os
import json
import uuid
import threading
import time
from flask import Flask, render_template, request, Response, jsonify, stream_with_context

# Load .env if present (for local/Replit dev)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from modules.scraper import (
    scrape_competitor,
    gather_review_intelligence,
    search_market_intel,
    format_competitor_content,
    format_review_intelligence,
)
from modules.analyzer import run_full_analysis

app = Flask(__name__)

# ── API key: set ANTHROPIC_API_KEY in your .env or environment ──────
def get_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to your .env file: "
            "ANTHROPIC_API_KEY=sk-ant-..."
        )
    return key

# In-memory job store
jobs = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    try:
        get_api_key()
        return jsonify({"status": "ok", "api_key_configured": True})
    except RuntimeError:
        return jsonify({"status": "ok", "api_key_configured": False})


@app.route("/analyze", methods=["POST"])
def start_analysis():
    data = request.json

    product_name = data.get("product_name", "").strip()
    product_description = data.get("product_description", "").strip()
    target_market = data.get("target_market", "").strip()
    competitors_raw = data.get("competitors", [])

    if not product_name:
        return jsonify({"error": "Product name is required"}), 400
    if not competitors_raw:
        return jsonify({"error": "At least one competitor is required"}), 400

    try:
        api_key = get_api_key()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "running",
        "events": [],
        "results": None,
        "error": None,
        "meta": {
            "product_name": product_name,
            "competitors": [c["name"] for c in competitors_raw],
        },
    }

    thread = threading.Thread(
        target=run_job,
        args=(job_id, api_key, product_name, product_description, target_market, competitors_raw),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


def run_job(job_id, api_key, product_name, product_description, target_market, competitors_raw):
    job = jobs[job_id]

    def push(event_type, data):
        job["events"].append({"type": event_type, "data": data, "ts": time.time()})

    try:
        # ── Phase 1: Scrape competitor sites ────────────────────────
        push("phase", "Researching competitors")
        competitors_formatted = []
        for comp in competitors_raw:
            push("progress", f"Scanning {comp['name']} website…")
            try:
                scraped = scrape_competitor(comp["name"], comp["url"])
                formatted = format_competitor_content(scraped)
                competitors_formatted.append(formatted)
                push("progress", f"✓ {comp['name']} — {len(scraped['pages'])} pages captured")
            except Exception as e:
                competitors_formatted.append(f"=== {comp['name']} ===\n[Scraping failed: {e}]")
                push("progress", f"⚠ {comp['name']} — partial data only")

        # ── Phase 2: Review intelligence ─────────────────────────────
        push("phase", "Mining customer reviews")
        all_review_findings = []
        for comp in competitors_raw:
            push("progress", f"Pulling reviews for {comp['name']}…")
            def _log(msg, _comp=comp):
                push("progress", msg)
            findings = gather_review_intelligence(comp["name"], progress_cb=_log)
            all_review_findings.append(findings)
            push("progress", f"✓ {comp['name']} — reviews gathered from {len(findings['sources'])} sources")

        reviews_formatted = format_review_intelligence(all_review_findings)

        # ── Phase 3: Market intelligence ─────────────────────────────
        push("phase", "Scanning the market")
        push("progress", "Gathering market discussions, trends, and buyer signals…")
        def _mkt_log(msg):
            push("progress", msg)
        market_formatted = search_market_intel(product_description, target_market, progress_cb=_mkt_log)
        push("progress", "✓ Market intelligence gathered")

        # ── Phase 4–8: AI Analysis ────────────────────────────────────
        push("phase", "AI analysis in progress")
        push("progress", "All data collected — starting Claude analysis…")

        def progress_callback(event_type, data):
            push(event_type, data)

        results = run_full_analysis(
            api_key=api_key,
            product_name=product_name,
            product_description=product_description,
            target_market=target_market,
            competitors_formatted=competitors_formatted,
            reviews_formatted=reviews_formatted,
            market_formatted=market_formatted,
            progress_callback=progress_callback,
        )

        job["results"] = results
        job["status"] = "done"
        push("complete", results)

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        push("error", str(e))


@app.route("/stream/<job_id>")
def stream_events(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        sent_index = 0
        while True:
            job = jobs.get(job_id, {})
            events = job.get("events", [])
            while sent_index < len(events):
                evt = events[sent_index]
                payload = json.dumps({"type": evt["type"], "data": evt["data"]})
                yield f"data: {payload}\n\n"
                sent_index += 1
            if job.get("status") in ("done", "error"):
                break
            time.sleep(0.08)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/results/<job_id>")
def get_results(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    job = jobs[job_id]
    return jsonify({
        "status": job["status"],
        "results": job.get("results"),
        "error": job.get("error"),
        "meta": job.get("meta"),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
