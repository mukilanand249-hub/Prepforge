from django.utils import timezone
from django.conf import settings
from interview.models import GenerationUsage


def check_and_increment_daily_limit(user) -> tuple[bool, int, int]:
    """
    Checks if user is within their daily Gemini question generation limit.
    If within limit, increments counter and returns (True, current_count, max_limit).
    If limit reached, returns (False, current_count, max_limit).
    """
    today = timezone.localdate() if timezone.is_aware(timezone.now()) else timezone.now().date()
    max_limit = getattr(settings, 'DAILY_GENERATION_LIMIT', 20)

    usage, _ = GenerationUsage.objects.get_or_create(
        user=user,
        date=today,
        defaults={'count': 0}
    )

    if usage.count >= max_limit:
        return False, usage.count, max_limit

    usage.count += 1
    usage.save(update_fields=['count'])
    return True, usage.count, max_limit


def get_user_daily_usage(user) -> tuple[int, int]:
    """
    Returns (current_count, max_limit) for today.
    """
    today = timezone.localdate() if timezone.is_aware(timezone.now()) else timezone.now().date()
    max_limit = getattr(settings, 'DAILY_GENERATION_LIMIT', 20)
    usage = GenerationUsage.objects.filter(user=user, date=today).first()
    current = usage.count if usage else 0
    return current, max_limit
