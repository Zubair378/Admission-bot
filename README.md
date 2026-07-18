# Admissions Email Auto-Reply System

**RAG-powered admissions assistant for Pakistani educational institutions.**

Reads incoming Gmail admissions inquiries, answers from an approved knowledge base (prospectus, fee structure), and escalates anything uncertain to human staff via a `SPECIAL` Gmail label — built to never fabricate an answer it can't back up.
<img width="941" height="509" alt="image" src="https://github.com/user-attachments/assets/3899b33b-25d7-46d1-a687-8f445ce00931" />


<img width="724" height="463" alt="image" src="https://github.com/user-attachments/assets/b5c4422a-31e6-4caf-80d4-996824da36bf" />

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Google Cloud & API Setup](#google-cloud--api-setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)

---

## Overview

Every private school, college, and university in Pakistan faces the same admissions-season crisis: 50–200 repetitive email inquiries a day (fees, eligibility, deadlines), handled manually by a 2–5 person admissions team. 70–85% of these emails are answerable from documents the institution already has (prospectus, fee structure).

This system:
- Answers admissions questions **only** from an approved knowledge base — no hallucinated fees, dates, or policies
- Watches a Gmail inbox and auto-replies to confident matches
- Routes anything uncertain to a `SPECIAL` Gmail label, left unread for staff — never guesses
- Logs every decision (subject, sender, similarity score, outcome) to Google Sheets for admin visibility
- Runs entirely on a free tier — local embeddings, no cost for the prototype

## Key Features

| | |
|---|---|
| 🧠 **Grounded answers** | RAG over institution documents with a calibrated similarity threshold — if nothing relevant is retrieved, it doesn't guess |
| 🛡️ **Two-layer safety** | (1) Similarity threshold filters irrelevant emails before generation even happens. (2) The LLM is instructed to output an `INSUFFICIENT_CONTEXT` marker if it can't confidently answer from the retrieved context, even when similarity scored high — caught and routed to SPECIAL |
| 📧 **Real Gmail integration** | Polls the inbox every 60 seconds, sends genuine replies, applies a `SPECIAL` label to anything uncertain |
| 📋 **Admin logging** | Every decision logged to Google Sheets — timestamp, subject, sender, similarity, decision, whether a reply was sent |
| 💸 **Zero-cost prototype** | Embeddings run locally (`sentence-transformers`, free forever); only reply generation uses a free-tier API call |
| 🔁 **No duplicate processing** | Emails already labeled `SPECIAL` are skipped on future polling cycles instead of being re-scored and re-logged endlessly |

## Architecture

```
New email arrives (Gmail inbox, polled every 60s)
        │
        ▼
Extract text → embed (local model) → query Chroma vector store
        │
        ▼
Top similarity score ≥ threshold (0.40)?
        │
   ┌────┴────┐
  Yes         No
   │           │
   ▼           ▼
Generate reply   Apply SPECIAL label
(Gemini API)     Leave unread
   │             Log to Sheets
   ▼
Reply says "INSUFFICIENT_CONTEXT"?
   │
 ┌─┴─┐
Yes   No
 │     │
 ▼     ▼
SPECIAL   Send reply via Gmail
label     Mark as read
Log       Log to Sheets
```

**Core design principle:** the LLM never sends an email or applies a label directly. Python evaluates the similarity score, calls the LLM for text generation only, checks its output for a confidence marker, and only then executes the actual Gmail/Sheets action. This keeps every failure mode recoverable rather than customer-facing.

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.13 |
| Email | Gmail API (OAuth 2.0, `gmail.modify` scope) |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) — local, free, no API cost |
| Vector store | ChromaDB (local, persistent, cosine similarity) |
| LLM (reply generation) | Gemini API (`gemini-flash-lite-latest`) |
| Admin log | Google Sheets API (via `gspread`, service account) |
| Document parsing | `pypdf` |

## Project Structure

```
admission-bot/
├── data/
│   ├── Prospectus.pdf          # Institution prospectus (knowledge base source)
│   └── fee_structure.pdf       # Fee structure document (knowledge base source)
├── chroma_db/                  # Generated vector store (not committed — see .gitignore)
├── ingest.py                   # Builds the knowledge base: chunk → embed → store
├── test_retrieval.py           # Manual retrieval testing tool (not part of the live bot)
├── bot.py                      # The live bot: Gmail watcher + RAG + auto-reply/SPECIAL logic
├── test_gmail-auth.py          # One-off script to confirm Gmail OAuth is working
├── .env.example                # Template for required environment variables
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.11+
- A Google account for testing (recommend a dedicated test Gmail account, not your personal one)
- A [Gemini API key](https://aistudio.google.com/apikey) (free tier)

### Installation

```bash
git clone https://github.com/Zubair378/Admission-bot.git
cd Admission-bot
python -m pip install sentence-transformers chromadb pypdf python-dotenv google-generativeai google-auth-oauthlib google-auth-httplib2 google-api-python-client gspread
```

## Google Cloud & API Setup

This system needs two things enabled on a Google Cloud project: **Gmail API access** (OAuth) and a **Gemini API key**. Follow these in order.

### 1. Create a Google Cloud project

- Go to [console.cloud.google.com](https://console.cloud.google.com/)
- Click the project dropdown → **New Project** → give it a name → **Create**

### 2. Enable the Gmail API

- In the search bar, type **Gmail API** → select it → click **Enable**
- Docs: [developers.google.com/gmail/api](https://developers.google.com/gmail/api)

### 3. Configure the OAuth consent screen

- Left sidebar → **APIs & Services** → **Google Auth Platform** (formerly "OAuth consent screen")
- Click **Get started**, fill in app name, support email, choose **External**, add developer contact email
- Under **Audience** → **Test users**, add the Gmail address the bot will actually monitor/send from

### 4. Create OAuth credentials

- Left sidebar → **APIs & Services** → **Clients** → **Create Client**
- Application type: **Desktop app** → name it → **Create**
- Download the JSON file, save it in the project root as `credentials.json`

### 5. Get a Gemini API key

- Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- Click **Create API key**, select your Google Cloud project
- Copy the key — do not commit it. It goes in your `.env` file (see below)
- Pricing/free-tier details: [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing)

### 6. Set up Google Sheets logging

- Create a new Google Sheet, add header row: `Timestamp | Subject | Sender | Similarity | Decision | Reply Sent`
- Create a Google Cloud **service account** (APIs & Services → Credentials → Create Credentials → Service Account), download its JSON key as `service_account.json`
- Share the Sheet with the service account's email address (found inside `service_account.json`), Editor access
- Copy the Sheet ID from its URL (`.../d/THIS_PART/edit`) into `.env`

### 7. First run — Gmail authorization

```bash
python test_gmail-auth.py
```

This opens a browser window — log in with the **test Gmail account** you added in step 3, and click Allow. This creates `token.json`, which the bot reuses on future runs without asking you to log in again.

## Configuration

Copy `.env.example` to `.env` and fill in:

```
GEMINI_API_KEY=your_gemini_api_key_here
SHEET_ID=your_google_sheet_id_here
```

Required local files (never committed — see `.gitignore`):
- `credentials.json` — OAuth client credentials (step 4 above)
- `token.json` — generated automatically after first Gmail login
- `service_account.json` — Sheets service account key (step 6 above)

## Usage

### 1. Build the knowledge base (run once, or whenever source documents change)

```bash
python ingest.py
```

Chunks and embeds `data/Prospectus.pdf` and `data/fee_structure.pdf`, stores them in a local ChromaDB collection.

### 2. (Optional) Test retrieval manually

```bash
python test_retrieval.py
```

Runs a set of sample questions against the knowledge base and prints similarity scores and matched context — useful for calibrating the confidence threshold before running the live bot.

### 3. Run the live bot

```bash
python bot.py
```

Polls the inbox every 60 seconds. For each unread email: retrieves relevant context, checks the similarity threshold, generates a reply if confident, applies the `SPECIAL` label if not, and logs the outcome to Google Sheets. Press `Ctrl+C` to stop.

## Using This for a Different Institution

This system isn't hardcoded to Foundation University Islamabad — the knowledge base is just whatever PDFs sit in the `data/` folder. To reuse it for a different school, college, or university:

1. **Replace the documents** — remove the existing PDFs from `data/` and add the new institution's prospectus, fee structure, and any other admissions documents (eligibility criteria, scholarship policy, entrance test schedule, etc.)
2. **Update the filenames in `ingest.py`** — the `pdf_files` list near the top of the script must list the exact filenames of whatever you placed in `data/` (matching capitalization — Windows ignores case, but Git and other operating systems don't)
3. **Update the institution name** — in `bot.py`, the prompt inside `generate_reply()` currently says *"You are an admissions assistant for Foundation University Islamabad."* Change this to the new institution's name, and update the reply signature if one is added later
4. **Rebuild the knowledge base** — delete the old `chroma_db/` folder and re-run `python ingest.py` to embed the new documents
5. **Re-test and recalibrate the threshold** — every institution's documents will produce a different score distribution (see `test_retrieval.py`). Run a set of real sample questions, check the similarity scores, and adjust `THRESHOLD` in `bot.py` if needed, following the same calibration approach used in this project (favor a stricter/higher threshold — zero false positives over maximum coverage)
6. **Re-authorize Gmail** — if switching to a different institution's actual Gmail inbox, delete `token.json` and re-run `python test_gmail-auth.py` to log in with the correct account

No other code changes are required — the retrieval, threshold logic, SPECIAL routing, and Sheets logging all work identically regardless of which documents are loaded.

## Known Limitations

Documented honestly:

- **Local-only execution** — the bot only runs while `bot.py` is actively running on a machine with internet access. It does not run 24/7 unattended; production deployment to an always-on server (e.g. Railway, Render, or a small VPS) is a planned next step, not yet implemented.
- **PDF table extraction** — fee and program tables in source PDFs don't always extract cleanly as plain text (a known, common limitation of PDF text extraction). Some fields (e.g. a complete program list) required a supplementary curated text file rather than relying on raw PDF extraction alone.
- **No dedicated spam filtering** — the system currently relies solely on semantic similarity to filter irrelevant emails. Testing showed at least one false positive (a newsletter with topically-adjacent vocabulary scoring above threshold). A basic sender-pattern filter is a planned refinement.
- **Local embeddings, smaller model** — `all-MiniLM-L6-v2` is free and fast but less precise than larger hosted embedding models; occasional topically-plausible-but-incorrect matches are possible on ambiguous queries.
- **Single free-tier Gemini API key** — subject to daily rate limits on the free tier; production use at full volume (200 emails/day) would need a paid tier or quota increase (see cost breakdown for pricing).

## Roadmap

- [ ] Deploy to an always-on host (Railway/Render) for 24/7 operation
- [ ] Add sender/subject-based spam pre-filtering
- [ ] Supplement PDF sources with curated text documents for table-heavy sections
- [ ] Multi-institution support (separate knowledge base per client)
- [ ] Basic authentication/rate limiting if ever exposed beyond a single Gmail inbox

---

Built as part of an AI/ML Internship Program project — Admissions Email Overload (Problem 00).
