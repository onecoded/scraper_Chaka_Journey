"""
match_deals.py
--------------
Scores every scraped deal against every buyer's criteria.
Outputs matches above the minimum score threshold to matches.json.

Scoring: Two-phase
  Phase 1 — Hard stops: auto-disqualify if any critical criteria fail
  Phase 2 — Weighted scoring across 6 dimensions (total = 100 pts)

Grades: A=80+, B=60-79, C=40-59, below 40 = dropped

Usage:
    python tools/match_deals.py
    python tools/match_deals.py --listings .tmp/all_listings.json --buyers .tmp/buyers.json --out .tmp/matches.json --min-score 40
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Industry matching helpers
# ---------------------------------------------------------------------------

# Broad category groupings for partial industry matching
INDUSTRY_GROUPS = {
    "home_services": [
        "hvac", "plumbing", "electrical", "roofing", "landscaping",
        "pest control", "cleaning", "janitorial", "painting", "handyman",
        "home services", "home repair", "home improvement", "pool",
        "gutters", "insulation", "flooring", "windows", "doors",
    ],
    "automotive": [
        "auto repair", "automotive", "car wash", "auto body", "tire",
        "oil change", "auto parts", "transmission", "mechanic",
    ],
    "food_beverage": [
        "restaurant", "cafe", "bakery", "food", "catering", "bar",
        "brewery", "winery", "food truck", "deli", "pizza",
    ],
    "healthcare": [
        "healthcare", "medical", "dental", "optometry", "pharmacy",
        "chiropractic", "physical therapy", "veterinary", "vet", "spa",
    ],
    "technology": [
        "saas", "software", "technology", "it services", "managed services",
        "web", "app", "digital", "ecommerce", "e-commerce", "online",
    ],
    "manufacturing": [
        "manufacturing", "production", "fabrication", "machining",
        "custom parts", "industrial",
    ],
    "distribution": [
        "distribution", "wholesale", "logistics", "trucking", "freight",
        "supply", "warehouse",
    ],
    "retail": [
        "retail", "store", "shop", "boutique", "resale",
    ],
    "services": [
        "staffing", "consulting", "accounting", "bookkeeping",
        "financial", "insurance", "real estate brokerage", "marketing",
        "advertising", "printing", "sign", "security",
    ],
    "childcare_education": [
        "childcare", "daycare", "preschool", "tutoring", "education",
        "learning center", "school",
    ],
    "fitness": [
        "gym", "fitness", "yoga", "martial arts", "crossfit",
        "personal training",
    ],
    "hospitality": [
        "hotel", "motel", "bed and breakfast", "inn", "resort",
        "airbnb", "vacation rental",
    ],
    "construction": [
        "construction", "contracting", "general contractor", "remodeling",
        "renovation", "concrete", "masonry", "framing",
    ],
    "laundry": [
        "laundry", "dry cleaning", "laundromat", "coin laundry",
    ],
}

# Map each keyword to its group
KEYWORD_TO_GROUP: dict[str, str] = {}
for group, keywords in INDUSTRY_GROUPS.items():
    for kw in keywords:
        KEYWORD_TO_GROUP[kw] = group


def get_industry_group(industry_str: str) -> str | None:
    if not industry_str:
        return None
    low = industry_str.lower()
    for kw, group in KEYWORD_TO_GROUP.items():
        if kw in low:
            return group
    return None


def industry_match_score(deal_industry: str, buyer_prefs: list[str], buyer_exclusions: list[str], weight: int) -> tuple[int, str]:
    """
    Returns (score, reason).
    Full score = exact/near match; 60% = same broad category; 0 = no match.
    Hard stop if industry is in exclusions.
    """
    if not deal_industry:
        return int(weight * 0.3), "Industry not specified in listing"

    deal_low = deal_industry.lower()

    # Check exclusions first
    for excl in buyer_exclusions:
        if excl.lower() in deal_low or deal_low in excl.lower():
            return -1, f"EXCLUDED: industry matches exclusion '{excl}'"

    # Exact / near match to any preference
    for pref in buyer_prefs:
        if pref.lower() in deal_low or deal_low in pref.lower():
            return weight, f"Industry '{deal_industry}' matches preference '{pref}'"

    # Broad category match
    deal_group = get_industry_group(deal_industry)
    if deal_group:
        for pref in buyer_prefs:
            pref_group = get_industry_group(pref)
            if pref_group and pref_group == deal_group:
                return int(weight * 0.6), f"Industry '{deal_industry}' is in same category as '{pref}' ({deal_group})"

    # No preferences set = neutral
    if not buyer_prefs:
        return int(weight * 0.5), "No industry preference set (neutral)"

    return 0, f"Industry '{deal_industry}' does not match any buyer preference"


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

def score_deal_for_buyer(deal: dict, buyer: dict) -> dict | None:
    """
    Score a deal against a buyer's criteria.
    Returns a MatchResult dict, or None if a hard stop is triggered.
    """
    criteria = buyer["criteria"]
    fin = criteria["financials"]
    ds = criteria["deal_structure"]
    ba = criteria["business_attributes"]
    weights = criteria["scoring_weights"]

    hard_stops = []
    soft_flags = []
    scores = {}

    # -----------------------------------------------------------------------
    # Phase 1: Hard Stops
    # -----------------------------------------------------------------------

    asking_price = deal.get("asking_price")
    annual_revenue = deal.get("annual_revenue")
    cash_flow = deal.get("cash_flow") or deal.get("sde")
    deal_state = deal.get("location_state", "")
    deal_industry = deal.get("industry", "")

    # Asking price range
    if fin.get("asking_price_max") and asking_price:
        if asking_price > fin["asking_price_max"]:
            hard_stops.append(
                f"Asking price ${asking_price:,} exceeds buyer max ${fin['asking_price_max']:,}"
            )
    if fin.get("asking_price_min") and asking_price:
        if asking_price < fin["asking_price_min"]:
            hard_stops.append(
                f"Asking price ${asking_price:,} below buyer min ${fin['asking_price_min']:,}"
            )

    # Geography
    target_states = criteria.get("geography_states", [])
    if target_states and deal_state and deal_state not in target_states:
        hard_stops.append(
            f"State {deal_state} not in buyer's target states {target_states}"
        )

    # Cash flow minimum
    if fin.get("cash_flow_min") and cash_flow:
        if cash_flow < fin["cash_flow_min"]:
            hard_stops.append(
                f"Cash flow ${cash_flow:,} below buyer min ${fin['cash_flow_min']:,}"
            )

    # Industry exclusions (checked inside industry_match_score too, but enforce as hard stop)
    for excl in criteria.get("industry_exclusions", []):
        if deal_industry and excl.lower() in deal_industry.lower():
            hard_stops.append(f"Industry '{deal_industry}' is excluded by buyer")

    if hard_stops:
        return None  # disqualified

    # -----------------------------------------------------------------------
    # Phase 2: Weighted Scoring
    # -----------------------------------------------------------------------

    # --- Industry Match (default 30 pts) ---
    ind_score, ind_reason = industry_match_score(
        deal_industry,
        criteria.get("industry_preferences", []),
        criteria.get("industry_exclusions", []),
        weights.get("industry_match", 30)
    )
    if ind_score == -1:
        return None  # industry exclusion hard stop
    scores["industry_match"] = {"score": ind_score, "max": weights.get("industry_match", 30), "reason": ind_reason}

    # --- Geography Match (default 20 pts) ---
    geo_weight = weights.get("geography_match", 20)
    if not target_states:
        geo_score = geo_weight  # No restriction = full points
        geo_reason = "No geographic restriction set"
    elif deal_state in target_states:
        geo_score = geo_weight
        geo_reason = f"State {deal_state} is in buyer's target list"
    else:
        geo_score = 0
        geo_reason = f"State {deal_state} not in target list"
    scores["geography_match"] = {"score": geo_score, "max": geo_weight, "reason": geo_reason}

    # --- Financials In Range (default 25 pts) ---
    fin_weight = weights.get("financials_in_range", 25)
    fin_score = 0
    fin_reasons = []

    # Price in range (40% of fin weight)
    price_pts = fin_weight * 0.4
    if not asking_price:
        soft_flags.append("Asking price not listed")
        fin_score += price_pts * 0.3  # partial credit for unknown
        fin_reasons.append("Asking price unknown (partial credit)")
    elif (
        (not fin.get("asking_price_max") or asking_price <= fin["asking_price_max"]) and
        (not fin.get("asking_price_min") or asking_price >= fin["asking_price_min"])
    ):
        fin_score += price_pts
        fin_reasons.append(f"Price ${asking_price:,} in range")
    else:
        fin_reasons.append(f"Price ${asking_price:,} outside preferred range")

    # Revenue in range (32% of fin weight)
    rev_pts = fin_weight * 0.32
    if not annual_revenue:
        soft_flags.append("Annual revenue not listed")
        fin_score += rev_pts * 0.3
        fin_reasons.append("Revenue unknown (partial credit)")
    elif (
        (not fin.get("revenue_max") or annual_revenue <= fin["revenue_max"]) and
        (not fin.get("revenue_min") or annual_revenue >= fin["revenue_min"])
    ):
        fin_score += rev_pts
        fin_reasons.append(f"Revenue ${annual_revenue:,} in range")
    else:
        fin_reasons.append(f"Revenue ${annual_revenue:,} outside preferred range")

    # Cash flow above minimum (28% of fin weight)
    cf_pts = fin_weight * 0.28
    if not cash_flow:
        soft_flags.append("Cash flow/SDE not listed")
        fin_score += cf_pts * 0.3
        fin_reasons.append("Cash flow unknown (partial credit)")
    elif not fin.get("cash_flow_min") or cash_flow >= fin["cash_flow_min"]:
        if fin.get("cash_flow_max") and cash_flow > fin["cash_flow_max"]:
            fin_score += cf_pts * 0.8  # Slightly above max, still good
            fin_reasons.append(f"Cash flow ${cash_flow:,} slightly above max (good sign)")
        else:
            fin_score += cf_pts
            fin_reasons.append(f"Cash flow ${cash_flow:,} in range")
    else:
        fin_reasons.append(f"Cash flow ${cash_flow:,} below minimum")

    scores["financials_in_range"] = {
        "score": round(fin_score, 1),
        "max": fin_weight,
        "reason": "; ".join(fin_reasons)
    }

    # --- Cash Flow Multiple (default 10 pts) ---
    cf_mult_weight = weights.get("cash_flow_multiple", 10)
    cf_mult_score = 0
    cf_mult_reason = ""
    max_multiple = fin.get("cash_flow_multiple_max") or 5.0

    if cash_flow and asking_price and cash_flow > 0:
        multiple = asking_price / cash_flow
        if multiple <= max_multiple:
            # Better deals get higher scores (lower multiple = better)
            cf_mult_score = cf_mult_weight * (1 - (multiple / max_multiple) * 0.5)
            cf_mult_reason = f"Multiple {multiple:.1f}x vs max {max_multiple}x (good)"
        else:
            cf_mult_score = 0
            cf_mult_reason = f"Multiple {multiple:.1f}x exceeds max {max_multiple}x"
    else:
        soft_flags.append("Cannot calculate price/CF multiple (missing data)")
        cf_mult_score = cf_mult_weight * 0.3
        cf_mult_reason = "Multiple unknown (partial credit)"

    scores["cash_flow_multiple"] = {
        "score": round(cf_mult_score, 1),
        "max": cf_mult_weight,
        "reason": cf_mult_reason
    }

    # --- Years Established (default 8 pts) ---
    yr_weight = weights.get("years_established", 8)
    years = deal.get("years_established")
    min_years = ba.get("years_in_business_min") or 3

    if not years:
        soft_flags.append("Years in business not listed")
        yr_score = yr_weight * 0.4
        yr_reason = "Years unknown (partial credit)"
    elif years < min_years:
        yr_score = 0
        yr_reason = f"Only {years} years, below buyer min {min_years}"
    elif years >= 10:
        yr_score = yr_weight
        yr_reason = f"{years} years established (strong)"
    else:
        yr_score = yr_weight * (years / 10)
        yr_reason = f"{years} years established"

    scores["years_established"] = {"score": round(yr_score, 1), "max": yr_weight, "reason": yr_reason}

    # --- Deal Structure (default 7 pts) ---
    struct_weight = weights.get("deal_structure", 7)
    struct_score = 0
    struct_reasons = []

    sba_eligible = deal.get("sba_eligible")
    financing_available = deal.get("financing_available")

    if ds.get("sba_loan_preferred") and sba_eligible:
        struct_score += struct_weight * 0.6
        struct_reasons.append("SBA eligible (preferred)")
    elif ds.get("sba_loan_preferred") and sba_eligible is None:
        soft_flags.append("SBA eligibility not confirmed in listing")
        struct_score += struct_weight * 0.2
        struct_reasons.append("SBA eligibility unknown")

    if ds.get("seller_financing_ok") and financing_available:
        struct_score += struct_weight * 0.4
        struct_reasons.append("Seller financing available")
    elif financing_available is None:
        soft_flags.append("Financing availability not stated")

    if ds.get("all_cash_ok") and not financing_available:
        struct_score += struct_weight * 0.3
        struct_reasons.append("All-cash deal (buyer OK with this)")

    struct_score = min(struct_score, struct_weight)
    scores["deal_structure"] = {
        "score": round(struct_score, 1),
        "max": struct_weight,
        "reason": "; ".join(struct_reasons) if struct_reasons else "No deal structure match"
    }

    # -----------------------------------------------------------------------
    # Totals and grade
    # -----------------------------------------------------------------------

    total = sum(s["score"] for s in scores.values())
    max_total = sum(s["max"] for s in scores.values())
    score_pct = round((total / max_total) * 100, 1) if max_total > 0 else 0

    if score_pct >= 80:
        grade = "A"
    elif score_pct >= 60:
        grade = "B"
    elif score_pct >= 40:
        grade = "C"
    else:
        grade = "F"

    match_summary_parts = [
        s["reason"] for s in scores.values()
        if s["score"] > 0 and "unknown" not in s["reason"].lower()
    ]
    match_summary = " | ".join(match_summary_parts[:3])

    match_id = f"match_{buyer['buyer_id']}_{deal['deal_id']}"

    return {
        "match_id": match_id,
        "buyer_id": buyer["buyer_id"],
        "buyer_name": buyer.get("buyer_name", ""),
        "deal_id": deal["deal_id"],
        "deal_url": deal.get("url", ""),
        "deal_title": deal.get("title", ""),
        "deal_source": deal.get("source", ""),
        "deal_location": f"{deal.get('location_city', '')}, {deal.get('location_state', '')}",
        "deal_industry": deal_industry,
        "deal_asking_price": asking_price,
        "deal_asking_price_raw": deal.get("asking_price_raw", ""),
        "deal_revenue_raw": deal.get("annual_revenue_raw", ""),
        "deal_cash_flow_raw": deal.get("cash_flow_raw", ""),
        "total_score": round(total, 1),
        "max_possible_score": max_total,
        "score_pct": score_pct,
        "grade": grade,
        "score_breakdown": scores,
        "hard_stops": hard_stops,
        "soft_flags": soft_flags,
        "match_summary": match_summary,
        "email_draft": None,  # Populated by generate_emails.py
        "matched_at": datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Match scraped deals to buyer criteria")
    parser.add_argument("--listings", default=".tmp/all_listings.json")
    parser.add_argument("--buyers", default=os.getenv("BUYERS_JSON_PATH", ".tmp/buyers.json"))
    parser.add_argument("--out", default=".tmp/matches.json")
    parser.add_argument(
        "--min-score",
        type=float,
        default=float(os.getenv("MIN_MATCH_SCORE", "40")),
        help="Minimum score percentage to include in output (0-100)"
    )
    args = parser.parse_args()

    listings_path = Path(args.listings)
    buyers_path = Path(args.buyers)
    out_path = Path(args.out)

    if not listings_path.exists():
        print(f"[ERROR] Listings file not found: {listings_path}")
        return
    if not buyers_path.exists():
        print(f"[ERROR] Buyers file not found: {buyers_path}")
        return

    listings = json.loads(listings_path.read_text())
    buyers = json.loads(buyers_path.read_text())
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Matching {len(listings)} listings against {len(buyers)} buyer(s)")
    print(f"[INFO] Minimum score threshold: {args.min_score}%\n")

    all_matches = []
    disqualified_count = 0

    for buyer in buyers:
        buyer_matches = []
        for deal in listings:
            result = score_deal_for_buyer(deal, buyer)
            if result is None:
                disqualified_count += 1
                continue
            if result["score_pct"] >= args.min_score:
                buyer_matches.append(result)

        # Sort by score descending
        buyer_matches.sort(key=lambda x: x["score_pct"], reverse=True)
        all_matches.extend(buyer_matches)

        a_count = sum(1 for m in buyer_matches if m["grade"] == "A")
        b_count = sum(1 for m in buyer_matches if m["grade"] == "B")
        c_count = sum(1 for m in buyer_matches if m["grade"] == "C")
        print(
            f"[{buyer.get('buyer_name', buyer['buyer_id'])}] "
            f"{len(buyer_matches)} matches — A:{a_count} B:{b_count} C:{c_count}"
        )

    print(f"\n[INFO] Total matches: {len(all_matches)} | Disqualified: {disqualified_count}")
    out_path.write_text(json.dumps(all_matches, indent=2))
    print(f"[DONE] Wrote matches to {out_path}")


if __name__ == "__main__":
    main()
