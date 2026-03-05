# Social Media Cross-Poster — SOP

## What This Does

Generates AI-powered content (text, image, video, music) from a topic idea and
cross-posts to Instagram, Facebook, and email newsletter. Ideas are seeded by
real trending data from Google Trends, Reddit, and RSS feeds. Past engagement
data feeds back into idea generation to improve over time.

---

## First-Time Setup (do once)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Also install ffmpeg (for video creation):

```bash
# Windows (PowerShell)
winget install ffmpeg

# Or download from: https://ffmpeg.org/download.html
# After install, verify: ffmpeg -version
```

### 2. Get your API keys

| Key | Where to get | Cost |
|-----|-------------|------|
| `ANTHROPIC_API_KEY` | console.anthropic.com | Pay per use (~$0.01/post) |
| `HF_TOKEN` | huggingface.co → Settings → Access Tokens | Free |
| Meta App credentials | developers.facebook.com (steps below) | Free |
| Gmail App Password | myaccount.google.com → Security → App passwords | Free |

### 3. Create Meta Developer App (Facebook + Instagram)

You need a Facebook Developer App to post via API.

1. Go to: https://developers.facebook.com/apps/
2. Click **Create App** → select **Business** type → name it anything
3. In your app dashboard → **Add Products**:
   - Add **Instagram Graph API**
   - Add **Pages API**
4. Go to **Settings → Basic** → copy **App ID** and **App Secret**
5. Go to **Facebook Login → Settings** → under "Valid OAuth Redirect URIs", add:
   ```
   https://localhost/callback
   ```
6. Save changes

Make sure your Instagram account is a **Business** or **Creator** account (not Personal),
and that it is connected to your Facebook Page:
- Instagram → Settings → Account → Switch to Professional Account
- Then: Settings → Linked accounts → Facebook → connect your Page

### 4. Add keys to `.env`

Open `.env` and fill in:

```
ANTHROPIC_API_KEY=sk-ant-...your key...
HF_TOKEN=hf_...your token...
META_APP_ID=...your app id...
META_APP_SECRET=...your app secret...
SMTP_USER=your@gmail.com
SMTP_PASSWORD=...your 16-char app password...
EMAIL_FROM_ADDRESS=your@gmail.com
SOCIAL_NICHE=business acquisitions
SOCIAL_BRAND_NAME=Valar Brokers
```

### 5. Run Meta OAuth (get tokens)

```bash
python tools/run_social.py --refresh-token
```

This opens a browser → you authorize → paste the redirect URL back → tokens
are saved to `.env` automatically.

### 6. Verify everything works

```bash
python tools/run_social.py --check-config
```

All checks should show OK (or NOT SET for optional ones).

---

## Daily Workflow

### Step 1 — Generate ideas

```bash
python tools/run_social.py --ideas
```

The system:
1. Pulls trending topics from Google Trends, Reddit, and RSS
2. Uses your past top-performing posts as context
3. Suggests 5 content ideas with titles and hooks
4. You pick one (or type your own)

The approved idea is saved with an ID number.

### Step 2 — Create content

```bash
python tools/run_social.py --create --idea-id 3
```

Generates:
- **Instagram caption** + hashtags
- **Facebook post** with CTA
- **Email article** with subject line
- **1080×1080 PNG image** (via HuggingFace FLUX)
- **Background music** WAV (via HuggingFace MusicGen)
- **30-second MP4 video** slideshow (via ffmpeg)

Text-only mode (if you want to skip media):
```bash
python tools/run_social.py --create --idea-id 3 --skip-image
```

### Step 3 — Review content

Check the generated files before posting:
- Images: `.tmp/social/images/`
- Videos: `.tmp/social/video/`
- Audio: `.tmp/social/audio/`

Review captions:
```bash
python tools/run_social.py --list-posts
```

### Step 4 — Post

```bash
python tools/run_social.py --post --post-id 7
```

Posts to all three platforms simultaneously. If one platform fails, the others
still go out.

Post to specific platforms only:
```bash
python tools/run_social.py --post --post-id 7 --platforms instagram facebook
python tools/run_social.py --post --post-id 7 --platforms email
```

### Step 5 — Track engagement (weekly)

```bash
python tools/run_social.py --analytics
python tools/run_social.py --report
```

Fetches likes, comments, saves, reach from Meta API.
Stores in SQLite. Top posts automatically seed the next idea session.

---

## Email Subscriber Management

```bash
# Add one subscriber
python tools/run_social.py --add-subscriber email@example.com
python tools/run_social.py --add-subscriber email@example.com --name "Jane Doe"

# Remove (unsubscribe)
python tools/run_social.py --remove-subscriber email@example.com

# Bulk import from CSV
# CSV format — header required: email,first_name,last_name
python tools/run_social.py --import-subscribers /path/to/subscribers.csv

# View list
python tools/run_social.py --list-subscribers
```

---

## File Locations

| Path | Contents |
|------|---------|
| `.env` | All API keys and config |
| `.tmp/social.db` | SQLite database (ideas, posts, subscribers, engagement) |
| `.tmp/social/images/` | Generated PNG images |
| `.tmp/social/audio/` | Generated WAV audio files |
| `.tmp/social/video/` | Generated MP4 video slideshows |
| `tools/run_social.py` | CLI entry point |
| `tools/social/` | All module code |

---

## Troubleshooting

### "Image generation returns None"
- Check `HF_TOKEN` is set in `.env`
- HuggingFace free tier has rate limits — wait a few minutes and retry
- Model may be cold-starting (503 error) — the retry logic waits up to 90s

### "Instagram posting fails"
- Make sure Instagram is a Business/Creator account (not Personal)
- Make sure Instagram is connected to your Facebook Page
- Run `--refresh-token` again to re-authorize
- Instagram requires an image or video — text-only posts are not supported

### "Gmail authentication failed"
- Must use an **App Password**, not your regular login password
- Setup: myaccount.google.com → Security → App passwords
- Make sure 2-factor auth is enabled on your Google account first

### "ffmpeg not found"
- Install ffmpeg: `winget install ffmpeg`
- Restart your terminal after installation
- Video will be skipped gracefully if ffmpeg is absent — other content still posts

### "Meta API token expired"
- Run: `python tools/run_social.py --refresh-token`
- If you used a Page Access Token (the default), it never expires
- If you see expiry warnings, your token may be a User token — re-run OAuth

---

## Architecture

```
tools/
  run_social.py           — CLI entry point (argparse)
  social/
    __init__.py           — Orchestration: run_content_creation(), run_post()
    db.py                 — SQLite schema + all queries
    utils.py              — Shared paths, retry(), format_table()
    trends.py             — Google Trends + Reddit + RSS + AI brainstorm
    content_text.py       — Claude API: captions, articles, hashtags
    content_image.py      — HuggingFace FLUX.1-schnell: PNG generation
    content_audio.py      — HuggingFace MusicGen: background music
    content_video.py      — ffmpeg: image slideshow → MP4
    poster_meta.py        — Meta Graph API: Instagram + Facebook
    poster_email.py       — smtplib: Gmail newsletter send
    analytics.py          — Meta Insights API → engagement → SQLite
    token_manager.py      — Meta OAuth flow + token expiry check
    subscribers.py        — Email list add/remove/import/export
```

### Data flow

```
--ideas
  pytrends + Reddit + RSS → trend_data
  top_posts (from DB)     → engagement context
  Claude API              → 5 content ideas
  User picks one          → saved to ideas table (status: approved)

--create --idea-id N
  ideas[N]                → idea dict
  Claude API              → caption_instagram, caption_facebook,
                            hashtags, email_subject, article_html
  HuggingFace FLUX        → 1080x1080 PNG image
  HuggingFace MusicGen    → WAV background music (optional)
  ffmpeg                  → MP4 slideshow (image + music)
  → saved to posts table (status: draft → ready)

--post --post-id M
  posts[M]                → caption, image, video, article
  Meta Graph API          → Instagram image/reel post
  Meta Graph API          → Facebook photo/video post
  smtplib                 → email to all active subscribers
  → saved to platform_posts table (status: posted)

--analytics
  platform_posts (posted) → Meta Insights API → engagement snapshots
  → saved to engagement table

--ideas (next time)
  engagement table        → top posts → seed next idea session
```
