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


def get_user_excluded_question_titles(user, current_session=None, exclude_question_id=None) -> List[str]:
    """
    Returns question titles that must not be served to this user:
    1. Any question the user has already solved (score >= 100.0 or 100% tests passed) across any session.
    2. Any question already assigned in the current session.
    """
    from django.db.models import F, Q
    from ..models import SessionQuestion, Question

    excluded = set()

    if user and user.is_authenticated:
        # Questions successfully solved by the user across any previous or current session
        solved_sqs = (
            SessionQuestion.objects.filter(session__user=user)
            .filter(Q(score__gte=100.0) | (Q(tests_total__gt=0) & Q(tests_passed=F('tests_total'))))
            .exclude(question__topic="Pending Generation")
            .select_related('question')
        )
        for sq in solved_sqs:
            if sq.question and sq.question.title:
                t = sq.question.title.strip()
                if t and not t.startswith("Question "):
                    excluded.add(t)

    # Questions already in the current session (to avoid duplicate questions within the same session)
    if current_session:
        qs_in_session = Question.objects.filter(session_appearances__session=current_session)
        if exclude_question_id:
            qs_in_session = qs_in_session.exclude(id=exclude_question_id)
        for t in qs_in_session.exclude(topic="Pending Generation").values_list('title', flat=True):
            if t:
                cleaned = t.strip()
                if cleaned and not cleaned.startswith("Question "):
                    excluded.add(cleaned)

    return list(excluded)
