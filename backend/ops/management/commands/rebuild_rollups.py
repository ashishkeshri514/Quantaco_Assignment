"""
Rebuild HourlyRollup from Transaction rows (idempotent wipe + rewrite).
"""

from django.core.management.base import BaseCommand

from ops.models import HourlyRollup, Transaction
from ops.rollups import apply_rollup


class Command(BaseCommand):
    help = "Rebuild hourly rollups from all transactions"

    def handle(self, *args, **options):
        HourlyRollup.objects.all().delete()
        count = 0
        for txn in Transaction.objects.select_related("venue").iterator(chunk_size=500):
            apply_rollup(txn)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Rebuilt rollups from {count} transactions"))
