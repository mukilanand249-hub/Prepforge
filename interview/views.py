import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
from django.db import transaction

from .models import Company, Question, TestCase, Session, SessionQuestion, Submission
from .services.sessions import (
    calculate_difficulty_distribution,
    get_question_time_limit,
    calculate_question_score,
    calculate_session_score,
)
from .services.gemini import generate_question_with_gemini


@login_required
def settings_view(request):
    companies = Company.objects.filter(is_active=True).order_by('name')
    return render(request, 'interview/settings.html', {
        'companies': companies,
    })


@login_required
@require_POST
def create_session_view(request):
    company_id = request.POST.get('company_id')
    difficulty_mode = request.POST.get('difficulty_mode', 'mixed')
    num_questions = int(request.POST.get('num_questions', 3))
    time_limit_override = request.POST.get('time_limit_override')

    company = get_object_or_404(Company, id=company_id, is_active=True)

    # Bound num_questions between 1 and 10
    num_questions = max(1, min(10, num_questions))

    override_mins = None
    if time_limit_override and time_limit_override.strip():
        try:
            val = int(time_limit_override.strip())
            if 5 <= val <= 60:
                override_mins = val
        except ValueError:
            override_mins = None

    with transaction.atomic():
        session = Session.objects.create(
            user=request.user,
            company=company,
            difficulty_mode=difficulty_mode,
            num_questions=num_questions,
            time_limit_override_minutes=override_mins,
            status='in_progress',
            started_at=timezone.now(),
        )

        distribution = calculate_difficulty_distribution(num_questions, difficulty_mode)

        # Pre-create slot SessionQuestions without questions attached yet (lazy generation on demand)
        for idx, diff in enumerate(distribution, start=1):
            time_limit_sec = get_question_time_limit(diff, override_mins)
            # Create a placeholder question container to be filled upon generation
            placeholder_q = Question.objects.create(
                company=company,
                difficulty=diff,
                topic="Pending Generation",
                title=f"Question {idx} (Pending)",
                description="Generating problem specification...",
                function_name="solution",
                starter_code="# Loading...",
                reference_solution="# Loading...",
                status='pending',
            )

            SessionQuestion.objects.create(
                session=session,
                question=placeholder_q,
                order=idx,
                time_limit_seconds=time_limit_sec,
                started_at=timezone.now(),
            )

    return redirect('interview:session_question', session_id=session.id)


@login_required
def session_question_view(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    if session.user != request.user:
        return HttpResponseForbidden("You do not have permission to view this session.")

    if session.status == 'finished':
        return redirect('interview:results', session_id=session.id)

    # Find the current in-progress question
    current_sq = session.session_questions.filter(submitted_at__isnull=True).order_by('order').first()
    if not current_sq:
        # All questions finished
        session.status = 'finished'
        session.finished_at = timezone.now()
        sq_scores = list(session.session_questions.values_list('score', flat=True))
        session.score = calculate_session_score(sq_scores)
        session.save()
        return redirect('interview:results', session_id=session.id)

    return render(request, 'interview/question.html', {
        'session': session,
        'current_sq': current_sq,
        'total_questions': session.num_questions,
        'order': current_sq.order,
    })


@login_required
@require_POST
def next_question_api(request, session_id):
    """
    Returns the question payload for the active slot.
    Generates via Gemini if pending verification.
    """
    session = get_object_or_404(Session, id=session_id)
    if session.user != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    current_sq = session.session_questions.filter(submitted_at__isnull=True).order_by('order').first()
    if not current_sq:
        return JsonResponse({'finished': True})

    question = current_sq.question

    # If pending or not generated yet, generate with Gemini
    if question.status == 'pending' and question.topic == "Pending Generation":
        used_titles = list(
            Question.objects.filter(session_appearances__session=session)
            .exclude(id=question.id)
            .values_list('title', flat=True)
        )

        generated = generate_question_with_gemini(
            company_name=session.company.name,
            style_notes=session.company.style_notes,
            difficulty=question.difficulty,
            used_titles=used_titles,
        )

        with transaction.atomic():
            question.title = generated['title']
            question.topic = generated['topic']
            question.description = generated['description']
            question.constraints = generated.get('constraints', '')
            question.examples = generated.get('examples', [])
            question.function_name = generated['function_name']
            question.starter_code = generated['starter_code']
            question.reference_solution = generated['reference_solution']
            question.status = 'pending'
            question.save()

            # Clear any old test cases and insert generated ones
            question.test_cases.all().delete()
            for tc in generated.get('test_cases', []):
                TestCase.objects.create(
                    question=question,
                    input_json=tc.get('input', []),
                    expected_json=tc.get('expected'),
                    kind=tc.get('kind', 'normal'),
                    is_hidden=tc.get('hidden', False),
                )

    # Format payload
    test_cases_payload = []
    for tc in question.test_cases.all():
        test_cases_payload.append({
            'id': tc.id,
            'input': tc.input_json,
            'expected': tc.expected_json,
            'kind': tc.kind,
            'hidden': tc.is_hidden,
        })

    # Elapsed seconds calculation
    elapsed = int((timezone.now() - current_sq.started_at).total_seconds())
    remaining = max(0, current_sq.time_limit_seconds - elapsed)

    payload = {
        'finished': False,
        'session_id': session.id,
        'session_question_id': current_sq.id,
        'question_id': question.id,
        'order': current_sq.order,
        'total_questions': session.num_questions,
        'company': session.company.name,
        'difficulty': question.difficulty,
        'topic': question.topic,
        'title': question.title,
        'description': question.description,
        'constraints': question.constraints,
        'examples': question.examples,
        'function_name': question.function_name,
        'starter_code': question.starter_code,
        'reference_solution': question.reference_solution, # Used for in-browser verification
        'status': question.status,
        'time_limit_seconds': current_sq.time_limit_seconds,
        'remaining_seconds': remaining,
        'test_cases': test_cases_payload,
    }

    return JsonResponse(payload)


@login_required
@require_POST
def verify_question_api(request, question_id):
    """
    Client reports in-browser verification outcome.
    If passed: question.status = 'verified'.
    If rejected: question.status = 'rejected' and regenerate.
    """
    question = get_object_or_404(Question, id=question_id)

    try:
        body = json.loads(request.body.decode('utf-8'))
        passed = bool(body.get('passed', False))
    except Exception:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    if passed:
        question.status = 'verified'
        question.save()
        return JsonResponse({'status': 'verified', 'message': 'Verification approved'})
    else:
        question.status = 'rejected'
        question.save()

        # Trigger replacement generation
        session_q = question.session_appearances.first()
        if session_q:
            session = session_q.session
            used_titles = list(
                Question.objects.filter(session_appearances__session=session)
                .exclude(id=question.id)
                .values_list('title', flat=True)
            )
            # Generate replacement
            generated = generate_question_with_gemini(
                company_name=session.company.name,
                style_notes=session.company.style_notes,
                difficulty=question.difficulty,
                used_titles=used_titles,
            )
            with transaction.atomic():
                question.title = generated['title']
                question.topic = generated['topic']
                question.description = generated['description']
                question.constraints = generated.get('constraints', '')
                question.examples = generated.get('examples', [])
                question.function_name = generated['function_name']
                question.starter_code = generated['starter_code']
                question.reference_solution = generated['reference_solution']
                question.status = 'pending'
                question.save()

                question.test_cases.all().delete()
                for tc in generated.get('test_cases', []):
                    TestCase.objects.create(
                        question=question,
                        input_json=tc.get('input', []),
                        expected_json=tc.get('expected'),
                        kind=tc.get('kind', 'normal'),
                        is_hidden=tc.get('hidden', False),
                    )

            return JsonResponse({'status': 'retry', 'message': 'Replacement question prepared'})

        return JsonResponse({'status': 'rejected', 'message': 'Question marked rejected'})


@login_required
@require_POST
def submit_question_api(request, session_question_id):
    """
    Submits user code and client execution test results.
    """
    sq = get_object_or_404(SessionQuestion, id=session_question_id)
    if sq.session.user != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        body = json.loads(request.body.decode('utf-8'))
        code = body.get('code', '')
        results = body.get('results', [])
        auto_submitted = bool(body.get('auto_submitted', False))
    except Exception:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    # Size limit on code (50KB)
    if len(code) > 50000:
        return JsonResponse({'error': 'Code payload exceeds size limit (50KB)'}, status=400)

    # Compute tests passed and total
    tests_total = len(results)
    tests_passed = sum(1 for r in results if r.get('passed') is True)
    score = calculate_question_score(tests_passed, tests_total)

    with transaction.atomic():
        sq.submitted_at = timezone.now()
        sq.auto_submitted = auto_submitted
        sq.tests_passed = tests_passed
        sq.tests_total = tests_total
        sq.score = score
        sq.save()

        Submission.objects.create(
            session_question=sq,
            code=code,
            results=results,
            created_at=timezone.now(),
        )

        # Check if more questions remain
        remaining_sq = sq.session.session_questions.filter(submitted_at__isnull=True).order_by('order').first()
        if not remaining_sq:
            # Finalize session
            session = sq.session
            session.status = 'finished'
            session.finished_at = timezone.now()
            all_scores = list(session.session_questions.values_list('score', flat=True))
            session.score = calculate_session_score(all_scores)
            session.save()
            return JsonResponse({
                'finished': True,
                'session_score': session.score,
                'redirect_url': f"/sessions/{session.id}/results/"
            })

    return JsonResponse({
        'finished': False,
        'next_order': remaining_sq.order,
        'score': score
    })


@login_required
def results_view(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    if session.user != request.user:
        return HttpResponseForbidden("You do not have permission to view these results.")

    session_questions = session.session_questions.select_related('question').prefetch_related('submissions').all()

    solved_count = sum(1 for sq in session_questions if sq.score >= 100.0)

    items = []
    for sq in session_questions:
        last_sub = sq.submissions.order_by('-created_at').first()
        time_taken = None
        if sq.submitted_at and sq.started_at:
            time_taken = int((sq.submitted_at - sq.started_at).total_seconds())

        items.append({
            'order': sq.order,
            'title': sq.question.title,
            'difficulty': sq.question.difficulty,
            'topic': sq.question.topic,
            'tests_passed': sq.tests_passed,
            'tests_total': sq.tests_total,
            'score': sq.score,
            'time_taken_seconds': time_taken,
            'auto_submitted': sq.auto_submitted,
            'code': last_sub.code if last_sub else "",
        })

    return render(request, 'interview/results.html', {
        'session': session,
        'solved_count': solved_count,
        'total_count': session.num_questions,
        'items': items,
    })
