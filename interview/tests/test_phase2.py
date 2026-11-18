from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from interview.models import Company, Session, SessionQuestion, Question, GenerationUsage
from interview.services.limits import check_and_increment_daily_limit, get_user_daily_usage
from interview.services.gemini import generate_ai_performance_summary


class Phase2FeatureTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='carol', password='password123')
        self.client.login(username='carol', password='password123')

    def test_daily_generation_limits(self):
        # Initial usage is 0
        current, max_limit = get_user_daily_usage(self.user)
        self.assertEqual(current, 0)
        self.assertEqual(max_limit, 20)

        # Increment up to limit
        for i in range(1, 21):
            allowed, count, limit = check_and_increment_daily_limit(self.user)
            self.assertTrue(allowed)
            self.assertEqual(count, i)

        # 21st call should be rejected
        allowed, count, limit = check_and_increment_daily_limit(self.user)
        self.assertFalse(allowed)
        self.assertEqual(count, 20)

    def test_ai_performance_summary_schema(self):
        stats = [
            {'title': 'Problem 1', 'topic': 'Arrays', 'difficulty': 'easy', 'tests_passed': 4, 'tests_total': 4, 'score': 100.0, 'auto_submitted': False, 'time_seconds': 120},
            {'title': 'Problem 2', 'topic': 'DP', 'difficulty': 'medium', 'tests_passed': 2, 'tests_total': 4, 'score': 50.0, 'auto_submitted': True, 'time_seconds': 300},
        ]
        summary = generate_ai_performance_summary('Zoho', stats)
        self.assertIn('strengths', summary)
        self.assertIn('weak_topics', summary)
        self.assertIn('next_steps', summary)
        self.assertIsInstance(summary['strengths'], list)
        self.assertIsInstance(summary['weak_topics'], list)
        self.assertIsInstance(summary['next_steps'], list)

    def test_custom_company_session_creation(self):
        resp = self.client.post(reverse('interview:create_session'), {
            'company_id': 'custom',
            'custom_company_name': 'Stripe',
            'custom_style_notes': 'Payment webhooks and idempotent charges',
            'difficulty_mode': 'hard',
            'num_questions': 2,
        })
        self.assertEqual(resp.status_code, 302)
        company = Company.objects.filter(name='Stripe').first()
        self.assertIsNotNone(company)
        self.assertIn('Payment webhooks', company.style_notes)

        session = Session.objects.filter(user=self.user, company=company).first()
        self.assertIsNotNone(session)
        self.assertEqual(session.difficulty_mode, 'hard')
        self.assertEqual(session.num_questions, 2)

    def test_dashboard_view_renders_cleanly(self):
        # Create a finished session
        comp = Company.objects.create(name='Amazon', style_notes='Algorithms')
        session = Session.objects.create(
            user=self.user,
            company=comp,
            difficulty_mode='medium',
            num_questions=1,
            status='finished',
            score=90.0
        )
        q = Question.objects.create(
            company=comp,
            difficulty='medium',
            topic='Hash Maps',
            title='Two Sum',
            function_name='solve',
            starter_code='def solve(): pass',
            reference_solution='def solve(): pass',
            status='verified'
        )
        SessionQuestion.objects.create(
            session=session,
            question=q,
            order=1,
            tests_passed=9,
            tests_total=10,
            score=90.0,
            auto_submitted=False
        )

        resp = self.client.get(reverse('interview:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Amazon')
        self.assertContains(resp, 'Hash Maps')
        self.assertContains(resp, 'CANDIDATE TELEMETRY & HISTORICAL ANALYTICS')
