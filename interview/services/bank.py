import json
import logging
from typing import Optional, Dict, Any, List
from django.conf import settings

logger = logging.getLogger(__name__)

TURSO_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE IF NOT EXISTS test_cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id INTEGER NOT NULL REFERENCES questions(id),
  input_json TEXT NOT NULL,
  expected_json TEXT NOT NULL,
  kind TEXT NOT NULL,
  is_hidden INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_questions_lookup ON questions(company, difficulty);
"""


def get_turso_client():
    url = getattr(settings, 'TURSO_DATABASE_URL', '')
    token = getattr(settings, 'TURSO_AUTH_TOKEN', '')
    if not url or not token:
        return None

    try:
        import libsql_client
        return libsql_client.create_client_sync(url=url, auth_token=token)
    except Exception as e:
        logger.warning(f"Could not initialize Turso client: {e}")
        return None


def fetch_verified_question_from_bank(company: str, difficulty: str, exclude_titles: List[str] = None) -> Optional[Dict[str, Any]]:
    """
    Attempts to retrieve an unseen verified question from Turso question bank.
    Returns parsed question dict matching the Gemini schema, or None if unavailable.
    """
    client = get_turso_client()
    if not client:
        return None

    exclude_titles = exclude_titles or []
    try:
        query = "SELECT id, title, topic, description, constraints, examples_json, function_name, starter_code, reference_solution FROM questions WHERE company = ? AND difficulty = ? AND verified = 1"
        res = client.execute(query, [company, difficulty])

        for row in res.rows:
            q_id = row[0]
            title = row[1]
            if title in exclude_titles:
                continue

            # Fetch test cases for this question
            tc_res = client.execute(
                "SELECT input_json, expected_json, kind, is_hidden FROM test_cases WHERE question_id = ?",
                [q_id]
            )
            test_cases = []
            for tc in tc_res.rows:
                test_cases.append({
                    "input": json.loads(tc[0]),
                    "expected": json.loads(tc[1]),
                    "kind": tc[2],
                    "hidden": bool(tc[3])
                })

            return {
                "bank_id": q_id,
                "title": title,
                "topic": row[2],
                "difficulty": difficulty,
                "description": row[3],
                "constraints": row[4] or "",
                "examples": json.loads(row[5]) if row[5] else [],
                "function_name": row[6],
                "starter_code": row[7],
                "reference_solution": row[8],
                "test_cases": test_cases,
                "source": "bank"
            }

        return None
    except Exception as e:
        logger.warning(f"Error querying Turso question bank: {e}")
        return None


def save_verified_question_to_bank(company: str, data: Dict[str, Any]) -> Optional[int]:
    """
    Saves a newly verified question and its test cases to Turso.
    """
    client = get_turso_client()
    if not client:
        return None

    try:
        insert_q = """
        INSERT INTO questions (company, difficulty, topic, title, description, constraints, examples_json, function_name, starter_code, reference_solution, verified, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))
        """
        res = client.execute(insert_q, [
            company,
            data.get('difficulty', 'medium'),
            data.get('topic', 'Algorithms'),
            data.get('title'),
            data.get('description'),
            data.get('constraints', ''),
            json.dumps(data.get('examples', [])),
            data.get('function_name'),
            data.get('starter_code'),
            data.get('reference_solution')
        ])

        q_id = res.last_insert_rowid
        for tc in data.get('test_cases', []):
            client.execute(
                "INSERT INTO test_cases (question_id, input_json, expected_json, kind, is_hidden) VALUES (?, ?, ?, ?, ?)",
                [
                    q_id,
                    json.dumps(tc.get('input', [])),
                    json.dumps(tc.get('expected')),
                    tc.get('kind', 'normal'),
                    1 if tc.get('hidden') else 0
                ]
            )

        logger.info(f"Successfully cached verified question '{data.get('title')}' in Turso (ID: {q_id})")
        return q_id
    except Exception as e:
        logger.warning(f"Failed to cache question to Turso: {e}")
        return None
