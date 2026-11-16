import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from interview.models import Company, Session, SessionQuestion, Question, TestCase as ModelTestCase, Submission


class InterviewViewsAndApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='alice', password='password123')
        self.user2 = User.objects.create_user(username='bob', password='password123')

        self.company = Company.objects.create(
            name="Razorpay",
            style_notes="FinTech transactions and ledgers",
            is_active=True
        )

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(reverse('interview:settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_create_session(self):
        self.client.login(username='alice', password='password123')
        response = self.client.post(reverse('interview:create_session'), {
            'company_id': self.company.id,
            'difficulty_mode': 'mixed',
            'num_questions': 3,
            'time_limit_override': '15',
        })
        self.assertEqual(response.status_code, 302)
        session = Session.objects.filter(user=self.user1).first()
        self.assertIsNotNone(session)
        self.assertEqual(session.num_questions, 3)
        self.assertEqual(session.time_limit_override_minutes, 15)
        self.assertEqual(session.session_questions.count(), 3)

    def test_tenant_isolation_unauthorized_user_forbidden(self):
        # Alice creates a session
        session = Session.objects.create(
            user=self.user1,
            company=self.company,
            difficulty_mode='easy',
            num_questions=1,
            status='in_progress',
        )

        # Bob logs in and tries to access Alice's session
        self.client.login(username='bob', password='password123')
        response = self.client.get(reverse('interview:session_question', kwargs={'session_id': session.id}))
        self.assertEqual(response.status_code, 403)

        api_response = self.client.post(reverse('interview:next_question_api', kwargs={'session_id': session.id}))
        self.assertEqual(api_response.status_code, 403)

    def test_next_question_api_and_verification_flow(self):
        self.client.login(username='alice', password='password123')

        # Create session
        session = Session.objects.create(
            user=self.user1,
            company=self.company,
            difficulty_mode='easy',
            num_questions=1,
            status='in_progress',
        )
        q = Question.objects.create(
            company=self.company,
            difficulty='easy',
            topic="Pending Generation",
            title="Placeholder",
            function_name="sol",
            starter_code="# Code",
            reference_solution="# Ref",
            status='pending',
        )
        sq = SessionQuestion.objects.create(
            session=session,
            question=q,
            order=1,
            time_limit_seconds=600,
        )

        # Call next question API -> generates question
        resp = self.client.post(reverse('interview:next_question_api', kwargs={'session_id': session.id}))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['finished'])
        self.assertIn('reference_solution', data)
        self.assertIn('test_cases', data)

        # Report verification approved
        verify_resp = self.client.post(
            reverse('interview:verify_question_api', kwargs={'question_id': q.id}),
            data=json.dumps({'passed': True}),
            content_type='application/json'
        )
        self.assertEqual(verify_resp.status_code, 200)
        q.refresh_from_db()
        self.assertEqual(q.status, 'verified')

    def test_submit_question_api_scoring_and_completion(self):
        self.client.login(username='alice', password='password123')

        session = Session.objects.create(
            user=self.user1,
            company=self.company,
            difficulty_mode='easy',
            num_questions=1,
            status='in_progress',
        )
        q = Question.objects.create(
            company=self.company,
            difficulty='easy',
            topic="Arrays",
            title="Sum Problem",
            function_name="solve",
            starter_code="def solve(): pass",
            reference_solution="def solve(): return 10",
            status='verified',
        )
        sq = SessionQuestion.objects.create(
            session=session,
            question=q,
            order=1,
            time_limit_seconds=600,
        )

        # Submit 3 passed test cases out of 4 (75% score)
        results = [
            {"index": 0, "passed": True, "actual": 10, "error": None, "ms": 2},
            {"index": 1, "passed": True, "actual": 10, "error": None, "ms": 2},
            {"index": 2, "passed": True, "actual": 10, "error": None, "ms": 2},
            {"index": 3, "passed": False, "actual": 9, "error": "Mismatch", "ms": 2},
        ]

        resp = self.client.post(
            reverse('interview:submit_question_api', kwargs={'session_question_id': sq.id}),
            data=json.dumps({
                'code': 'def solve(): return 10',
                'results': results,
                'auto_submitted': False
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['finished'])
        self.assertEqual(data['session_score'], 75.0)

        sq.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(sq.tests_passed, 3)
        self.assertEqual(sq.tests_total, 4)
        self.assertEqual(sq.score, 75.0)
        self.assertEqual(session.status, 'finished')
        self.assertEqual(session.score, 75.0)
