"""
Clear transactional data for a clean demo run.
Keeps venues and the ops user.
"""

from django.core.management.base import BaseCommand

from ops.models import (
    AlertAcknowledgement,
    DeadLetterPayload,
    HourlyRollup,
    Transaction,
)


class Command(BaseCommand):
    help = "Delete transactions, rollups, dead letters, and alert acks (keeps venues/users)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip confirmation prompt",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            self.stdout.write("Pass --yes to confirm wipe of transactional data.")
            return

        counts = {
            "transactions": Transaction.objects.count(),
            "rollups": HourlyRollup.objects.count(),
            "dead_letters": DeadLetterPayload.objects.count(),
            "alert_acks": AlertAcknowledgement.objects.count(),
        }
        Transaction.objects.all().delete()
        HourlyRollup.objects.all().delete()
        DeadLetterPayload.objects.all().delete()
        AlertAcknowledgement.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                "Cleared "
                f"transactions={counts['transactions']}, "
                f"rollups={counts['rollups']}, "
                f"dead_letters={counts['dead_letters']}, "
                f"alert_acks={counts['alert_acks']}"
            )
        )
