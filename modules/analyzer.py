"""
AI Analysis module for PMM Intelligence Tool
Uses Claude API via direct HTTP calls (no anthropic SDK required).
"""

import requests
import json


CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-opus-4-5"


def call_claude(api_key, system_prompt, user_prompt, max_tokens=2500, stream_callback=None):
    """
    Call Claude API. If stream_callback is provided, streams chunks to it.
    Returns the full response text.
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "stream": stream_callback is not None,
    }

    if stream_callback:
        full_text = ""
        with requests.post(CLAUDE_API_URL, headers=headers, json=payload, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        if data.get("type") == "content_block_delta":
                            chunk = data.get("delta", {}).get("text", "")
                            if chunk:
                                full_text += chunk
                                stream_callback(chunk)
                    except json.JSONDecodeError:
                        pass
        return full_text
    else:
        resp = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


def analyze_competitors(api_key, competitors_data, product_name, product_description, callback=None):
    system = """You are a senior product marketing analyst. Analyze competitor data and extract:
1. Their core positioning statement (how they define themselves)
2. Key value propositions they lead with
3. Target audience signals (who they seem to be selling to)
4. Pricing model/signals (if visible)
5. Key features/capabilities they highlight
6. Tone and messaging style

Be specific and quote directly from their content where relevant. Be concise but thorough."""

    competitor_text = "\n\n".join(competitors_data)
    prompt = f"""We are analyzing competitors for {product_name}: {product_description}

Here is scraped content from competitor websites:

{competitor_text[:12000]}

For each competitor, provide a structured analysis covering positioning, value props, target audience, pricing signals, highlighted capabilities, and messaging tone. Format as clear sections per competitor."""

    return call_claude(api_key, system, prompt, stream_callback=callback)


def analyze_reviews(api_key, review_data, competitors, callback=None):
    system = """You are a customer insights analyst specializing in B2B software.
Analyze customer review data and identify:
1. Most common praise themes (what customers love)
2. Most common complaint themes (what frustrates customers)
3. Switching triggers (why people switch away)
4. Unmet needs customers mention
5. Features/capabilities that are deal-breakers when missing
6. How customers describe the value they get

Focus on patterns, not individual reviews. Be specific."""

    competitors_str = ", ".join(competitors) if competitors else "these companies"
    prompt = f"""Analyze these customer review search results for {competitors_str}.

Review data:
{review_data[:10000]}

Identify the key sentiment themes — what do customers love, hate, and wish existed?
What pain points come up repeatedly? What do buyers seem to care most about?
Group insights by theme."""

    return call_claude(api_key, system, prompt, stream_callback=callback)


def analyze_market(api_key, market_data, target_market, product_description, callback=None):
    system = """You are a market intelligence analyst. Analyze search data about a market to identify:
1. Top buyer pain points and challenges
2. What buyers prioritize when evaluating solutions
3. Emerging trends shaping the category
4. Language buyers use to describe their problems (exact phrases matter for messaging)
5. Gaps between what's available and what buyers actually want

Be specific. Extract actual language patterns from the data."""

    prompt = f"""Analyze this market intelligence data for the {target_market} market evaluating {product_description} solutions.

Market research data:
{market_data[:10000]}

What are the dominant pain points? What language do buyers use? What trends matter?
What do buyers say they can't find in existing solutions?"""

    return call_claude(api_key, system, prompt, stream_callback=callback)


def identify_gaps(api_key, competitive_analysis, review_analysis, market_analysis,
                  product_name, product_description, callback=None):
    system = """You are a strategic product marketing advisor. Your job is to identify
positioning gaps and market opportunities by cross-referencing competitive intelligence,
customer sentiment, and market research.

Look for:
1. Pain points buyers have that no competitor addresses well
2. Claims competitors make that customer reviews say don't hold up
3. Market trends that no one is positioned against yet
4. Audience segments that appear underserved
5. Messaging angles that are completely unclaimed in the market
6. Features/capabilities buyers want that are absent or poorly marketed

Be specific and strategic. Each gap should be actionable."""

    prompt = f"""You have analyzed the market for {product_name} ({product_description}).

COMPETITIVE ANALYSIS:
{competitive_analysis[:3000]}

CUSTOMER REVIEW THEMES:
{review_analysis[:3000]}

MARKET INTELLIGENCE:
{market_analysis[:3000]}

Now identify the most important gaps and opportunities. What is the whitespace?
Where are competitors weak despite their claims? What do buyers want that nobody delivers?
Rank by strategic importance."""

    return call_claude(api_key, system, prompt, stream_callback=callback)


def generate_messaging(api_key, gap_analysis, product_name, product_description,
                       target_market, competitive_analysis, callback=None):
    system = """You are a world-class B2B product marketing strategist.
Generate specific, differentiated messaging recommendations that are:
- Grounded in real market gaps (not generic claims)
- Specific enough to be useful, not generic platitudes
- Written in the voice of a confident market leader
- Designed to resonate with the identified target buyer pain points

For each messaging angle provide:
- The strategic rationale (why this works)
- A headline/positioning statement
- 2-3 supporting proof points or sub-messages
- Suggested tone and approach"""

    prompt = f"""Create messaging recommendations for {product_name} ({product_description}) targeting {target_market}.

COMPETITIVE LANDSCAPE (summary):
{competitive_analysis[:1500]}

IDENTIFIED GAPS & OPPORTUNITIES:
{gap_analysis}

Generate 4-5 distinct messaging angles, each grounded in a specific market gap or opportunity.
These should be differentiated and defensible — not generic claims.
Include a recommended primary positioning statement."""

    return call_claude(api_key, system, prompt, stream_callback=callback)


def run_full_analysis(api_key, product_name, product_description, target_market,
                      competitors_formatted, reviews_formatted, market_formatted,
                      progress_callback=None):
    """
    Run the complete analysis pipeline.
    progress_callback(event_type, data) is called at each stage.
    Returns dict with all analysis sections.
    """

    def emit(event_type, data):
        if progress_callback:
            progress_callback(event_type, data)

    results = {}

    # Stage 1: Competitive
    emit("stage", "Analyzing competitor positioning and messaging...")
    def comp_cb(chunk): emit("chunk", {"section": "competitive", "text": chunk})
    results["competitive"] = analyze_competitors(
        api_key, competitors_formatted, product_name, product_description, comp_cb
    )

    # Stage 2: Reviews
    emit("stage", "Mining customer reviews for sentiment and themes...")
    comp_names = [c.split("===")[1].split("(")[0].strip() for c in competitors_formatted if "===" in c]
    def rev_cb(chunk): emit("chunk", {"section": "reviews", "text": chunk})
    results["reviews"] = analyze_reviews(api_key, reviews_formatted, comp_names, rev_cb)

    # Stage 3: Market
    emit("stage", "Analyzing market trends and buyer priorities...")
    def mkt_cb(chunk): emit("chunk", {"section": "market", "text": chunk})
    results["market"] = analyze_market(api_key, market_formatted, target_market, product_description, mkt_cb)

    # Stage 4: Gaps
    emit("stage", "Identifying gaps and opportunities...")
    def gap_cb(chunk): emit("chunk", {"section": "gaps", "text": chunk})
    results["gaps"] = identify_gaps(
        api_key, results["competitive"], results["reviews"], results["market"],
        product_name, product_description, gap_cb
    )

    # Stage 5: Messaging
    emit("stage", "Generating differentiated messaging recommendations...")
    def msg_cb(chunk): emit("chunk", {"section": "messaging", "text": chunk})
    results["messaging"] = generate_messaging(
        api_key, results["gaps"], product_name, product_description,
        target_market, results["competitive"], msg_cb
    )

    emit("done", "Analysis complete!")
    return results
