from django.core.management.base import BaseCommand
from interview.models import Company

DEFAULT_COMPANIES = [
    {
        "name": "Zoho",
        "style_notes": "Logic-heavy, string/array manipulation, pattern and simulation problems. Emphasizes clean algorithmic flow and corner-case handling without relying on heavy external libraries.",
    },
    {
        "name": "Freshworks",
        "style_notes": "Practical data-handling, nested dictionaries, API-style payloads, and customer-ticket scenarios. Realistic business logic and parsing.",
    },
    {
        "name": "Razorpay",
        "style_notes": "Payments/FinTech scenarios: transactions, double-entry ledgers, sliding window rate limits, and currency reconciliation.",
    },
    {
        "name": "PhonePe",
        "style_notes": "UPI-style transaction processing, validation, routing, idempotency, and high-frequency balance aggregation.",
    },
    {
        "name": "TCS / Infosys",
        "style_notes": "Core fundamentals: strings, lists, matrix traversal, basic math, search, and sorting. Clear procedural problem-solving.",
    },
    {
        "name": "Amazon",
        "style_notes": "Data structures, hash maps, two pointers, sliding windows, graphs, and algorithmic time/space optimization.",
    },
]


class Command(BaseCommand):
    help = "Seeds initial company records with authentic interview style notes"

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        for data in DEFAULT_COMPANIES:
            company, created = Company.objects.update_or_create(
                name=data["name"],
                defaults={
                    "style_notes": data["style_notes"],
                    "is_active": True,
                }
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created company: {company.name}"))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"Updated company: {company.name}"))

        self.stdout.write(self.style.SUCCESS(f"Seeding finished. ({created_count} created, {updated_count} updated)"))
