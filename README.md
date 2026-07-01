# SEO Audit Tool

A full-stack SEO auditing platform built with Flask + Socket.IO. Crawls a
website and produces a live, streaming audit covering on-page SEO, technical
SEO, mobile-friendliness, PageSpeed performance, backlinks, structured data,
and social preview cards — plus AI-generated recommendations and an SEO
chatbot (Gemini / Groq / OpenRouter), and PDF/CSV export of results.

## Features
- Real-time crawl progress via WebSockets (Flask-SocketIO)
- On-page, technical, and mobile SEO scoring
- Google PageSpeed Insights integration
- Backlink and internal link analysis
- Structured data (schema.org) validation
- AI-powered recommendations and chatbot assistant
- Social share preview generation
- Historical audit tracking / progress comparison between scans
- Exportable audit reports

## Tech stack
Python, Flask, Flask-SocketIO, PostgreSQL, BeautifulSoup, vanilla JS/HTML/CSS
frontend, external APIs (Google PageSpeed, Gemini, Groq, OpenRouter).

## Local setup
```bash
git clone <your-repo-url>
cd SEO_TOOL
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your API keys + DATABASE_URL
python app.py
```
Visit http://localhost:5000

You'll need a PostgreSQL database (a free one works fine, e.g. from Render,
Railway, Supabase, or Neon) and to set `DATABASE_URL` in `.env`. API keys for
PageSpeed/Gemini/Groq/OpenRouter are optional but needed for those specific
features — the app will still run without them.

## Deploying so you can put a live link on your resume

The easiest free/low-cost options for a Flask + Socket.IO + Postgres app:

### Option A: Render.com (recommended, has a free Postgres tier)
1. Push this project to a **public or private GitHub repo** (the `.gitignore`
   already excludes `.env` and the local `.db` file — never commit real keys).
2. On Render: New → PostgreSQL → create a free database, copy its
   "Internal Database URL".
3. New → Web Service → connect your repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn --worker-class eventlet -w 1 app:app`
4. In the service's Environment tab, add: `DATABASE_URL`,
   `GOOGLE_PAGESPEED_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`,
   `OPENROUTER_API_KEY`, `GROQ_CHATBOT_KEY`, `SECRET_KEY` (any random string).
5. Deploy. Render gives you a URL like `https://your-app.onrender.com` —
   that's your resume link.

### Option B: Railway.app
Same idea — connect the GitHub repo, add a Postgres plugin, set the same env
vars, Railway auto-detects the `Procfile`.

### Option C: PythonAnywhere
Good free tier for Flask, but WebSocket (Socket.IO) support is limited on
the free plan — Render/Railway are a better fit for this project specifically
because of the live crawl progress feature.

> ⚠️ Free-tier web services often "sleep" after inactivity and take ~30s to
> wake on the first request — worth mentioning to anyone testing your link,
> or worth a small note on your resume/portfolio page.

## Security note
This repo previously had a `.env` file with live API keys checked in. If you
ever pushed this to GitHub or shared the zip before, **rotate/regenerate**
those keys (PageSpeed, Gemini, Groq, OpenRouter) now, since the old ones
should be treated as compromised.
