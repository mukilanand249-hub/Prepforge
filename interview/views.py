import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from django.db.models import Avg, Count

from .models import Company, Question, TestCase, Session, SessionQuestion, Submission
from .services.sessions import (
    calculate_difficulty_distribution,
    get_question_time_limit,
    calculate_question_score,
    calculate_session_score,
)
from .services.gemini import (
    generate_question_with_gemini,
    generate_ai_performance_summary,
)
from .services.limits import (
    check_and_increment_daily_limit,
    get_user_daily_usage,
)
from .services.bank import (
    fetch_verified_question_from_bank,
    save_verified_question_to_bank,
)


@login_required
def settings_view(request):
    companies = Company.objects.filter(is_active=True).order_by('name')
    usage_count, max_limit = get_user_daily_usage(request.user)
    return render(request, 'interview/settings.html', {
        'companies': companies,
        'daily_usage': usage_count,
        'daily_limit': max_limit,
    })


@login_required
@require_POST
def create_session_view(request):
    company_id = request.POST.get('company_id')
    custom_company_name = request.POST.get('custom_company_name', '').strip()
    custom_style_notes = request.POST.get('custom_style_notes', '').strip()
    difficulty_mode = request.POST.get('difficulty_mode', 'mixed')
    num_questions = int(request.POST.get('num_questions', 3))
    time_limit_override = request.POST.get('time_limit_override')

    if company_id == 'custom' or custom_company_name:
        if not custom_company_name:
            custom_company_name = "Custom Company"
        company, _ = Company.objects.get_or_create(
            name=custom_company_name,
            defaults={
                'style_notes': custom_style_notes or f"Practical software engineering scenarios inspired by {custom_company_name}.",
                'is_active': True,
            }
        )
    else:
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

        for idx, diff in enumerate(distribution, start=1):
            time_limit_sec = get_question_time_limit(diff, override_mins)
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

    current_sq = session.session_questions.filter(submitted_at__isnull=True).order_by('order').first()
    if not current_sq:
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
    Returns question payload for active slot.
    Turso-first strategy: checks question bank first, falls back to Gemini if needed.
    """
    session = get_object_or_404(Session, id=session_id)
    if session.user != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    current_sq = session.session_questions.filter(submitted_at__isnull=True).order_by('order').first()
    if not current_sq:
        return JsonResponse({'finished': True})

    question = current_sq.question

    if question.status == 'pending' and question.topic == "Pending Generation":
        used_titles = list(
            Question.objects.filter(session_appearances__session=session)
            .exclude(id=question.id)
            .values_list('title', flat=True)
        )

        # 1. Turso Question Bank Check
        bank_question = fetch_verified_question_from_bank(
            company=session.company.name,
            difficulty=question.difficulty,
            exclude_titles=used_titles
        )

        if bank_question:
            # Served from Turso question bank
            with transaction.atomic():
                question.title = bank_question['title']
                question.topic = bank_question['topic']
                question.description = bank_question['description']
                question.constraints = bank_question.get('constraints', '')
                question.examples = bank_question.get('examples', [])
                question.function_name = bank_question['function_name']
                question.starter_code = bank_question['starter_code']
                question.reference_solution = bank_question['reference_solution']
                question.source = 'bank'
                question.bank_id = bank_question.get('bank_id')
                question.status = 'verified' # Pre-verified from bank
                question.save()

                question.test_cases.all().delete()
                for tc in bank_question.get('test_cases', []):
                    TestCase.objects.create(
                        question=question,
                        input_json=tc.get('input', []),
                        expected_json=tc.get('expected'),
                        kind=tc.get('kind', 'normal'),
                        is_hidden=tc.get('hidden', False),
                    )
        else:
            # 2. Check Daily Generation Limit before Gemini call
            allowed, count, limit = check_and_increment_daily_limit(request.user)
            if not allowed:
                return JsonResponse({
                    'error': f'Daily generation limit reached ({limit}/{limit}). You can continue practicing with questions from the question bank.',
                    'limit_reached': True
                }, status=429)

            # 3. Gemini Generation
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
                question.source = 'gemini'
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

    test_cases_payload = []
    for tc in question.test_cases.all():
        test_cases_payload.append({
            'id': tc.id,
            'input': tc.input_json,
            'expected': tc.expected_json,
            'kind': tc.kind,
            'hidden': tc.is_hidden,
        })

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
        'reference_solution': question.reference_solution,
        'status': question.status,
        'source': question.source,
        'time_limit_seconds': current_sq.time_limit_seconds,
        'remaining_seconds': remaining,
        'test_cases': test_cases_payload,
    }

    return JsonResponse(payload)


@login_required
@require_POST
def verify_question_api(request, question_id):
    question = get_object_or_404(Question, id=question_id)

    try:
        body = json.loads(request.body.decode('utf-8'))
        passed = bool(body.get('passed', False))
    except Exception:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    if passed:
        question.status = 'verified'
        question.save()

        # Phase 2: Cache verified question in Turso question bank asynchronously
        try:
            save_verified_question_to_bank(
                company=question.company.name,
                data={
                    'difficulty': question.difficulty,
                    'topic': question.topic,
                    'title': question.title,
                    'description': question.description,
                    'constraints': question.constraints,
                    'examples': question.examples,
                    'function_name': question.function_name,
                    'starter_code': question.starter_code,
                    'reference_solution': question.reference_solution,
                    'test_cases': [
                        {
                            'input': tc.input_json,
                            'expected': tc.expected_json,
                            'kind': tc.kind,
                            'hidden': tc.is_hidden
                        } for tc in question.test_cases.all()
                    ]
                }
            )
        except Exception:
            pass

        return JsonResponse({'status': 'verified', 'message': 'Verification approved'})
    else:
        question.status = 'rejected'
        question.save()

        session_q = question.session_appearances.first()
        if session_q:
            session = session_q.session
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

    if len(code) > 50000:
        return JsonResponse({'error': 'Code payload exceeds size limit (50KB)'}, status=400)

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

        remaining_sq = sq.session.session_questions.filter(submitted_at__isnull=True).order_by('order').first()
        if not remaining_sq:
            session = sq.session
            session.status = 'finished'
            session.finished_at = timezone.now()
            all_scores = list(session.session_questions.values_list('score', flat=True))
            session.score = calculate_session_score(all_scores)

            # Generate Phase 2 AI Performance Summary
            session_stats = []
            for item in session.session_questions.select_related('question').all():
                session_stats.append({
                    'title': item.question.title,
                    'topic': item.question.topic,
                    'difficulty': item.question.difficulty,
                    'tests_passed': item.tests_passed,
                    'tests_total': item.tests_total,
                    'score': item.score,
                    'auto_submitted': item.auto_submitted,
                    'time_seconds': int((item.submitted_at - item.started_at).total_seconds()) if item.submitted_at else None
                })
            try:
                session.ai_summary = generate_ai_performance_summary(session.company.name, session_stats)
            except Exception:
                pass

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
@require_POST
def session_summary_api(request, session_id):
    """
    On-demand AI performance summary generation or retry.
    """
    session = get_object_or_404(Session, id=session_id)
    if session.user != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    session_stats = []
    for item in session.session_questions.select_related('question').all():
        session_stats.append({
            'title': item.question.title,
            'topic': item.question.topic,
            'difficulty': item.question.difficulty,
            'tests_passed': item.tests_passed,
            'tests_total': item.tests_total,
            'score': item.score,
            'auto_submitted': item.auto_submitted,
            'time_seconds': int((item.submitted_at - item.started_at).total_seconds()) if item.submitted_at else None
        })

    summary = generate_ai_performance_summary(session.company.name, session_stats)
    session.ai_summary = summary
    session.save(update_fields=['ai_summary'])
    return JsonResponse({'success': True, 'ai_summary': summary})


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
        'ai_summary': session.ai_summary,
    })


@login_required
def dashboard_view(request):
    """
    Phase 2: History dashboard with score trend, accuracy per topic, and stats.
    """
    user_sessions = Session.objects.filter(user=request.user, status='finished').order_by('started_at')

    # Chart 1: Score over time
    dates = []
    scores = []
    for s in user_sessions:
        dates.append(s.started_at.strftime("%b %d, %H:%M"))
        scores.append(s.score if s.score is not None else 0.0)

    # Chart 2: Accuracy per topic
    topic_aggregates = (
        SessionQuestion.objects.filter(session__user=request.user, session__status='finished')
        .values('question__topic')
        .annotate(avg_score=Avg('score'), total=Count('id'))
        .order_by('-total')[:8]
    )

    topics = [item['question__topic'] for item in topic_aggregates]
    topic_scores = [round(item['avg_score'], 1) for item in topic_aggregates]

    # Stats
    total_sessions = user_sessions.count()
    avg_session_score = user_sessions.aggregate(Avg('score'))['score__avg'] or 0.0

    all_sqs = SessionQuestion.objects.filter(session__user=request.user, session__status='finished')
    auto_submit_count = all_sqs.filter(auto_submitted=True).count()
    auto_submit_rate = round((auto_submit_count / all_sqs.count() * 100), 1) if all_sqs.exists() else 0.0

    recent_sessions = user_sessions.order_by('-started_at')[:10]

    return render(request, 'interview/dashboard.html', {
        'total_sessions': total_sessions,
        'avg_session_score': round(avg_session_score, 1),
        'auto_submit_rate': auto_submit_rate,
        'recent_sessions': recent_sessions,
        'chart_dates_json': json.dumps(dates),
        'chart_scores_json': json.dumps(scores),
        'chart_topics_json': json.dumps(topics),
        'chart_topic_scores_json': json.dumps(topic_scores),
    })
