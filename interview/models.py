from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Company(models.Model):
    name = models.CharField(max_length=100, unique=True)
    style_notes = models.TextField(help_text="Guidance injected into the Gemini prompt to reflect company interview style")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Companies"
        ordering = ['name']

    def __str__(self):
        return self.name


class Question(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    SOURCE_CHOICES = [
        ('gemini', 'Gemini Generated'),
        ('bank', 'Question Bank'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='questions')
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)
    topic = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    description = models.TextField()
    constraints = models.TextField(blank=True, default='')
    examples = models.JSONField(default=list, help_text="List of example objects with input, output, explanation")
    function_name = models.CharField(max_length=100)
    starter_code = models.TextField()
    reference_solution = models.TextField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='gemini')
    bank_id = models.IntegerField(null=True, blank=True, help_text="ID in Turso question bank if synced")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'difficulty', 'status']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"[{self.difficulty.upper()}] {self.title} ({self.company.name})"


class TestCase(models.Model):
    KIND_CHOICES = [
        ('normal', 'Normal'),
        ('edge', 'Edge Case'),
        ('performance', 'Performance'),
    ]

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='test_cases')
    input_json = models.JSONField(help_text="JSON list of positional arguments to pass to the function")
    expected_json = models.JSONField(help_text="JSON expected return value")
    kind = models.CharField(max_length=15, choices=KIND_CHOICES, default='normal')
    is_hidden = models.BooleanField(default=False)

    def __str__(self):
        visibility = "Hidden" if self.is_hidden else "Visible"
        return f"TestCase #{self.id} for {self.question.title} ({self.kind}, {visibility})"


class Session(models.Model):
    DIFFICULTY_MODE_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
        ('mixed', 'Mixed'),
    ]

    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('finished', 'Finished'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interview_sessions')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='sessions')
    difficulty_mode = models.CharField(max_length=10, choices=DIFFICULTY_MODE_CHOICES, default='mixed')
    num_questions = models.PositiveSmallIntegerField(default=3)
    time_limit_override_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='in_progress')
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True, help_text="Average percentage score across questions")
    ai_summary = models.JSONField(null=True, blank=True, help_text="Strengths, weak topics, and next steps")

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Session #{self.id} - {self.user.username} ({self.company.name}, {self.difficulty_mode})"


class SessionQuestion(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='session_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='session_appearances')
    order = models.PositiveSmallIntegerField(default=1)
    time_limit_seconds = models.PositiveIntegerField(default=1200)
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    auto_submitted = models.BooleanField(default=False)
    tests_passed = models.PositiveSmallIntegerField(default=0)
    tests_total = models.PositiveSmallIntegerField(default=0)
    score = models.FloatField(default=0.0, help_text="Percentage score (tests_passed / tests_total * 100)")

    class Meta:
        ordering = ['order']
        unique_together = ('session', 'order')

    def __str__(self):
        return f"Session #{self.session.id} - Q{self.order}: {self.question.title}"


class Submission(models.Model):
    session_question = models.ForeignKey(SessionQuestion, on_delete=models.CASCADE, related_name='submissions')
    code = models.TextField()
    results = models.JSONField(default=list, help_text="Array of per-test results: index, passed, actual, error, ms")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Submission for {self.session_question} at {self.created_at}"


class GenerationUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generation_usages')
    date = models.DateField(default=timezone.now)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('user', 'date')
        verbose_name_plural = "Generation Usages"

    def __str__(self):
        return f"{self.user.username} - {self.date}: {self.count} generations"
