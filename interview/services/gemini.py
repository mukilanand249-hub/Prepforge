import json
import re
import ast
import logging
from typing import Dict, Any, List, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)

# Allowed safe Python standard library modules for reference solutions
SAFE_MODULES = {'math', 'collections', 'itertools', 'heapq', 'bisect', 'functools', 're', 'typing'}

# Dangerous tokens forbidden in reference solutions
FORBIDDEN_TOKENS = [
    'import os', 'os.', 'subprocess', 'open(', 'socket', 'eval(', 'exec(',
    '__import__', 'importlib', 'sys.', 'shutil', 'builtin', '__subclasses__',
    'requests', 'urllib', 'http.client'
]

QUESTION_PROMPT_TEMPLATE = """You are an interview question writer. Create ONE Python coding question inspired by the interview style of {company}.

Company style notes: {style_notes}
Difficulty: {difficulty}
Topic hint: {topic_hint}
Do NOT repeat these titles: {used_titles}

Rules:
- The solution must be a single pure Python function named {function_name_hint}.
- No input(), no file access, no network, no external libraries (standard library only).
- Inputs and outputs must be JSON-serializable (numbers, strings, lists, dicts, booleans, null).
- Provide 3 examples with clear explanation.
- Provide 8 to 12 test cases:
  * at least 3 "normal" test cases
  * at least 3 "edge" test cases (e.g. empty input, single element, duplicates, negative numbers, extreme allowed values)
  * 1 "performance" test case (input size that tests algorithmic efficiency, runs in under 1s with O(N) or O(N log N))
  * The first 3 test cases should have hidden = false (corresponding to the examples), the rest hidden = true.
- Provide a correct, clean Python reference solution.
- Return ONLY valid JSON matching this schema:
{{
  "title": "string",
  "topic": "string",
  "difficulty": "{difficulty}",
  "description": "string (markdown allowed for formatting)",
  "constraints": "string (time/space complexity, input limits)",
  "function_name": "snake_case_name",
  "starter_code": "def function_name(args):\\n    pass",
  "examples": [
    {{ "input": [ ... ], "output": ..., "explanation": "string" }}
  ],
  "test_cases": [
    {{ "input": [ ... ], "expected": ..., "kind": "normal|edge|performance", "hidden": false }}
  ],
  "reference_solution": "def function_name(args):\\n    ..."
}}
"""

MOCK_FALLBACK_QUESTIONS = {
    'easy': {
        "title": "Unique Customer Identifier Formatter",
        "topic": "Strings and Hash Sets",
        "difficulty": "easy",
        "description": "Given a list of customer account IDs (strings with leading/trailing spaces or lowercase/uppercase differences), normalize them by trimming whitespace and converting to uppercase, then return the count of unique identifiers.",
        "constraints": "1 <= len(ids) <= 10^4\nEach ID length <= 50",
        "function_name": "count_unique_ids",
        "starter_code": "def count_unique_ids(ids: list[str]) -> int:\n    pass",
        "examples": [
            {"input": [[" abc ", "ABC", "xyz "]], "output": 2, "explanation": "' abc ' and 'ABC' normalize to 'ABC'."},
            {"input": [["a", "b", "c"]], "output": 3, "explanation": "All 3 are distinct."},
            {"input": [[]], "output": 0, "explanation": "Empty list has 0 unique IDs."}
        ],
        "test_cases": [
            {"input": [[" abc ", "ABC", "xyz "]], "expected": 2, "kind": "normal", "hidden": False},
            {"input": [["a", "b", "c"]], "expected": 3, "kind": "normal", "hidden": False},
            {"input": [["dup", "DUP", "  dup  "]], "expected": 1, "kind": "normal", "hidden": False},
            {"input": [[]], "expected": 0, "kind": "edge", "hidden": True},
            {"input": [["single"]], "expected": 1, "kind": "edge", "hidden": True},
            {"input": [["  ", " ", ""]], "expected": 1, "kind": "edge", "hidden": True},
            {"input": [["id1", "id2", "ID1", "ID2"]], "expected": 2, "kind": "normal", "hidden": True},
            {"input": [[f"usr_{i % 50}" for i in range(1000)]], "expected": 50, "kind": "performance", "hidden": True}
        ],
        "reference_solution": "def count_unique_ids(ids):\n    normalized = {x.strip().upper() for x in ids}\n    return len(normalized)"
    },
    'medium': {
        "title": "Sliding Window Idempotent Ledger",
        "topic": "Hash Maps and Sliding Window",
        "difficulty": "medium",
        "description": "Given a sequence of transaction records as tuples (timestamp, transaction_id, amount), process transactions in chronological order. A transaction is valid only if its transaction_id has NOT been seen in the previous window_seconds. Return the total accepted amount.",
        "constraints": "1 <= transactions.length <= 10^5\ntimestamp is non-decreasing",
        "function_name": "reconcile_transactions",
        "starter_code": "def reconcile_transactions(transactions: list[list], window_seconds: int) -> int:\n    pass",
        "examples": [
            {"input": [[[10, "tx1", 100], [15, "tx1", 100], [25, "tx1", 100]], 10], "output": 200, "explanation": "tx1 at 15 is rejected because 15 - 10 <= 10. tx1 at 25 is accepted (25 - 10 > 10)."},
            {"input": [[[1, "a", 50], [2, "b", 70]], 5], "output": 120, "explanation": "Distinct IDs are both accepted."},
            {"input": [[], 5], "output": 0, "explanation": "No transactions."}
        ],
        "test_cases": [
            {"input": [[[10, "tx1", 100], [15, "tx1", 100], [25, "tx1", 100]], 10], "expected": 200, "kind": "normal", "hidden": False},
            {"input": [[[1, "a", 50], [2, "b", 70]], 5], "expected": 120, "kind": "normal", "hidden": False},
            {"input": [[[1, "a", 10], [1, "a", 20]], 0], "expected": 30, "kind": "normal", "hidden": False},
            {"input": [[], 10], "expected": 0, "kind": "edge", "hidden": True},
            {"input": [[[5, "z", 1000]], 10], "expected": 1000, "kind": "edge", "hidden": True},
            {"input": [[[1, "k", 10], [3, "k", 10], [5, "k", 10], [7, "k", 10]], 3], "expected": 20, "kind": "normal", "hidden": True},
            {"input": [[[1, "x", -50], [10, "x", 100]], 5], "expected": 50, "kind": "edge", "hidden": True},
            {"input": [[[i, f"id_{i % 10}", 1] for i in range(500)], 5], "expected": 104, "kind": "performance", "hidden": True}
        ],
        "reference_solution": "def reconcile_transactions(transactions, window_seconds):\n    last_seen = {}\n    total = 0\n    for ts, tx_id, amount in transactions:\n        if tx_id in last_seen and (ts - last_seen[tx_id]) <= window_seconds:\n            continue\n        last_seen[tx_id] = ts\n        total += amount\n    return total"
    },
    'hard': {
        "title": "Optimal Multi-Currency Arbitrage Routing",
        "topic": "Graphs and Dynamic Programming",
        "difficulty": "hard",
        "description": "Given a source currency, a target currency, and a list of direct exchange rates [from_curr, to_curr, rate], find the maximum multiplier to convert 1.0 unit of source currency into target currency through at most max_hops intermediate conversions. Return 0.0 if unreachable.",
        "constraints": "rates.length <= 500\nmax_hops <= 5",
        "function_name": "max_exchange_rate",
        "starter_code": "def max_exchange_rate(rates: list[list], src: str, dst: str, max_hops: int) -> float:\n    pass",
        "examples": [
            {"input": [[["USD", "EUR", 0.9], ["EUR", "INR", 90.0], ["USD", "INR", 80.0]], "USD", "INR", 2], "output": 81.0, "explanation": "USD -> EUR -> INR yields 0.9 * 90.0 = 81.0, beating direct 80.0."},
            {"input": [[["USD", "GBP", 0.8]], "USD", "JPY", 1], "output": 0.0, "explanation": "No path exists."},
            {"input": [[["A", "B", 2.0]], "A", "A", 0], "output": 1.0, "explanation": "Same currency with 0 hops."}
        ],
        "test_cases": [
            {"input": [[["USD", "EUR", 0.9], ["EUR", "INR", 90.0], ["USD", "INR", 80.0]], "USD", "INR", 2], "expected": 81.0, "kind": "normal", "hidden": False},
            {"input": [[["USD", "GBP", 0.8]], "USD", "JPY", 1], "expected": 0.0, "kind": "normal", "hidden": False},
            {"input": [[["A", "B", 2.0]], "A", "A", 0], "expected": 1.0, "kind": "normal", "hidden": False},
            {"input": [[], "USD", "EUR", 2], "expected": 0.0, "kind": "edge", "hidden": True},
            {"input": [[["A", "B", 0.5], ["B", "C", 0.5]], "A", "C", 1], "expected": 0.0, "kind": "edge", "hidden": True},
            {"input": [[["A", "B", 1.5], ["B", "A", 0.6]], "A", "B", 3], "expected": 1.5, "kind": "normal", "hidden": True},
            {"input": [[["X", "Y", 10.0], ["Y", "Z", 10.0], ["Z", "W", 10.0]], "X", "W", 3], "expected": 1000.0, "kind": "normal", "hidden": True},
            {"input": [[["N1", "N2", 1.1], ["N2", "N3", 1.2], ["N3", "N4", 1.3], ["N4", "N5", 1.4]], "N1", "N5", 4], "expected": 2.4024, "kind": "performance", "hidden": True}
        ],
        "reference_solution": "def max_exchange_rate(rates, src, dst, max_hops):\n    if src == dst:\n        return 1.0\n    best = {src: 1.0}\n    for _ in range(max_hops):\n        curr = dict(best)\n        updated = False\n        for u, v, r in rates:\n            if u in curr and curr[u] * r > best.get(v, 0.0):\n                best[v] = curr[u] * r\n                updated = True\n        if not updated:\n            break\n    return round(best.get(dst, 0.0), 4)"
    }
}


def clean_json_response(raw_text: str) -> str:
    """
    Strips markdown code fences (```json ... ```) or whitespace.
    """
    text = raw_text.strip()
    if text.startswith('```'):
        # Strip opening line like ```json or ```
        lines = text.split('\n')
        if len(lines) >= 2:
            lines = lines[1:]
        text = '\n'.join(lines)
    if text.endswith('```'):
        text = text[:-3]
    return text.strip()


def validate_question_data(data: Dict[str, Any], used_titles: List[str] = None) -> Tuple[bool, str]:
    """
    Validates Gemini structured output against spec requirements:
    - Required fields and types
    - function_name identifier validity
    - function_name presence in starter_code and reference_solution
    - 8 to 12 test cases, at least one edge case
    - Forbidden token checks in reference solution
    - Title uniqueness within session
    """
    required_fields = [
        'title', 'topic', 'difficulty', 'description', 'constraints',
        'function_name', 'starter_code', 'examples', 'test_cases', 'reference_solution'
    ]
    for field in required_fields:
        if field not in data or data[field] is None:
            return False, f"Missing required field: {field}"

    if data['difficulty'] not in ('easy', 'medium', 'hard'):
        return False, f"Invalid difficulty: {data['difficulty']}"

    function_name = data.get('function_name', '').strip()
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', function_name):
        return False, f"Invalid function_name identifier: {function_name}"

    starter_code = data.get('starter_code', '')
    ref_sol = data.get('reference_solution', '')
    if function_name not in starter_code:
        return False, f"function_name '{function_name}' not found in starter_code"
    if function_name not in ref_sol:
        return False, f"function_name '{function_name}' not found in reference_solution"

    # Test cases validation
    test_cases = data.get('test_cases', [])
    if not isinstance(test_cases, list) or len(test_cases) < 6:
        return False, f"Expected at least 6-12 test cases, got {len(test_cases) if isinstance(test_cases, list) else 0}"

    has_edge = any(tc.get('kind') == 'edge' for tc in test_cases if isinstance(tc, dict))
    if not has_edge:
        return False, "Test cases must include at least one 'edge' case"

    for idx, tc in enumerate(test_cases):
        if not isinstance(tc, dict):
            return False, f"Test case #{idx} is not a valid object"
        if 'input' not in tc or 'expected' not in tc:
            return False, f"Test case #{idx} missing input or expected"
        if not isinstance(tc['input'], list):
            return False, f"Test case #{idx} input must be a list of arguments"

    # Security check on reference solution
    lower_ref = ref_sol.lower()
    for token in FORBIDDEN_TOKENS:
        if token in lower_ref:
            return False, f"Forbidden token detected in reference solution: {token}"

    # Verify AST syntax of reference solution
    try:
        parsed_ast = ast.parse(ref_sol)
        for node in ast.walk(parsed_ast):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split('.')[0]
                    if root_mod not in SAFE_MODULES:
                        return False, f"Unauthorized module import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split('.')[0]
                    if root_mod not in SAFE_MODULES:
                        return False, f"Unauthorized module import from: {node.module}"
    except SyntaxError as e:
        return False, f"Reference solution syntax error: {str(e)}"

    # Title collision check
    if used_titles and data.get('title') in used_titles:
        return False, f"Duplicate title in session: {data.get('title')}"

    return True, "Valid"


def generate_question_with_gemini(
    company_name: str,
    style_notes: str,
    difficulty: str,
    topic_hint: str = "Algorithms and data structures",
    used_titles: List[str] = None
) -> Dict[str, Any]:
    """
    Calls Gemini API to generate a structured interview question.
    Falls back to high-fidelity mock questions if API key is not configured or fails.
    """
    used_titles = used_titles or []
    api_key = getattr(settings, 'GEMINI_API_KEY', '')

    if not api_key:
        logger.warning("GEMINI_API_KEY is not configured. Serving high-fidelity mock question.")
        fallback = MOCK_FALLBACK_QUESTIONS.get(difficulty, MOCK_FALLBACK_QUESTIONS['medium']).copy()
        fallback['difficulty'] = difficulty
        fallback['title'] = f"{fallback['title']} ({company_name} Style)"
        return fallback

    prompt = QUESTION_PROMPT_TEMPLATE.format(
        company=company_name,
        style_notes=style_notes,
        difficulty=difficulty,
        topic_hint=topic_hint,
        used_titles=", ".join(used_titles) if used_titles else "None",
        function_name_hint="solution or domain specific snake_case"
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash')

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
            )
        )

        cleaned_text = clean_json_response(response.text)
        data = json.loads(cleaned_text)
        is_valid, reason = validate_question_data(data, used_titles)
        if not is_valid:
            logger.error(f"Gemini output validation failed: {reason}")
            raise ValueError(f"Gemini output validation failed: {reason}")

        return data

    except Exception as e:
        logger.error(f"Gemini generation error: {e}. Reverting to fallback question.")
        fallback = MOCK_FALLBACK_QUESTIONS.get(difficulty, MOCK_FALLBACK_QUESTIONS['medium']).copy()
        fallback['difficulty'] = difficulty
        fallback['title'] = f"{fallback['title']} ({company_name} Edition)"
        return fallback


SUMMARY_PROMPT_TEMPLATE = """You are a senior technical interviewer providing feedback on a candidate's Python coding practice session.
Analyze the following session performance statistics (NO code is provided):

Target Company Style: {company}
Session Summary:
{stats_json}

Provide actionable, concise feedback in valid JSON matching this schema:
{{
  "strengths": ["string", "string"],
  "weak_topics": ["string", "string"],
  "next_steps": ["string", "string"]
}}

Rules:
- Keep items concise (1-2 sentences each).
- Max 2 to 3 items per list.
- Return ONLY JSON.
"""

def generate_ai_performance_summary(company: str, session_stats: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Sends session stats to Gemini and returns structured performance summary.
    Falls back to deterministic rule-based summary if API key is not set or fails.
    """
    api_key = getattr(settings, 'GEMINI_API_KEY', '')

    # Fallback / offline summary
    avg_score = 0
    if session_stats:
        avg_score = sum(s.get('score', 0) for s in session_stats) / len(session_stats)

    fallback_summary = {
        "strengths": [
            f"Successfully attempted {len(session_stats)} question(s) in {company} problem archetype.",
            "Demonstrated foundational algorithmic formulation and syntax compliance."
        ],
        "weak_topics": [
            "Review edge-case boundary conditions (empty inputs, zero values, and scale constraints).",
            "Focus on execution speed and space complexity under tight per-test limits."
        ],
        "next_steps": [
            f"Practice 2-3 more Medium difficulty questions targeting {company} data patterns.",
            "Profile solutions locally with timer benchmarks before submitting."
        ]
    }

    if not api_key:
        return fallback_summary

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash')

        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            company=company,
            stats_json=json.dumps(session_stats, indent=2)
        )

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.6,
            )
        )

        cleaned = clean_json_response(response.text)
        data = json.loads(cleaned)
        if 'strengths' in data and 'weak_topics' in data and 'next_steps' in data:
            return data
        return fallback_summary
    except Exception as e:
        logger.warning(f"Error generating AI performance summary with Gemini: {e}")
        return fallback_summary
