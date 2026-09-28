"""
Dashboard aggregation and anomaly detection.

Reads prefer HourlyRollup (updated on ingest). Top items still come from line items.
Alerts compare last-hour sales to a daypart baseline (same hour_of_day historically),
falling back to the prior hour when history is thin.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from .models import AlertAcknowledgement, HourlyRollup, Transaction, TransactionItem, Venue
from .rollups import hour_bucket


def _day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or timezone.now()
    local = timezone.localtime(now)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _money(value: Decimal | int | float | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _active_acks(now: datetime | None = None) -> set[tuple[int, str]]:
    now = now or timezone.now()
    return {
        (row.venue_id, row.alert_type)
        for row in AlertAcknowledgement.objects.filter(expires_at__gt=now).only(
            "venue_id", "alert_type"
        )
    }


def top_items(queryset, limit: int = 10) -> list[dict[str, Any]]:
    sale_ids = list(queryset.filter(type=Transaction.Type.SALE).values_list("id", flat=True))
    if not sale_ids:
        return []

    rows = (
        TransactionItem.objects.filter(transaction_id__in=sale_ids)
        .values("item_id", "name")
        .annotate(qty=Sum("qty"))
        .order_by("-qty")[:limit]
    )
    top = list(rows)
    if not top:
        return []

    top_ids = {r["item_id"] for r in top}
    revenue_map: dict[str, Decimal] = {}
    for item in TransactionItem.objects.filter(
        transaction_id__in=sale_ids, item_id__in=top_ids
    ).only("item_id", "qty", "price"):
        revenue_map[item.item_id] = revenue_map.get(item.item_id, Decimal("0")) + (
            item.price * item.qty
        )

    return [
        {
            "item_id": r["item_id"],
            "name": r["name"],
            "qty": int(r["qty"] or 0),
            "revenue": _money(revenue_map.get(r["item_id"])),
        }
        for r in top
    ]


def venue_sales_today() -> list[dict[str, Any]]:
    start, end = _day_bounds()
    venues = list(Venue.objects.filter(is_active=True))

    rollups = (
        HourlyRollup.objects.filter(hour_start__gte=start, hour_start__lte=end)
        .values("venue_id")
        .annotate(
            sales=Sum("sales_total"),
            sale_count=Sum("sale_count"),
            void_count=Sum("void_count"),
            refund_count=Sum("refund_count"),
        )
    )
    by_venue = {r["venue_id"]: r for r in rollups}
    alerts = detect_alerts(end)

    ranked = []
    for v in venues:
        row = by_venue.get(v.id, {})
        sales = _money(row.get("sales"))
        voids = int(row.get("void_count") or 0) + int(row.get("refund_count") or 0)
        sales_n = int(row.get("sale_count") or 0)
        ranked.append(
            {
                "venue_id": v.id,
                "code": v.code,
                "name": v.name,
                "city": v.city,
                "venue_type": v.venue_type,
                "sales_today": sales,
                "sale_count": sales_n,
                "void_refund_count": voids,
                "transaction_count": sales_n + voids,
                "alerts": alerts.get(v.id, []),
            }
        )

    ranked.sort(key=lambda x: x["sales_today"], reverse=True)
    return ranked


def _daypart_baselines(hour_of_day: int, before: datetime) -> dict[int, float]:
    """Average sales_total for this hour_of_day over prior days (excludes `before` hour)."""
    lookback = getattr(settings, "BASELINE_LOOKBACK_DAYS", 14)
    min_samples = getattr(settings, "MIN_BASELINE_SAMPLES", 2)
    window_start = before - timedelta(days=lookback)

    rows = (
        HourlyRollup.objects.filter(
            hour_of_day=hour_of_day,
            hour_start__gte=window_start,
            hour_start__lt=before,
        )
        .values("venue_id")
        .annotate(avg_sales=Avg("sales_total"), samples=Count("id"))
    )
    return {
        r["venue_id"]: _money(r["avg_sales"])
        for r in rows
        if r["samples"] >= min_samples and _money(r["avg_sales"]) > 0
    }


def detect_alerts(now: datetime | None = None) -> dict[int, list[dict[str, Any]]]:
    """
    Flag venues where:
    - last-hour (sliding) sales dropped vs daypart baseline (or prior hour fallback), or
    - voids+refunds spiked as a share of last-hour transactions.
    Acknowledged alerts are omitted until expiry.
    """
    from django.db.models import Count, Q, Sum

    now = now or timezone.now()
    last_hour_start = now - timedelta(hours=1)
    prior_hour_start = now - timedelta(hours=2)
    current_hour = hour_bucket(now)
    # Daypart key = hour_of_day for the sliding window's midpoint-ish (start of current hour)
    hour_of_day = current_hour.hour

    last_hour = Transaction.objects.filter(timestamp__gte=last_hour_start, timestamp__lt=now)
    prior_hour = Transaction.objects.filter(
        timestamp__gte=prior_hour_start, timestamp__lt=last_hour_start
    )

    last_sales = {
        r["venue_id"]: _money(r["sales"])
        for r in last_hour.filter(type=Transaction.Type.SALE)
        .values("venue_id")
        .annotate(sales=Sum("total"))
    }
    prior_sales = {
        r["venue_id"]: _money(r["sales"])
        for r in prior_hour.filter(type=Transaction.Type.SALE)
        .values("venue_id")
        .annotate(sales=Sum("total"))
    }
    last_counts = {
        r["venue_id"]: r
        for r in last_hour.values("venue_id").annotate(
            total=Count("id"),
            bad=Count("id", filter=Q(type__in=[Transaction.Type.VOID, Transaction.Type.REFUND])),
        )
    }

    baselines = _daypart_baselines(hour_of_day, before=current_hour)

    drop_ratio = getattr(settings, "SALES_DROP_RATIO", 0.45)
    spike_ratio = getattr(settings, "VOID_REFUND_SPIKE_RATIO", 0.18)
    min_tx = getattr(settings, "MIN_TRANSACTIONS_FOR_ALERT", 3)
    acks = _active_acks(now)

    alerts: dict[int, list[dict[str, Any]]] = {}
    venue_ids = set(last_sales) | set(prior_sales) | set(last_counts) | set(baselines)

    for vid in venue_ids:
        flags: list[dict[str, Any]] = []
        lh = last_sales.get(vid, 0.0)
        ph = prior_sales.get(vid, 0.0)

        baseline = baselines.get(vid)
        compare_to = baseline if baseline is not None else ph
        compare_label = "daypart baseline" if baseline is not None else "prior hour"

        if compare_to > 0 and lh < compare_to * drop_ratio:
            ratio = lh / compare_to
            flags.append(
                {
                    "type": "sales_drop",
                    "severity": "high" if ratio < 0.25 else "medium",
                    "message": f"Sales dropped to {ratio:.0%} of {compare_label}",
                    "last_hour_sales": lh,
                    "baseline_sales": compare_to,
                    "prior_hour_sales": ph,
                }
            )

        counts = last_counts.get(vid)
        if counts and counts["total"] >= min_tx:
            ratio = counts["bad"] / counts["total"]
            if ratio >= spike_ratio:
                flags.append(
                    {
                        "type": "void_refund_spike",
                        "severity": "high" if ratio >= 0.3 else "medium",
                        "message": f"Voids/refunds are {ratio:.0%} of last-hour transactions",
                        "void_refund_count": counts["bad"],
                        "transaction_count": counts["total"],
                    }
                )

        flags = [f for f in flags if (vid, f["type"]) not in acks]
        if flags:
            alerts[vid] = flags

    return alerts


def group_summary() -> dict[str, Any]:
    start, end = _day_bounds()
    ranked = venue_sales_today()
    today = HourlyRollup.objects.filter(hour_start__gte=start, hour_start__lte=end).aggregate(
        sales=Sum("sales_total"),
        sales_n=Sum("sale_count"),
        voids=Sum("void_count"),
        refunds=Sum("refund_count"),
    )
    today_txns = Transaction.objects.filter(timestamp__gte=start, timestamp__lte=end)
    alerted = [v for v in ranked if v["alerts"]]

    return {
        "as_of": end.isoformat(),
        "day_start": start.isoformat(),
        "total_sales": round(_money(today["sales"]), 2),
        "venue_count": len(ranked),
        "alert_count": len(alerted),
        "sale_count": int(today["sales_n"] or 0),
        "void_refund_count": int(today["voids"] or 0) + int(today["refunds"] or 0),
        "venues": ranked,
        "top_items": top_items(today_txns, limit=10),
    }


def venue_detail(venue_id: int) -> dict[str, Any] | None:
    try:
        venue = Venue.objects.get(pk=venue_id, is_active=True)
    except Venue.DoesNotExist:
        return None

    start, end = _day_bounds()
    txns = Transaction.objects.filter(venue=venue, timestamp__gte=start, timestamp__lte=end)

    rollups = list(
        HourlyRollup.objects.filter(
            venue=venue, hour_start__gte=start, hour_start__lte=end
        ).order_by("hour_start")
    )
    sales_today = sum((_money(r.sales_total) for r in rollups), 0.0)
    baselines_by_hod = {
        hod: _daypart_baselines(hod, before=hour_bucket(end)).get(venue.id)
        for hod in {r.hour_of_day for r in rollups}
    }
    hourly_trade = [
        {
            "hour": timezone.localtime(r.hour_start).isoformat(),
            "sales": _money(r.sales_total),
            "count": r.sale_count,
            "baseline": baselines_by_hod.get(r.hour_of_day),
        }
        for r in rollups
    ]

    return {
        "venue_id": venue.id,
        "code": venue.code,
        "name": venue.name,
        "city": venue.city,
        "venue_type": venue.venue_type,
        "sales_today": sales_today,
        "alerts": detect_alerts(end).get(venue.id, []),
        "hourly_trade": hourly_trade,
        "top_items": top_items(txns, limit=10),
        "as_of": end.isoformat(),
    }


def acknowledge_alert(
    venue_id: int, alert_type: str, user, note: str = ""
) -> AlertAcknowledgement | None:
    try:
        venue = Venue.objects.get(pk=venue_id, is_active=True)
    except Venue.DoesNotExist:
        return None

    now = timezone.now()
    local = timezone.localtime(now)
    expires = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    existing = (
        AlertAcknowledgement.objects.filter(
            venue=venue, alert_type=alert_type, expires_at__gt=now
        )
        .order_by("-acknowledged_at")
        .first()
    )
    if existing:
        existing.acknowledged_by = user
        existing.expires_at = expires
        existing.note = note[:255]
        existing.save(update_fields=["acknowledged_by", "expires_at", "note"])
        return existing

    return AlertAcknowledgement.objects.create(
        venue=venue,
        alert_type=alert_type,
        acknowledged_by=user,
        expires_at=expires,
        note=note[:255],
    )
