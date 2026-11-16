from django.test import TestCase
from interview.services.gemini import (
    validate_question_data,
    clean_json_response,
    generate_question_with_gemini,
    MOCK_FALLBACK_QUESTIONS,
)


class GeminiServiceValidationTests(TestCase):
    def setUp(self):
        self.valid_question = {
            "title": "Two Sum Target",
            "topic": "Arrays",
            "difficulty": "easy",
            "description": "Find indices of two numbers that add up to target.",
            "constraints": "2 <= len(nums) <= 1000",
            "function_name": "two_sum",
            "starter_code": "def two_sum(nums, target):\n    pass",
            "examples": [
                {"input": [[2, 7, 11], 9], "output": [0, 1], "explanation": "2 + 7 = 9"}
            ],
            "test_cases": [
                {"input": [[2, 7, 11], 9], "expected": [0, 1], "kind": "normal", "hidden": False},
                {"input": [[3, 2, 4], 6], "expected": [1, 2], "kind": "normal", "hidden": False},
                {"input": [[3, 3], 6], "expected": [0, 1], "kind": "normal", "hidden": False},
                {"input": [[0, 4, 3, 0], 0], "expected": [0, 3], "kind": "edge", "hidden": True},
                {"input": [[-1, -2, -3], -5], "expected": [1, 2], "kind": "edge", "hidden": True},
                {"input": [[i for i in range(100)], 197], "expected": [98, 99], "kind": "performance", "hidden": True},
            ],
            "reference_solution": "def two_sum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        if target - n in seen:\n            return [seen[target - n], i]\n        seen[n] = i\n    return []"
        }

    def test_clean_json_response_markdown_fences(self):
        raw = "```json\n{\"test\": 123}\n```"
        self.assertEqual(clean_json_response(raw), '{"test": 123}')

    def test_valid_question_data_passes(self):
        is_valid, reason = validate_question_data(self.valid_question)
        self.assertTrue(is_valid, reason)

    def test_missing_required_field_rejected(self):
        broken = self.valid_question.copy()
        del broken['function_name']
        is_valid, reason = validate_question_data(broken)
        self.assertFalse(is_valid)
        self.assertIn("Missing required field: function_name", reason)

    def test_function_name_mismatch_rejected(self):
        broken = self.valid_question.copy()
        broken['function_name'] = 'different_name'
        is_valid, reason = validate_question_data(broken)
        self.assertFalse(is_valid)
        self.assertIn("not found in starter_code", reason)

    def test_no_edge_cases_rejected(self):
        broken = self.valid_question.copy()
        broken['test_cases'] = [
            {"input": [[1, 2], 3], "expected": [0, 1], "kind": "normal", "hidden": False}
        ] * 6
        is_valid, reason = validate_question_data(broken)
        self.assertFalse(is_valid)
        self.assertIn("at least one 'edge' case", reason)

    def test_forbidden_tokens_rejected(self):
        forbidden_snippets = [
            "import os\ndef two_sum(nums, target): return []",
            "import subprocess\ndef two_sum(nums, target): return []",
            "def two_sum(nums, target):\n    open('/tmp/test', 'w')\n    return []",
            "def two_sum(nums, target):\n    eval('2+2')\n    return []",
            "def two_sum(nums, target):\n    exec('x = 1')\n    return []",
        ]
        for snippet in forbidden_snippets:
            broken = self.valid_question.copy()
            broken['reference_solution'] = snippet
            is_valid, reason = validate_question_data(broken)
            self.assertFalse(is_valid, f"Failed to reject forbidden code: {snippet}")

    def test_unauthorized_module_ast_rejected(self):
        broken = self.valid_question.copy()
        broken['reference_solution'] = "import socket\ndef two_sum(nums, target): return []"
        is_valid, reason = validate_question_data(broken)
        self.assertFalse(is_valid)

    def test_duplicate_title_rejected(self):
        used_titles = ["Two Sum Target", "Other Problem"]
        is_valid, reason = validate_question_data(self.valid_question, used_titles=used_titles)
        self.assertFalse(is_valid)
        self.assertIn("Duplicate title", reason)

    def test_mock_fallback_question_generation(self):
        # When called without API key, must return validated high-fidelity question
        res = generate_question_with_gemini(
            company_name="Zoho",
            style_notes="Logic-heavy pattern problems",
            difficulty="medium",
        )
        self.assertIn("title", res)
        self.assertEqual(res["difficulty"], "medium")
        is_valid, reason = validate_question_data(res)
        self.assertTrue(is_valid, reason)
