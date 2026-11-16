# PrepForge ⚡

> **A company-aware Python coding IDE where Gemini synthesizes interview questions and test cases, and every question is verified in-browser with a reference solution before it is shown.**

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-green.svg)](https://www.djangoproject.com/)
[![WebAssembly](https://img.shields.io/badge/Pyodide-WebAssembly-purple.svg)](https://pyodide.org/)
[![Gemini API](https://img.shields.io/badge/Google-Gemini%20API-orange.svg)](https://ai.google.dev/)
[![Render](https://img.shields.io/badge/Deployment-Render-black.svg)](https://render.com/)

**Headline Engineering Principle:** *LLM output cannot be trusted blindly, so every generated problem is verified before use.*

---

## 🚀 Live Demo

- **Live URL:** [https://prepforge.onrender.com](https://prepforge.onrender.com) *(Configure your deployment URL)*
> **Note on Free-Tier Hosting:** Render free instances spin down after inactivity and take 30–60 seconds to wake up on the first request.

---

## 💡 Key Architectural Pillars

### 1. In-Browser Verification Protocol (The Headline Feature)
Traditional AI coding tools show generated questions immediately, often leading to invalid examples, wrong test expectations, or impossible constraints. 
**PrepForge eliminates this problem:**
1. Gemini synthesizes problem descriptions, 8–12 test cases, and an algorithmic reference solution in structured JSON.
2. Before the question is displayed, the browser runs the reference solution against **all** generated test cases inside a **Pyodide Web Worker**.
3. If all test cases pass within time limits, the question is marked `verified` and presented to the user.
4. If any test case fails, crashes, or times out, the question is discarded, marked `rejected`, and a replacement attempt is triggered (up to 3 retries).

### 2. Zero Server-Side Execution Vulnerability
User code execution is executed entirely inside the browser's JavaScript environment via **WebAssembly (Pyodide)** inside isolated **Web Workers**. 
- No untrusted Python code ever runs on the backend server.
- Infinite loops (`while True: pass`) are killed cleanly via `Worker.terminate()`, safely reporting "Time Limit Exceeded" without freezing the user interface or consuming server CPU.

---

## 🏛️ Architecture Overview

```
┌───────────────────────────────── Browser ──────────────────────────────────┐
│  Settings UI  ───>  Question Workspace (Monaco Editor)  ───>  Results Page │
│                                  │                                         │
│                      Web Worker (Pyodide sandbox)                          │
│         - Executes reference solution (verification phase)                 │
│         - Executes candidate code against test cases with timeout          │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   │ HTTPS / JSON API
┌──────────────────────────────────▼─────────────────────────────────────────┐
│                           Django Application Server                        │
│    Auth & Security  │  Session Engine  │  Scoring Logic  │ Rate Limiting   │
└──────────────┬───────────────────┬───────────────────┬─────────────────────┘
               │                   │                   │
               ▼                   ▼                   ▼
       Google Gemini API    PostgreSQL / SQLite      Turso (Phase 2)
     (Structured JSON Gen)  (Sessions & Users)     (Verified Question Bank)
```

---

## 🛠️ Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Backend** | Python 3.12+, **Django 6.0** | Robust session management, ORM, built-in authentication, and security middleware. |
| **Database** | **SQLite** (local dev) / **PostgreSQL** (Render prod via `dj-database-url`) | Relational integrity across sessions, questions, submissions, and test cases. |
| **LLM Provider**| **Google Gemini API** (`gemini-2.5-flash`) | Fast structured JSON output generation with strict schema enforcement. |
| **Code Editor** | **Monaco Editor** (VS Code browser engine) | Industry-standard coding experience, syntax highlighting, and keyboard shortcuts. |
| **Execution Sandbox** | **Pyodide in a Web Worker** | Safely runs Python in WebAssembly; completely avoids server execution risks. |
| **Static Assets** | **WhiteNoise** | High-performance static asset compression and caching on production. |

---

## ⚙️ Local Development Setup

### 1. Prerequisites
- Python 3.12+ installed
- Git installed

### 2. Clone and Setup Environment
```bash
git clone https://github.com/your-username/prepforge.git
cd prepforge

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
python -m pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Populate your `.env` file:
```ini
SECRET_KEY=dev-secret-key-prepforge-12345
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
GEMINI_API_KEY=your_gemini_api_key_here  # Leave empty to test with offline high-fidelity mock questions!
GEMINI_MODEL=gemini-2.5-flash
```

### 4. Database Setup & Seed Data
```bash
python manage.py migrate
python manage.py seed_companies
```

### 5. Run Test Suite
```bash
python manage.py test
```

### 6. Start Development Server
```bash
python manage.py runserver
```
Visit `http://localhost:8000` in your browser. Register a user and begin your interview session!

---

## 🧪 Verification & Edge Case Checklist

PrepForge has been verified against the following adversarial edge cases:
- [x] **Infinite Loops:** `while True: pass` triggers worker termination after 2000ms with "Time Limit Exceeded" without crashing the browser tab.
- [x] **Malformed / Injected LLM Output:** Server-side AST validation rejects forbidden tokens (`os`, `subprocess`, `open`, `eval`, `exec`).
- [x] **Broken Reference Solution:** Automatically rejected by the in-browser Pyodide verification step and replaced.
- [x] **Timer Expiration:** Auto-submits candidate code and transitions to the next slot when countdown reaches 00:00.
- [x] **Page Refresh Mid-Session:** Session timer resumes seamlessly using server-authoritative timestamps.
- [x] **Argument Mutation Safety:** Pyodide test harness deepcopies all input parameters before invocation.

---

## 🎯 Interview Talking Points

1. **Why verify LLM outputs?**
   > *"LLMs frequently suffer from alignment drift or hallucinated edge-case expectations. Running the reference solution against test cases in Pyodide before showing the problem guarantees that the question is demonstrably solvable."*

2. **Why run code in Pyodide rather than Docker on the server?**
   > *"Running untrusted user code on a server requires expensive container isolation, gVisor sandboxing, or Docker management. By running Pyodide in WebAssembly inside a Web Worker, all execution occurs within the client's browser sandbox, eliminating server infrastructure cost and remote code execution vulnerabilities."*

3. **How does the Web Worker timeout work?**
   > *"Because JavaScript Web Workers run on a background thread, the host thread can call `worker.terminate()` if a run takes longer than the timeout threshold, re-spawning a clean worker immediately without dropping application state."*

---

## 🗺️ Roadmap
- [ ] **Phase 2:** Turso libSQL question bank integration for sub-second verified question retrieval.
- [ ] **Phase 2:** Post-session AI performance summaries highlighting strength and growth areas.
- [ ] **Phase 2:** Chart.js trend visualization dashboard.
- [ ] Multi-language support (JavaScript / TypeScript).

---

## 📄 License
MIT License. Created by Mukil Anand KS.
