# The Read — weekly runbook

A 100 Yards LinkedIn carousel that critiques one early-stage (seed–Series A) AI
company's homepage marketing. Runs manually on this MacBook, ~10 min start to posted.

---

## Every week

**1. Open Terminal and go to the project:**
```
cd /Users/joshmait/Desktop/Claude/pavilion/funded-and-found-out
```

**2. Find this week's companies (~3 min):**
```
.venv/bin/python scripts/run_pipeline.py
```
It scans your newsletters, verifies each company is really who the news says,
grades them, and prints a **Final lineup** of ~5 seed–Series A AI companies with
their C/L/E/A/R grades.

**3. Pick ONE** — the one you'd most want as a client, or whose homepage has the
most to fix — and generate the post (use the exact name from the lineup):
```
.venv/bin/python scripts/make_post.py "Company Name"
```

**4. Review.** It prints a folder path. Open the PDF and eyeball the numbers
(funding amount, etc.) — that's the only thing worth double-checking:
```
open output/posts/<date>-<company>/post.pdf
```

**5. Post on LinkedIn (desktop):**
- Start a post → **document icon** ("Add a document")
- Upload **post.pdf** from that folder
- Document **title** = the title line in `caption.txt`
- Paste the **caption** (rest of `caption.txt`) into the post body
- Post. LinkedIn auto-renders the PDF as a swipeable carousel.

---

## If it's been more than ~2 weeks since you last ran it

Gmail tokens expire after idle time. If step 2 says `invalid_grant` or
"Token expired/revoked", re-auth once (a browser opens for each):
```
.venv/bin/python scripts/auth_gmail.py personal      # pick josh.mait@gmail.com
.venv/bin/python scripts/auth_gmail.py 100yards      # pick joshmait@100yardstogo.com
```
Then re-run step 2. (Running weekly keeps the tokens warm, so this is rare.)

## If you want a post without waiting on Gmail

The newsletter scan is only how candidates get *found*. You can hand the pipeline
a list instead and everything downstream — the too-big screen, identity check,
screenshot, and grades — runs exactly the same:
```
.venv/bin/python scripts/run_pipeline.py --seed data/seeds/YYYY-MM-DD.json
```
The seed file is a JSON list; each entry needs `company_name`, `website_url`,
`news_hook`, `description`, `news_url`. Seed 6-7 candidates, not 5 — the pipeline
fills 5 slots and drops anything that fails identity or won't render, and below
5 it bails to the curation-email path (which needs the same Gmail token).
See `data/seeds/2026-09-01.json` for a worked example.

---

## Notes

- Uses the shared Anthropic key (in `.env`). If it ever says "credit too low,"
  top up or swap the key.
- You can post a different company from the same run any time:
  `.venv/bin/python scripts/make_post.py "Other Company"`
- To re-render a deck after hand-editing its HTML:
  `.venv/bin/python scripts/make_post.py "Company" --render-only`
