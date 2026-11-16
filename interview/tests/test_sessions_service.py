from django.test import TestCase
from interview.services.sessions import (
    calculate_difficulty_distribution,
    get_question_time_limit,
    calculate_question_score,
    calculate_session_score,
)


class SessionServiceUnitTests(TestCase):
    def test_mixed_mode_distribution_n1_to_n10(self):
        # Spec Rule: For n = 1, use medium
        self.assertEqual(calculate_difficulty_distribution(1, 'mixed'), ['medium'])

        # For n = 2..10: verify exact distribution counts and ordering (easy -> medium -> hard)
        for n in range(2, 11):
            dist = calculate_difficulty_distribution(n, 'mixed')
            self.assertEqual(len(dist), n, f"Failed length check for n={n}")
            
            # Verify ordering: easy before medium before hard
            seen_medium = False
            seen_hard = False
            for diff in dist:
                if diff == 'medium':
                    seen_medium = True
                elif diff == 'hard':
                    seen_hard = True
                elif diff == 'easy':
                    self.assertFalse(seen_medium, f"Easy found after medium in n={n}")
                    self.assertFalse(seen_hard, f"Easy found after hard in n={n}")

        # Test specific known values
        # n = 3: hard=round(0.6)=1, easy=round(1.2)=1, medium=3-1-1=1 -> ['easy', 'medium', 'hard']
        self.assertEqual(calculate_difficulty_distribution(3, 'mixed'), ['easy', 'medium', 'hard'])
        # n = 5: hard=round(1.0)=1, easy=round(2.0)=2, medium=5-2-1=2 -> ['easy', 'easy', 'medium', 'medium', 'hard']
        self.assertEqual(calculate_difficulty_distribution(5, 'mixed'), ['easy', 'easy', 'medium', 'medium', 'hard'])

    def test_fixed_difficulty_distributions(self):
        self.assertEqual(calculate_difficulty_distribution(4, 'easy'), ['easy'] * 4)
        self.assertEqual(calculate_difficulty_distribution(3, 'medium'), ['medium'] * 3)
        self.assertEqual(calculate_difficulty_distribution(2, 'hard'), ['hard'] * 2)

    def test_time_limit_calculation(self):
        # Defaults: Easy 10m (600s), Medium 20m (1200s), Hard 35m (2100s)
        self.assertEqual(get_question_time_limit('easy'), 600)
        self.assertEqual(get_question_time_limit('medium'), 1200)
        self.assertEqual(get_question_time_limit('hard'), 2100)

        # Custom override in minutes
        self.assertEqual(get_question_time_limit('easy', override_minutes=15), 900)
        self.assertEqual(get_question_time_limit('hard', override_minutes=45), 2700)

    def test_question_scoring_math(self):
        self.assertEqual(calculate_question_score(10, 10), 100.0)
        self.assertEqual(calculate_question_score(5, 10), 50.0)
        self.assertEqual(calculate_question_score(1, 3), 33.33)
        self.assertEqual(calculate_question_score(0, 5), 0.0)
        self.assertEqual(calculate_question_score(0, 0), 0.0)

    def test_session_score_math(self):
        # 7 full solves (100) and 3 half-solves (50) out of 10 = 85.0
        scores = [100.0] * 7 + [50.0] * 3
        self.assertEqual(calculate_session_score(scores), 85.0)

        # Empty session returns 0.0
        self.assertEqual(calculate_session_score([]), 0.0)
