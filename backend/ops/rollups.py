"""Hourly rollup updates — called from the ingest path."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import F
from django.utils import timezone

from .models import HourlyRollup, Transaction


def hour_bucket(ts):
    local = timezone.localtime(ts)
    return local.replace(minute=0, second=0, microsecond=0)


def apply_rollup(txn: Transaction) -> HourlyRollup:
    hour_start = hour_bucket(txn.timestamp)
    hour_of_day = hour_start.hour
    rollup, _ = HourlyRollup.objects.get_or_create(
        venue=txn.venue,
        hour_start=hour_start,
        defaults={"hour_of_day": hour_of_day},
    )

    updates: dict = {}
    if txn.type == Transaction.Type.SALE:
        updates = {
            "sales_total": F("sales_total") + Decimal(txn.total),
            "sale_count": F("sale_count") + 1,
        }
    elif txn.type == Transaction.Type.VOID:
        updates = {"void_count": F("void_count") + 1}
    elif txn.type == Transaction.Type.REFUND:
        updates = {"refund_count": F("refund_count") + 1}

    if updates:
        HourlyRollup.objects.filter(pk=rollup.pk).update(**updates)
        rollup.refresh_from_db()
    return rollup
