"""
message_generator.py — Generate personalized LinkedIn outreach messages for sellers.

Strategy: Soft, curiosity-driven messages that:
1. Do NOT reveal who the buyer is (confidential)
2. Do NOT say "I want to buy your business" (off-putting)
3. DO create curiosity — "we have a qualified buyer looking for businesses like yours"
4. DO ask a simple question to gauge interest
5. Stay under 300 characters for LinkedIn connection requests
   and under 1900 characters for LinkedIn InMails

Uses Claude API for personalization if ANTHROPIC_API_KEY is set.
Falls back to templates if not.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BROKER_NAME = os.getenv("BROKER_NAME", "Jordi Quevedo-Valls")
BROKER_COMPANY = os.getenv("BROKER_COMPANY", "Valar Brokers")
BROKER_LINKEDIN = os.getenv("BROKER_LINKEDIN", "")

# ── MESSAGE TEMPLATES ─────────────────────────────────────────────────────────

# Short connection request note (<300 chars)
CONNECTION_REQUEST_TEMPLATES = {
    "manufacturing": (
        "Hi {first_name} — I work with private equity groups actively acquiring "
        "{industry} businesses in {state}. Would love to connect and share what "
        "we're seeing in the market."
    ),
    "home services": (
        "Hi {first_name} — we represent buyers specifically looking for "
        "{industry} businesses in {state}. Curious if you've ever thought about "
        "your exit options. Happy to connect."
    ),
    "it": (
        "Hi {first_name} — I'm working with a PE group acquiring IT/MSP businesses "
        "in {state}. No pressure — just wanted to connect and share some market intel."
    ),
    "healthcare": (
        "Hi {first_name} — I represent buyers acquiring healthcare businesses in "
        "{state}. Would love to connect and explore if there's any fit."
    ),
    "legal": (
        "Hi {first_name} — I work with buyers specifically seeking legal services "
        "businesses. Thought it worth connecting to share what we're seeing."
    ),
    "logistics": (
        "Hi {first_name} — representing buyers actively acquiring logistics & freight "
        "businesses. Thought it worth a quick connect — no pressure."
    ),
    "construction": (
        "Hi {first_name} — we have buyers specifically seeking construction/contracting "
        "businesses in {state}. Happy to connect and share details."
    ),
    "aerospace": (
        "Hi {first_name} — I work with PE groups acquiring aerospace & defense "
        "manufacturers. Would love to connect and discuss what we're seeing."
    ),
    "chemicals": (
        "Hi {first_name} — I represent a buyer focused on acquiring chemical sector "
        "businesses. Thought it worth connecting — no obligation at all."
    ),
    "default": (
        "Hi {first_name} — I work with private equity buyers looking to acquire "
        "businesses like {company}. Happy to connect — no pressure, just exploring."
    ),
}

# Full LinkedIn InMail / direct message (<1,900 chars)
INMAIL_TEMPLATES = {
    "manufacturing": """Hi {first_name},

I hope this finds you well. My name is {broker_name} — I'm a business broker who works exclusively with serious, pre-qualified buyers looking to acquire manufacturing businesses.

I came across {company} and I'm reaching out because we currently represent a buyer specifically looking for manufacturing operations in {state} with your profile — they're capitalized, experienced, and ready to move.

I want to be upfront: I'm not here to pressure you into anything. A lot of business owners I connect with aren't actively looking to sell, but are open to understanding what their business is worth in today's market — especially with PE multiples where they are right now.

If you're at all curious about:
• What your business might be worth today
• What a sale/transition could look like
• Whether there's a buyer who'd be the right fit

I'd love to have a 15-minute confidential call.

Would you be open to a quick conversation this week?

Best,
{broker_name}
{broker_company}""",

    "home services": """Hi {first_name},

My name is {broker_name} and I represent pre-qualified buyers actively acquiring home services businesses across {state}.

I came across {company} and wanted to reach out directly — we have a buyer specifically looking for established businesses like yours. They're serious, funded, and can close without bank financing.

Even if you're not actively thinking about selling right now, many business owners find it valuable to understand what their business is worth and what a transition could look like — with no obligation.

Would you be open to a 15-minute confidential conversation to explore?

{broker_name}
{broker_company}""",

    "it": """Hi {first_name},

I'm {broker_name}, a business broker focused on technology and IT services acquisitions.

We're currently working with a PE-backed buyer specifically looking to acquire MSP/IT services businesses in {state}. They're funded, experienced operators — and they move fast when they find the right fit.

{company} caught our attention. If you've ever thought about an exit or partial liquidity event, now might be a great time to understand your options — multiples in IT services are strong right now.

Would you be open to a confidential 15-minute call this week?

Best,
{broker_name}
{broker_company}""",

    "healthcare": """Hi {first_name},

I'm {broker_name} — I work with buyers specifically acquiring healthcare businesses in {state}.

We have a well-capitalized buyer looking for practices and healthcare businesses with your profile. Even if selling isn't on your radar today, understanding your options and current market value is always valuable.

Would you be open to a quick 15-minute confidential call?

{broker_name}
{broker_company}""",

    "legal": """Hi {first_name},

I'm {broker_name}, a business broker who works with buyers acquiring legal services businesses.

We currently represent a buyer specifically interested in legal and legal support businesses in {state} — particularly businesses with consistent, recurring revenue. They're pre-qualified and serious.

Would you be open to a brief confidential conversation to see if there's any fit?

{broker_name}
{broker_company}""",

    "logistics": """Hi {first_name},

My name is {broker_name} and I represent buyers actively acquiring logistics and freight businesses across the US.

We have a well-capitalized buyer specifically looking for businesses like {company}. Freight and transportation businesses are trading at strong multiples right now, and buyers are moving quickly.

If you're curious about what your business might be worth or what an exit could look like, I'd love to have a brief confidential conversation.

Would a 15-minute call work for you this week?

{broker_name}
{broker_company}""",

    "aerospace": """Hi {first_name},

I'm {broker_name}, and I represent buyers specifically focused on aerospace and defense manufacturers.

We have a buyer actively looking for businesses like {company} — they're experienced in the space, well-capitalized, and serious about the right acquisition.

If you've ever thought about your exit timeline, now might be a great time to understand your options. I'd welcome a brief confidential conversation.

Would 15 minutes work this week?

{broker_name}
{broker_company}""",

    "construction": """Hi {first_name},

My name is {broker_name} — I work with buyers specifically seeking construction and contracting businesses in {state}.

We have a pre-qualified buyer looking for established businesses like {company}. They understand the industry, have the capital, and can move quickly.

Even if you're not ready to sell today, understanding your current market value is valuable. Would you be open to a brief confidential conversation?

{broker_name}
{broker_company}""",

    "default": """Hi {first_name},

My name is {broker_name} — I'm a business broker who works with serious, pre-qualified buyers looking to acquire businesses like {company}.

We currently have a buyer specifically interested in your sector and geography. They're capitalized, experienced, and ready to move on the right opportunity.

I wanted to reach out directly because the best deals we put together are never publicly listed — they come from conversations like this one.

Would you be open to a brief, confidential 15-minute call to see if there's any fit? No pressure, no obligation.

Best,
{broker_name}
{broker_company}""",
}


def _get_template(template_dict: dict, industry: str) -> str:
    """Get best matching template for an industry."""
    ind_lower = industry.lower()
    for key in template_dict:
        if key in ind_lower or ind_lower in key:
            return template_dict[key]
    return template_dict["default"]


def generate_connection_request(lead: dict) -> str:
    """Generate a short LinkedIn connection request note (<300 chars)."""
    name_parts = lead.get("owner_name", "there").split()
    first_name = name_parts[0] if name_parts else "there"
    industry = lead.get("industry", "business services")
    state = lead.get("state", "your area")
    company = lead.get("company_name", "your company")

    template = _get_template(CONNECTION_REQUEST_TEMPLATES, industry)

    msg = template.format(
        first_name=first_name,
        industry=industry,
        state=state,
        company=company,
        broker_name=BROKER_NAME,
    )

    # Ensure <300 chars
    if len(msg) > 295:
        msg = msg[:292] + "..."

    return msg


def generate_inmail(lead: dict) -> str:
    """Generate a full LinkedIn InMail / direct message."""
    name_parts = lead.get("owner_name", "there").split()
    first_name = name_parts[0] if name_parts else "there"
    industry = lead.get("industry", "business services")
    state = lead.get("state", "your area")
    company = lead.get("company_name", "your company")

    template = _get_template(INMAIL_TEMPLATES, industry)

    msg = template.format(
        first_name=first_name,
        industry=industry,
        state=state,
        company=company,
        broker_name=BROKER_NAME,
        broker_company=BROKER_COMPANY,
    )

    return msg


def generate_messages_with_ai(lead: dict, buyer: dict) -> dict:
    """
    Use Claude API to generate highly personalized messages.
    Falls back to templates if API key not available.
    """
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY in ("sk-ant-REPLACE_ME", "REPLACE_ME"):
        return {
            "connection_request": generate_connection_request(lead),
            "inmail": generate_inmail(lead),
        }

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        name_parts = lead.get("owner_name", "the owner").split()
        first_name = name_parts[0] if name_parts else "the owner"

        prompt = f"""You are {BROKER_NAME}, a business broker at {BROKER_COMPANY}.

Write two LinkedIn outreach messages to reach out to the owner of this business:

BUSINESS:
- Name: {lead.get('company_name', 'Unknown')}
- Industry: {lead.get('industry', 'Unknown')}
- Location: {lead.get('city', '')}, {lead.get('state', '')}
- Owner first name: {first_name}
- Description: {lead.get('description', 'N/A')}

BUYER CONTEXT (do NOT reveal buyer identity or details):
- We have a pre-qualified buyer looking for {', '.join(buyer.get('industries', []))} businesses
- Target geography: {', '.join(buyer.get('states', buyer.get('geographies', ['US'])))}
- Deal size: ${buyer.get('deal_size_min', 0):,} - ${min(buyer.get('deal_size_max', 50_000_000), 50_000_000):,}

Write:
1. CONNECTION_REQUEST: A soft, curiosity-driven LinkedIn connection request note. MAX 280 characters. DO NOT mention buying or selling directly. Create intrigue.

2. INMAIL: A professional LinkedIn InMail message. MAX 1,500 characters. Be direct but respectful. Mention you work with buyers in their industry. Ask if they've ever thought about exit options. No pressure. End with a soft CTA for a 15-minute call.

Format your response as JSON:
{{"connection_request": "...", "inmail": "..."}}

Rules:
- Never reveal the buyer's name or specific identity
- Do not say "I want to buy your business"
- Do not use generic corporate language
- Be warm, direct, and human
- Focus on value to the seller (market intel, knowing their options)"""

        response = client.messages.create(
            model="claude-haiku-3-5-20241022",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Extract JSON
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])

    except Exception as e:
        print(f"  [AI] Message generation error: {e} — using templates")

    return {
        "connection_request": generate_connection_request(lead),
        "inmail": generate_inmail(lead),
    }


def add_messages_to_leads(leads: list, buyer: dict) -> list:
    """Add personalized messages to each lead dict."""
    print(f"\n[MESSAGES] Generating messages for {len(leads)} leads...")
    for i, lead in enumerate(leads):
        messages = generate_messages_with_ai(lead, buyer)
        lead["connection_request"] = messages.get("connection_request", "")
        lead["inmail"] = messages.get("inmail", "")
        lead["linkedin_search_url"] = generate_linkedin_owner_search_url(lead)
        if i % 10 == 0 and i > 0:
            print(f"  → Generated {i}/{len(leads)} messages")
    print(f"  → Done: {len(leads)} messages generated")
    return leads


def generate_linkedin_owner_search_url(lead: dict) -> str:
    """Generate a LinkedIn search URL to find the owner of this company."""
    company = lead.get("company_name", "")
    if not company:
        return ""

    import urllib.parse
    query = urllib.parse.quote(f'"{company}" owner OR founder OR CEO OR president')
    return f"https://www.linkedin.com/search/results/people/?keywords={query}"


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from buyers_db import BUYERS

    # Test lead
    test_lead = {
        "company_name": "Precision Metal Works Inc",
        "industry": "manufacturing",
        "city": "Chicago",
        "state": "IL",
        "owner_name": "Robert Johnson",
        "description": "CNC machining and metal fabrication for industrial clients",
    }
    test_buyer = next(b for b in BUYERS if b["id"] == "magus_abraxas")

    messages = generate_messages_with_ai(test_lead, test_buyer)
    print("CONNECTION REQUEST:")
    print(messages["connection_request"])
    print(f"\nLength: {len(messages['connection_request'])} chars")
    print("\nINMAIL:")
    print(messages["inmail"])
