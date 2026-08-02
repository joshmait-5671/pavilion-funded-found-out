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

Gmail tokens expire after idle time. If step 2 says "Token expired/revoked",
re-auth once (a browser opens for each):
```
.venv/bin/python scripts/auth_gmail.py personal      # pick josh.mait@gmail.com
.venv/bin/python scripts/auth_gmail.py 100yards      # pick joshmait@100yardstogo.com
```
Then re-run step 2. (Running weekly keeps the tokens warm, so this is rare.)

---

## Notes

- Uses the shared Anthropic key (in `.env`). If it ever says "credit too low,"
  top up or swap the key.
- You can post a different company from the same run any time:
  `.venv/bin/python scripts/make_post.py "Other Company"`
- To re-render a deck after hand-editing its HTML:
  `.venv/bin/python scripts/make_post.py "Company" --render-only`
