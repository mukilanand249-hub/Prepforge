import math
from typing import List, Tuple

DEFAULT_TIMES_SECONDS = {
    'easy': 10 * 60,      # 10 minutes
    'medium': 20 * 60,    # 20 minutes
    'hard': 35 * 60,      # 35 minutes
}


def calculate_difficulty_distribution(num_questions: int, difficulty_mode: str) -> List[str]:
    """
    Returns an ordered list of difficulties for the session questions.
    For fixed difficulties ('easy', 'medium', 'hard'), returns [mode] * n.
    For 'mixed':
      - hard = round(0.2 * n)
      - easy = round(0.4 * n)
      - medium = n - easy - hard
      - Special case: if n == 1 -> ['medium']
      - Ordering: easy -> medium -> hard
    """
    if difficulty_mode in ('easy', 'medium', 'hard'):
        return [difficulty_mode] * num_questions

    if num_questions <= 1:
        return ['medium']

    hard = round(0.2 * num_questions)
    easy = round(0.4 * num_questions)
    medium = num_questions - easy - hard

    # Guard against rounding anomalies
    if medium < 0:
        medium = 0
        if easy + hard > num_questions:
            easy = num_questions - hard

    distribution = (['easy'] * easy) + (['medium'] * medium) + (['hard'] * hard)
    return distribution


def get_question_time_limit(difficulty: str, override_minutes: int | None = None) -> int:
    """
    Computes time limit in seconds for a question.
    Custom override applies uniformly if provided (in minutes).
    Otherwise default per difficulty applies.
    """
    if override_minutes and override_minutes > 0:
        return int(override_minutes * 60)
    return DEFAULT_TIMES_SECONDS.get(difficulty, 20 * 60)


def calculate_question_score(tests_passed: int, tests_total: int) -> float:
    """
    Computes percentage score for a single question.
    """
    if tests_total <= 0:
        return 0.0
    return round((tests_passed / tests_total) * 100.0, 2)


def calculate_session_score(scores: List[float]) -> float:
    """
    Computes session average score.
    """
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 2)
