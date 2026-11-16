# Project Specification: Company-Aware Python Interview IDE (working title: **PrepForge**)

**Author:** Mukil Anand KS
**Goal:** GitHub and resume portfolio project (AI engineering plus full-stack)
**Build style:** AI-assisted ("vibecoded"), with architecture decisions and verification owned by the author
**Time budget:** about 2 hours/day. Week 1 = working core. Week 2 = extras.

---

## 1. Overview

A web app where a user picks a **company**, **difficulty**, **number of questions**, and a **time limit**. The app uses **Gemini** to generate Python interview questions in that company's style, together with test cases and a reference solution. Before any question is shown, the **reference solution is run against the test cases in the browser (Pyodide)**. Questions that fail this check are discarded and replaced. The user solves each question in a Monaco editor, code runs safely in the browser, and the session ends with a score and (later) an AI-written performance summary.

**One-line pitch (for README and resume):**
> A company-aware Python coding IDE where Gemini generates interview questions and test cases, and every question is verified in-browser with a reference solution before it is shown.

**Headline engineering idea:** *LLM output cannot be trusted, so it is verified before use.*

---

## 2. Goals and Non-Goals

### Goals
- Show LLM integration with **structured JSON output** and a **verification layer**.
- Show full-stack skills: Django, auth, database design, deployment.
- Run user code **without any server-side code execution risk** (Pyodide in a Web Worker).
- Produce a live demo link plus a strong README.

### Non-Goals (version 1)
- Languages other than Python.
- AI hints.
- Adaptive difficulty.
- Real-time multiplayer or leaderboards.
- Dark/light theme toggle and a progress bar across questions (explicitly excluded).
- Claiming questions are real leaked interview questions. They are only **"inspired by"** a company's style.

---

## 3. Scope by Phase

### Phase 1: Week 1 (must ship)
| # | Feature |
|---|---------|
| 1 | Django project, register / login / logout |
| 2 | Settings page: company (fixed list of 5-8), difficulty, question count, timer |
| 3 | Gemini question generation (JSON: question, test cases, reference solution) |
| 4 | Monaco editor and Pyodide in a Web Worker with timeout |
| 5 | **Verification step** (reference solution vs. test cases, discard bad, retry up to 3) |
| 6 | Auto-submit timer (default per difficulty, custom override) |
| 7 | Partial-credit scoring and results page (score and per-question breakdown) |
| 8 | Questions stored in the Django database |
| 9 | Deploy to Render |
| 10 | README, architecture diagram, screenshots |

### Phase 2: Week 2 (after the core works)
| # | Feature |
|---|---------|
| 1 | **Turso question bank** (serve from bank first, Gemini as fallback and background refill) |
| 2 | **AI performance summary** (strengths, weak topics, next steps) |
| 3 | **History dashboard** (score trend, accuracy per topic, recent sessions, average time) |
| 4 | **Daily generation limit** per user (default 20) |
| 5 | "Custom company" option (free-text company name) |

### Roadmap (README only)
Adaptive difficulty, AI hints, more languages, demo video.

---

## 4. User Stories

1. As a user, I can register and log in so my history is saved.
2. As a user, I can choose company, difficulty (easy / medium / hard / mixed), number of questions, and time per question.
3. As a user, I get questions that match the chosen company's style and difficulty.
4. As a user, I can write Python in an editor, run it against visible examples, and submit.
5. As a user, my code auto-submits when the timer ends and I move to the next question.
6. As a user, I see a score (percentage of test cases passed) and a per-question breakdown at the end.
7. As a user, I see an AI summary of my strengths and weak topics (Phase 2).
8. As a user, I can view my past sessions and trends on a dashboard (Phase 2).

---

## 5. Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | Python, **Django** |
| Auth | Django built-in auth |
| Main database | SQLite locally, **PostgreSQL** on Render (users, sessions, submissions) |
| Question bank (Phase 2) | **Turso** (libSQL) through its Python client |
| LLM | **Gemini API** (called only from the server) |
| Frontend | Django templates, vanilla JavaScript (or HTMX if wanted), CSS |
| Editor | **Monaco Editor** (CDN) |
| Code execution | **Pyodide** inside a **Web Worker** |
| Charts (Phase 2) | Chart.js |
| Hosting | **Render** (PythonAnywhere as backup) |
| Config | Environment variables via `python-dotenv` |

Notes:
- Check the current Gemini model names and the current Turso Python client in their official docs before coding. Keep the model name in an env variable (`GEMINI_MODEL`).
- Django does not support Turso as a native database backend. Use Turso only for the question bank, accessed through its client library.

---

## 6. Architecture

```
┌───────────────────────── Browser ─────────────────────────┐
│  Settings UI -> Question UI (Monaco) -> Results UI         │
│                    │                                       │
│           Web Worker (Pyodide)                             │
│   - runs reference solution (verification)                 │
│   - runs user code (tests) with timeout                    │
└───────────────┬───────────────────────────────────────────┘
                │ HTTPS (JSON)
┌───────────────▼───────────────────────────────────────────┐
│                     Django Server                          │
│  Auth | Session logic | Gemini client | Scoring | Limits   │
└───────┬──────────────────┬────────────────────┬───────────┘
        │                  │                    │
   Gemini API        Postgres/SQLite          Turso (Phase 2)
 (generate, summary) (users, sessions,        (verified question
                      submissions)             bank)
```

### Core request flow (Phase 1)
1. User submits settings -> server creates a `Session`.
2. Server asks Gemini for questions (one request per question, or small batches) and saves each as `status = pending`.
3. Browser receives a pending question and runs the **reference solution** against its test cases in the Pyodide worker.
4. Browser posts the verification result to the server.
   - All tests pass -> `status = verified`, question is shown to the user.
   - Any failure, crash, or timeout -> `status = rejected`, server generates a replacement (max **3 attempts** per slot).
5. User solves the question. Timer runs. Run executes visible tests only. Submit (or auto-submit) executes **all** tests.
6. Browser posts the per-test results. Server computes the score and saves the `Submission`.
7. After the last question, the server finalizes the session and shows results.

---

## 7. Functional Requirements

### 7.1 Authentication
- Register (username, email optional, password), login, logout using Django auth.
- All app pages and APIs require login (`@login_required`).
- Redirect to login with a `next` parameter.

### 7.2 Settings Page
| Setting | Options | Default |
|---------|---------|---------|
| Company | Fixed list (see 7.3). Custom text in Phase 2 | first in list |
| Difficulty | Easy, Medium, Hard, Mixed | Mixed |
| Number of questions | 1 to 10 | 3 |
| Time per question | "Use default" or custom 5 to 60 minutes | Use default |

**Default times:** Easy 10 min, Medium 20 min, Hard 35 min.
**Custom time:** if set, it applies to every question in the session. In Mixed mode, defaults apply per question's own difficulty unless a custom time is set.

**Mixed mode ratio (fixed for v1):** 40% easy, 40% medium, 20% hard.
Rounding rule: `hard = round(0.2 * n)`, `easy = round(0.4 * n)`, `medium = n - easy - hard`. For n = 1, use medium. Order the questions easy -> medium -> hard.

### 7.3 Company Styles
Store each company as a record with `name` and `style_notes` that go into the prompt. Starter list (edit freely):

| Company | Style notes for prompt |
|---------|------------------------|
| Zoho | Logic-heavy, string/array manipulation, pattern and simulation problems |
| Freshworks | Practical data-handling, dictionaries, API-style and customer-ticket scenarios |
| Razorpay | Payments/FinTech scenarios: transactions, ledgers, rate limits, reconciliation |
| PhonePe | UPI-style transaction processing, validation, aggregation |
| TCS / Infosys | Fundamentals: strings, lists, basic math, sorting |
| Amazon | Data structures, hash maps, two pointers, graphs, optimization |

**Important:** label all questions as *"inspired by the style of <company>"*. Never claim they are real company questions.

### 7.4 Question Generation (Gemini)
- Called **only from the server**. The API key never reaches the browser.
- Request structured JSON output (use Gemini's JSON response mode and a response schema).
- Prompt inputs: company, style notes, difficulty, topic hint, list of titles already used in this session (to avoid duplicates).
- Server validates the JSON before saving (see 9.2). Invalid JSON or schema mismatch counts as a failed attempt.

### 7.5 Verification (the headline feature)
- Runs in the browser, in the same Pyodide worker, **before** the user sees the question.
- For every test case: call the reference solution with the test input, compare to `expected`.
- A question is **approved** only if **all** test cases pass and none crash or time out.
- Per-slot retry limit: 3. If all 3 fail, show a friendly error and let the user retry the slot.
- Show a loading state: "Generating and verifying question 2 of 5..."
- Known limitation (document in README): the reference solution passes through the browser during verification, so a technical user could find it in the network tab. This is acceptable for a practice tool.

### 7.6 Editor and Execution
- Monaco editor with Python syntax highlighting and starter code (function signature only).
- **Run:** runs the code against **visible** test cases (the examples) and shows output, pass/fail, and errors.
- **Submit:** runs against **all** test cases (visible and hidden) and records results.
- Code runs in a **Web Worker** with Pyodide. Per-run timeout (for example 5 seconds). If exceeded, terminate the worker, recreate it, and report "Time Limit Exceeded".
- Capture `stdout` and exceptions. Show tracebacks in a readable output panel.
- Convention: the user must implement the function named in `function_name`. Tests call it directly with the given arguments.

### 7.7 Timer and Auto-Submit
- Countdown shown at the top of the question screen. It turns red in the last 60 seconds.
- At zero: lock the editor, run all tests, save the submission with `auto_submitted = true`, move to the next question.
- Server stores `started_at` and `time_limit_seconds`. When a submission arrives, the server records the time taken (server time is the source of truth).
- If the user refreshes mid-question, the timer resumes from the server's `started_at`.

### 7.8 Scoring
- **Per question:** `score = tests_passed / tests_total * 100`.
- **Solved:** a question is "solved" only at 100%.
- **Session score:** average of the question scores.
- All test cases weigh equally in v1.
- Example: 7 full solves and 3 half-solves out of 10 = 85%.

### 7.9 Results Page
- Session score and "X of N solved".
- Per-question table: difficulty badge (green / yellow / red), title, topic, tests passed, score bar, time taken, auto-submitted flag, link to review the submitted code.
- AI summary block (Phase 2).
- Buttons: "New session", "View history".

### 7.10 AI Summary (Phase 2)
- On session finish, the server sends **stats only** (not full code) to Gemini: company, per-question topic, difficulty, pass/fail per test kind (`normal` / `edge` / `performance`), time taken, auto-submitted.
- Gemini returns JSON: `strengths[]`, `weak_topics[]`, `next_steps[]` (2 to 3 items).
- Saved in `Session.ai_summary` so it is shown again without another API call.
- If the call fails, show the results without the summary and offer a "Generate summary" retry button.

### 7.11 History Dashboard (Phase 2)
- Line chart: session score over time.
- Bar chart: accuracy per topic.
- Table: recent sessions (date, company, difficulty, score).
- Stats: average time per difficulty, auto-submit rate.
- Computed from Django queries and rendered with Chart.js.

### 7.12 Question Bank with Turso (Phase 2)
- Table `questions` and `test_cases` in Turso hold **verified** questions only.
- **Serve order:**
  1. Query Turso for verified questions matching company and difficulty that this user has not seen.
  2. If enough, serve them instantly with no Gemini call.
  3. If not enough, generate with Gemini, verify in the browser, then save the verified ones to Turso.
  4. When unseen questions for a user's company and difficulty drop below a threshold (for example 3), generate a new batch in the background.
- "Seen" is tracked in Django (`SessionQuestion`), keyed by the question's bank ID.
- Questions served from the bank do **not** count toward the daily generation limit.

### 7.13 Daily Generation Limit (Phase 2)
- Table `GenerationUsage(user, date, count)`.
- Default limit: **20 Gemini-generated questions per user per day** (configurable via env).
- Counts only questions actually generated by Gemini, including rejected ones.
- When reached: show "Daily generation limit reached. You can still practice with saved questions." and keep serving from the bank.
- Resets at midnight (use the configured timezone, for example Asia/Kolkata).

---

## 8. Data Model

### 8.1 Django models (main database)

```text
Company
  id, name (unique), style_notes (text), is_active

Question
  id, company (FK), difficulty (easy|medium|hard), topic (str),
  title, description (text), constraints (text),
  examples (JSON), function_name, starter_code (text),
  reference_solution (text),
  status (pending|verified|rejected),
  source (gemini|bank), bank_id (nullable, Turso id),
  created_at

TestCase
  id, question (FK), input_json (JSON list of args),
  expected_json (JSON), kind (normal|edge|performance),
  is_hidden (bool)

Session
  id, user (FK), company (FK), difficulty_mode (easy|medium|hard|mixed),
  num_questions, time_limit_override_minutes (nullable),
  status (in_progress|finished), started_at, finished_at,
  score (float, nullable), ai_summary (JSON, nullable)

SessionQuestion
  id, session (FK), question (FK), order,
  time_limit_seconds, started_at, submitted_at (nullable),
  auto_submitted (bool), tests_passed, tests_total, score (float)

Submission
  id, session_question (FK), code (text),
  results (JSON: per-test pass/fail, error, runtime),
  created_at

GenerationUsage   (Phase 2)
  id, user (FK), date, count      unique (user, date)
```

### 8.2 Turso schema (Phase 2)

```sql
CREATE TABLE questions (
  id INTEGER PRIMARY KEY,
  company TEXT NOT NULL,
  difficulty TEXT NOT NULL,
  topic TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  constraints TEXT,
  examples_json TEXT,
  function_name TEXT NOT NULL,
  starter_code TEXT NOT NULL,
  reference_solution TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE test_cases (
  id INTEGER PRIMARY KEY,
  question_id INTEGER NOT NULL REFERENCES questions(id),
  input_json TEXT NOT NULL,
  expected_json TEXT NOT NULL,
  kind TEXT NOT NULL,          -- normal | edge | performance
  is_hidden INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_questions_lookup ON questions(company, difficulty);

-- optional
CREATE TABLE question_reports (
  id INTEGER PRIMARY KEY,
  question_id INTEGER NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL
);
```

---

## 9. Gemini Integration

### 9.1 Question prompt (template)

```text
You are an interview question writer. Create ONE Python coding question
inspired by the interview style of {company}.

Company style notes: {style_notes}
Difficulty: {difficulty}
Topic hint: {topic_hint}
Do NOT repeat these titles: {used_titles}

Rules:
- The solution must be a single pure Python function named {function_name or "chosen by you"}.
- No input(), no file access, no network, no external libraries (standard library only).
- Inputs and outputs must be JSON-serializable (numbers, strings, lists, dicts, booleans, null).
- Provide 3 examples, and 8 to 12 test cases:
  at least 3 "normal", 3 "edge" (empty input, single element, duplicates, negatives),
  and 1 "performance" (large input that a good solution handles in under 1 second).
- Provide a correct reference solution.
- Return ONLY JSON matching the schema.
```

Difficulty guide for the prompt:
- **Easy:** strings, lists, basic loops, simple math.
- **Medium:** dictionaries, sorting, two pointers, simple recursion.
- **Hard:** dynamic programming, graphs, optimization, performance constraints.

### 9.2 Response schema and validation

```json
{
  "title": "string",
  "topic": "string",
  "difficulty": "easy|medium|hard",
  "description": "string",
  "constraints": "string",
  "function_name": "snake_case string",
  "starter_code": "def function_name(args):\n    pass",
  "examples": [
    { "input": [ ... ], "output": ..., "explanation": "string" }
  ],
  "test_cases": [
    { "input": [ ... ], "expected": ..., "kind": "normal|edge|performance", "hidden": true }
  ],
  "reference_solution": "string (python source)"
}
```

Server-side validation (reject the attempt if any check fails):
- Valid JSON, all required fields present, correct types.
- `function_name` is a valid Python identifier and appears in `starter_code` and `reference_solution`.
- 8 to 12 test cases, at least one `edge`.
- Each `input` is a list of JSON-serializable values.
- Reference solution contains no forbidden tokens (`import os`, `subprocess`, `open(`, `socket`, `eval(`, `exec(`, `__import__`). Allow only a small set of safe imports (`math`, `collections`, `itertools`, `heapq`, `bisect`, `functools`, `re`).
- Title is not a duplicate within the session.

### 9.3 Reliability
- Set a request timeout and retry transient API errors (429/5xx) with short backoff.
- Strip markdown code fences before parsing JSON as a fallback.
- Log every failed attempt (reason: invalid JSON, validation error, verification failed).
- Never log the API key.

---

## 10. Pyodide Runner Design

### 10.1 Worker protocol

Main thread -> worker:
```json
{ "id": "run-123", "mode": "verify|run|submit",
  "code": "...", "function_name": "...",
  "tests": [ { "input": [ ... ], "expected": ..., "kind": "normal" } ],
  "per_test_timeout_ms": 2000 }
```

Worker -> main thread:
```json
{ "id": "run-123", "status": "ok|error|timeout",
  "results": [ { "index": 0, "passed": true, "actual": ..., "error": null, "ms": 3 } ] }
```

### 10.2 Timeout handling
- The main thread starts a timer when it sends a job. If no response arrives in time, call `worker.terminate()`, create a new worker, and return `timeout` for the affected tests.
- Pyodide takes a few seconds to load. Load it once per page and reuse the worker. Show "Loading Python runtime..." the first time.

### 10.3 Test harness (inside the worker)
- Execute the code in a fresh namespace dictionary.
- Look up `function_name` in the namespace. If missing, report "Function `<name>` not found".
- For each test: deep-copy the input (so a function that mutates its arguments does not affect later tests), call the function, compare with `expected`.
- **Comparison:** JSON-style equality. Tuples are treated as lists. Floats use `math.isclose` with a tolerance. Dict key order is ignored.
- Catch exceptions per test and report the error message and the last traceback line.
- Capture `print()` output and show it in the console panel (truncate at about 10 KB).

### 10.4 Limits to document
- Pure Python and standard library only.
- Slower than native Python, so performance tests must be modest.
- Pyodide runs inside the user's own browser, so no user code runs on the server.

---

## 11. API Endpoints (Django)

| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/accounts/register/`, `/login/`, `/logout/` | Auth |
| GET | `/` | Settings page |
| POST | `/sessions/` | Create a session from settings |
| GET | `/sessions/<id>/` | Question screen (current question) |
| POST | `/api/sessions/<id>/next-question/` | Get or generate the next pending question |
| POST | `/api/questions/<id>/verify/` | Browser reports verification result (`passed: bool`, details) |
| POST | `/api/session-questions/<id>/submit/` | Submit code and per-test results |
| GET | `/sessions/<id>/results/` | Results page |
| POST | `/api/sessions/<id>/summary/` | Generate AI summary (Phase 2) |
| GET | `/dashboard/` | History dashboard (Phase 2) |

Rules:
- All endpoints require login and check that the session belongs to `request.user`.
- CSRF protection stays on. Send the CSRF token with every `fetch` POST.
- Return JSON errors with clear messages and proper status codes.

**Trust note:** because tests run in the browser, the client could fake results. For a practice tool this is acceptable. Document it in the README ("results are self-reported by the client, since no server-side execution is used by design").

---

## 12. UI / Pages

1. **Login / Register**: simple forms.
2. **Settings page**: company dropdown, difficulty selector, question count (1-10), timer (default or custom minutes), Start button.
3. **Question screen (split layout)**
   - **Left:** title, difficulty badge, company tag ("Inspired by X"), description, examples, constraints.
   - **Right:** Monaco editor, **Run** and **Submit** buttons, output/test panel below the editor.
   - **Top bar:** countdown timer and question number (text only, "Question 2 of 5").
4. **Results page**: score, breakdown table, AI summary (Phase 2).
5. **Dashboard** (Phase 2): charts and table described in 7.11.

Explicitly excluded: dark/light theme toggle, progress bar across questions.
Keep the CSS simple and clean. Make it usable on a laptop screen first. Mobile is optional.

---

## 13. Security

- Gemini key and Django `SECRET_KEY` live in environment variables only. `.env` is in `.gitignore` from the first commit. If a key ever leaks, rotate it immediately.
- The browser never calls Gemini. It only calls your server.
- All generation endpoints require login. Phase 2 adds the daily per-user limit.
- Set a **quota or spending cap** in Google AI Studio as a backstop.
- User code runs only in the user's browser inside a Web Worker (no server execution).
- Render the question text as plain text or sanitized HTML. Never insert LLM output with `innerHTML` unsanitized (prevent XSS).
- `DEBUG = False` in production, set `ALLOWED_HOSTS`, use HTTPS-only cookies in production.
- Validate and size-limit all submitted code and results on the server (for example, max 50 KB code).

---

## 14. Error Handling and Edge Cases

| Case | Behavior |
|------|----------|
| Gemini returns invalid JSON | Count as failed attempt, retry (max 3) |
| Reference solution fails verification | Discard, regenerate |
| All 3 attempts fail | Friendly message and "Try again" button |
| Gemini rate limit / outage | Show "Generation is busy, try again shortly" |
| User code has an infinite loop | Worker terminated, "Time Limit Exceeded" |
| User code raises an exception | Show message, test marked failed |
| Function name missing in user code | Clear message, score 0 for that question |
| User closes the tab mid-session | Session stays `in_progress`, can resume, timer based on server `started_at` |
| Timer expires while a run is executing | Cancel the run, then auto-submit |
| Browser lacks WebAssembly or Worker support | Show unsupported-browser message |
| Pyodide fails to load (network) | Retry button |
| Daily limit reached (Phase 2) | Serve from bank only, show message |

---

## 15. Testing Plan

**Automated (Django tests):**
- Session creation and the Mixed ratio rounding for n = 1..10.
- Scoring math (partial credit, session average).
- JSON validation of Gemini responses (good, missing field, forbidden tokens, duplicate title).
- Access control (user A cannot open user B's session).
- Daily limit counter (Phase 2).

**Manual "break it on purpose" checklist (important for your interview story):**
- [ ] Infinite loop `while True: pass`
- [ ] Empty input and single-element input
- [ ] Code that raises an exception
- [ ] Code that mutates its input
- [ ] Wrong function name
- [ ] Timer reaches zero while typing
- [ ] Refresh mid-question
- [ ] Gemini returns garbage (mock it)
- [ ] A deliberately wrong reference solution is rejected by verification
- [ ] Logout and login keeps history

---

## 16. Deployment (Render)

- Create a Render web service from the GitHub repo.
- Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
- Start command: `gunicorn config.wsgi`
- Use **WhiteNoise** for static files.
- Use a Render **PostgreSQL** database (`DATABASE_URL` via `dj-database-url`). Do not rely on SQLite on Render, because the file is wiped on redeploy. Check Render's current free-tier terms for the database.
- Free tier sleeps after inactivity and takes about 30 to 60 seconds to wake up. Note this in the README, and open the link yourself before sharing it.

**Environment variables**
```text
SECRET_KEY=
DEBUG=False
ALLOWED_HOSTS=
DATABASE_URL=
GEMINI_API_KEY=
GEMINI_MODEL=
DAILY_GENERATION_LIMIT=20          # Phase 2
TURSO_DATABASE_URL=                # Phase 2
TURSO_AUTH_TOKEN=                  # Phase 2
```

---

## 17. Suggested Project Structure

```text
prepforge/
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── PROJECT_SPEC.md
├── config/                  # settings, urls, wsgi
├── accounts/                # register/login views and templates
├── interview/               # main app
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── services/
│   │   ├── gemini.py        # generation + summary + validation
│   │   ├── sessions.py      # mixed ratio, timing, scoring
│   │   ├── bank.py          # Turso access (Phase 2)
│   │   └── limits.py        # daily limit (Phase 2)
│   ├── templates/interview/
│   │   ├── settings.html
│   │   ├── question.html
│   │   ├── results.html
│   │   └── dashboard.html   # Phase 2
│   ├── static/interview/
│   │   ├── js/
│   │   │   ├── editor.js    # Monaco setup
│   │   │   ├── runner.js    # worker management and timeouts
│   │   │   ├── pyodide.worker.js
│   │   │   ├── session.js   # flow: verify -> solve -> submit -> next
│   │   │   └── timer.js
│   │   └── css/app.css
│   └── tests/
└── docs/
    ├── architecture.png
    └── screenshots/
```

---

## 18. Seven-Day Plan (about 14 hours)

| Day | Deliverable |
|-----|-------------|
| 1 | Django project, GitHub repo, auth (register/login/logout), settings page, models |
| 2 | Gemini service: generate question JSON, validate, save as pending |
| 3 | Monaco editor and Pyodide Web Worker: Run against visible tests, timeout works |
| 4 | **Verification flow** (retry/replace) and the auto-submit timer |
| 5 | Submissions, partial-credit scoring, results page |
| 6 | Deploy to Render, fix environment problems |
| 7 | README, architecture diagram, screenshots, break-it-on-purpose testing |

Week 2: Turso bank -> AI summary -> dashboard -> daily limit -> custom company.

If you fall behind, cut in this order: custom time override UI polish, review-code link, hard-difficulty tuning. **Never cut verification.**

---

## 19. Acceptance Criteria (Phase 1 "done")

- [ ] A new user can register, log in, and start a session from the settings page.
- [ ] Questions are generated by Gemini and shown only after passing verification.
- [ ] A deliberately broken question is rejected and replaced automatically.
- [ ] User code runs in the browser; an infinite loop shows "Time Limit Exceeded" without freezing the page.
- [ ] The timer auto-submits at zero and moves to the next question.
- [ ] Scores use partial credit and match the formula in 7.8.
- [ ] The results page shows the score and per-question breakdown.
- [ ] The live Render link works end to end.
- [ ] The README contains: pitch, live link, screenshots, architecture diagram, features, setup steps, design decisions, "How I built it", and roadmap.

---

## 20. README Requirements

1. Live demo link at the top (note about the free server wake-up delay).
2. One-line pitch and 3 to 4 screenshots (settings, question screen, results, dashboard).
3. Architecture diagram.
4. Key features list.
5. Tech stack and local setup steps.
6. **Design decisions:** why Pyodide (no server-side execution risk), why verification (LLM output cannot be trusted), why Turso as a cache (speed and cost).
7. **How I built it:** AI tools used, example prompts, and what you fixed by hand.
8. Known limitations (client-side results, Pyodide speed, free-tier cold start).
9. Roadmap: adaptive difficulty, AI hints, more languages.

---

## 21. Interview Talking Points

Be ready to explain these without help:

1. **Why verify?** LLM-generated test cases are often wrong, so a reference solution must pass them before a user sees the question.
2. **Why Pyodide?** User code never runs on the server, which removes the hardest security problem. Trade-off: slower, limited libraries.
3. **How does the timeout work?** The Web Worker is terminated and recreated if a run exceeds its limit.
4. **How does the Turso-first logic work?** Serve verified questions from the bank, generate only when needed, and refill in the background.
5. **How is the daily limit counted?** Only Gemini-generated questions count, per user per day.
6. **What did you verify yourself?** Say plainly: "I built it with AI coding tools, designed the architecture, and tested the failure cases myself."

**Resume bullet:**
> Built a company-aware Python interview practice IDE where Gemini generates questions and test cases, and every question is verified in-browser (Pyodide + Web Worker) with a reference solution before it is shown; Django, Gemini API, Turso, deployed on Render.

---

## 22. Prompt for Your AI Coding Tool: Day 1

```text
Create a Django project called "prepforge" with an app "accounts" and an app "interview".

Requirements:
1. Django auth: register, login, logout pages with simple clean templates.
2. All pages except login/register require login.
3. Models in interview/models.py: Company, Question, TestCase, Session,
   SessionQuestion, Submission (fields as described in the spec below).
4. A settings page (GET /) with: company dropdown (from Company table),
   difficulty (easy/medium/hard/mixed), number of questions (1-10),
   time per question ("use default" or custom 5-60 minutes).
5. POST creates a Session and redirects to /sessions/<id>/.
6. Seed 6 companies using a data migration or management command.
7. Use python-dotenv for config, add .env.example and .gitignore (ignore .env, db.sqlite3).
8. Use SQLite locally; structure settings so DATABASE_URL can switch to Postgres later.

Do not implement Gemini or code execution yet.
Write clear, simple code with comments.
```

*(Paste the Data Model from section 8.1 below this prompt.)*
