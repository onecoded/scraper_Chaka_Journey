"""
content_text.py — AI-powered text content generation via Claude API.

Generates:
  - Instagram captions (≤2200 chars + hashtags)
  - Facebook posts (conversational, with CTA link)
  - Email newsletter (subject line + full HTML article)

Falls back to structured templates if ANTHROPIC_API_KEY is not set or API fails.
"""

import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SOCIAL_NICHE = os.getenv("SOCIAL_NICHE", "business acquisitions")
BRAND_NAME = os.getenv("SOCIAL_BRAND_NAME", os.getenv("BROKER_COMPANY", "Valar Brokers"))
WEBSITE_URL = os.getenv("SOCIAL_WEBSITE_URL", "")
CTA = os.getenv("SOCIAL_CTA", "")
CONTENT_MODEL = os.getenv("EMAIL_MODEL", "claude-haiku-4-5-20251001")


# ── TEMPLATE FALLBACKS ────────────────────────────────────────────────────────

def _fallback_caption_instagram(idea: dict) -> str:
    title = idea.get("title", "")
    hook = idea.get("hook", "")
    cta = f"\n\n{CTA}" if CTA else ""
    return f"{hook or title}\n\nKey insights on {title}.\n\nWhat are your thoughts? Drop a comment below.{cta}"


def _fallback_caption_facebook(idea: dict) -> str:
    title = idea.get("title", "")
    hook = idea.get("hook", "")
    cta_line = f"\n\n{CTA}" if CTA else ""
    url_line = f"\n\n{WEBSITE_URL}" if WEBSITE_URL else ""
    return f"{hook or title}\n\nHere's what we're seeing in the market around {title}.{cta_line}{url_line}"


def _fallback_hashtags(idea: dict) -> str:
    niche = SOCIAL_NICHE.lower().replace(" ", "")
    title_words = idea.get("title", "").lower().split()
    base = ["#business", "#entrepreneur", "#smallbusiness", "#acquisition",
            f"#{niche}", "#businessgrowth", "#investing", "#dealflow"]
    extra = [f"#{w}" for w in title_words if len(w) > 4][:5]
    return " ".join(list(dict.fromkeys(base + extra)))  # deduplicated


def _fallback_article(idea: dict) -> tuple:
    title = idea.get("title", "Content Update")
    hook = idea.get("hook", "")
    subject = f"{title} | {BRAND_NAME}"
    body = f"""
<h2>{title}</h2>
<p>{hook or f"Here's what you need to know about {title}."}</p>
<p>This topic is increasingly relevant for business owners and entrepreneurs
in the {SOCIAL_NICHE} space. Understanding the key drivers behind these trends
can help you make smarter decisions about growth, exits, and acquisitions.</p>
<h3>What This Means for You</h3>
<p>Whether you're building to sell or looking to acquire, staying informed
is the first step. Reach out to discuss how these trends apply to your situation.</p>
{f'<p><a href="{WEBSITE_URL}">{CTA or "Learn more"}</a></p>' if WEBSITE_URL else ""}
"""
    return subject, body.strip()


# ── CLAUDE API ────────────────────────────────────────────────────────────────

def _call_claude(prompt: str, max_tokens: int = 1000) -> str:
    """Call Claude API. Returns response text or empty string on failure."""
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "sk-ant-REPLACE_ME":
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=CONTENT_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"  [WARN] Claude API error: {e}")
        return ""


# ── GENERATORS ────────────────────────────────────────────────────────────────

def generate_caption(idea: dict, platform: str) -> str:
    """
    Generate a platform-appropriate caption for the given idea.

    Args:
        idea: dict with keys: title, hook, niche (optional)
        platform: "instagram" or "facebook"

    Returns:
        Caption string.
    """
    title = idea.get("title", "")
    hook = idea.get("hook", "")
    niche = idea.get("niche") or SOCIAL_NICHE
    brand = BRAND_NAME
    cta = CTA or f"Follow {brand} for more insights."

    if platform == "instagram":
        max_chars = 2200
        tone_note = "engaging, concise, ends with a question to drive comments"
        format_note = "Do NOT include hashtags in the caption body — they will be added separately."
    else:  # facebook
        max_chars = 1500
        tone_note = "conversational, slightly longer, ends with a clear call to action"
        format_note = f"Include a CTA. If relevant, mention: {cta}"

    prompt = f"""Write a {platform} post caption for a {niche} brand called "{brand}".

Topic: {title}
Hook/Angle: {hook or title}
Tone: {tone_note}
Max length: {max_chars} characters
{format_note}

Write only the caption text. No intro, no explanation."""

    result = _call_claude(prompt, max_tokens=600)
    if result:
        return result

    # Template fallback
    if platform == "instagram":
        return _fallback_caption_instagram(idea)
    return _fallback_caption_facebook(idea)


def generate_hashtags(idea: dict, count: int = 20) -> str:
    """
    Generate Instagram hashtags for the idea.

    Returns:
        Space-separated hashtag string (e.g. "#business #growth #acquisition").
    """
    title = idea.get("title", "")
    niche = idea.get("niche") or SOCIAL_NICHE

    prompt = f"""Generate {count} relevant Instagram hashtags for this post topic:

Topic: {title}
Niche: {niche}

Rules:
- Mix broad (#business, #entrepreneur) and niche-specific tags
- Include some mid-size tags (50k–500k posts) for better reach
- No spaces within hashtags
- Format: one line of space-separated hashtags starting with #

Return only the hashtag line."""

    result = _call_claude(prompt, max_tokens=200)
    if result and result.startswith("#"):
        # Ensure we have exactly the right count
        tags = result.split()[:count]
        return " ".join(tags)

    return _fallback_hashtags(idea)


def generate_article(idea: dict, word_count: int = 500) -> tuple:
    """
    Generate a newsletter article for the idea.

    Returns:
        Tuple of (subject_line, html_body_string).
    """
    title = idea.get("title", "")
    hook = idea.get("hook", "")
    niche = idea.get("niche") or SOCIAL_NICHE
    brand = BRAND_NAME
    cta = CTA or ""
    url = WEBSITE_URL or ""

    prompt = f"""Write a short email newsletter article for a {niche} audience.
Brand: {brand}
Topic: {title}
Angle: {hook or title}
Target word count: {word_count} words

Format your response as:
SUBJECT: [compelling subject line, max 60 chars]
---
[Article body in HTML using only: <h2>, <h3>, <p>, <ul>, <li>, <strong>, <a> tags]
{"Include a CTA linking to: " + url if url else ""}

Write professional, valuable content. No fluff. No placeholder text."""

    result = _call_claude(prompt, max_tokens=1200)
    if result and "SUBJECT:" in result:
        try:
            lines = result.split("---", 1)
            subject_line = lines[0].replace("SUBJECT:", "").strip()
            html_body = lines[1].strip() if len(lines) > 1 else lines[0]
            if subject_line and html_body:
                return subject_line, html_body
        except Exception:
            pass

    return _fallback_article(idea)


def generate_all_text(idea: dict) -> dict:
    """
    Orchestrate all text generation for a post.

    Returns dict with keys:
        caption_instagram, caption_facebook, hashtags,
        email_subject, article_html

    Any individual failure returns an empty string for that key.
    """
    print("  [TEXT] Generating Instagram caption...")
    try:
        caption_ig = generate_caption(idea, "instagram")
    except Exception as e:
        print(f"  [WARN] Instagram caption failed: {e}")
        caption_ig = _fallback_caption_instagram(idea)

    print("  [TEXT] Generating Facebook post...")
    try:
        caption_fb = generate_caption(idea, "facebook")
    except Exception as e:
        print(f"  [WARN] Facebook caption failed: {e}")
        caption_fb = _fallback_caption_facebook(idea)

    print("  [TEXT] Generating hashtags...")
    try:
        hashtags = generate_hashtags(idea)
    except Exception as e:
        print(f"  [WARN] Hashtag generation failed: {e}")
        hashtags = _fallback_hashtags(idea)

    print("  [TEXT] Generating email article...")
    try:
        email_subject, article_html = generate_article(idea)
    except Exception as e:
        print(f"  [WARN] Article generation failed: {e}")
        email_subject, article_html = _fallback_article(idea)

    using_ai = bool(ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != "sk-ant-REPLACE_ME")
    print(f"  [TEXT] Done ({'AI' if using_ai else 'template fallback'})")

    return {
        "caption_instagram": caption_ig,
        "caption_facebook": caption_fb,
        "hashtags": hashtags,
        "email_subject": email_subject,
        "article_html": article_html,
    }
