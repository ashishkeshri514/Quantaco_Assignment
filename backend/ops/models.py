from django.conf import settings
from django.contrib.auth.models import User
from django.db import models


class Venue(models.Model):
    """A hospitality venue in the group."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=128)
    city = models.CharField(max_length=64, blank=True)
    venue_type = models.CharField(
        max_length=32,
        choices=[
            ("pub", "Pub"),
            ("restaurant", "Restaurant"),
            ("function", "Function Space"),
        ],
        default="pub",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Transaction(models.Model):
    class Type(models.TextChoices):
        SALE = "sale", "Sale"
        VOID = "void", "Void"
        REFUND = "refund", "Refund"

    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="transactions")
    transaction_id = models.CharField(max_length=64)
    timestamp = models.DateTimeField(db_index=True)
    type = models.CharField(max_length=16, choices=Type.choices, db_index=True)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    staff_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["venue", "transaction_id"],
                name="uniq_venue_transaction_id",
            )
        ]
        indexes = [
            models.Index(fields=["venue", "timestamp"]),
            models.Index(fields=["timestamp", "type"]),
        ]
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.transaction_id} ({self.type}) ${self.total}"


class TransactionItem(models.Model):
    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, related_name="items"
    )
    item_id = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=128)
    qty = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.name} x{self.qty}"


class HourlyRollup(models.Model):
    """
    Materialised per-venue hour bucket, updated on ingest.
    Powers fast dashboard reads and daypart baseline alerts.
    """

    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="hourly_rollups")
    hour_start = models.DateTimeField(db_index=True)
    hour_of_day = models.PositiveSmallIntegerField(db_index=True)  # 0–23 local
    sales_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sale_count = models.PositiveIntegerField(default=0)
    void_count = models.PositiveIntegerField(default=0)
    refund_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["venue", "hour_start"],
                name="uniq_venue_hour_rollup",
            )
        ]
        indexes = [
            models.Index(fields=["venue", "hour_of_day"]),
            models.Index(fields=["hour_start"]),
        ]

    @property
    def void_refund_count(self) -> int:
        return self.void_count + self.refund_count

    @property
    def transaction_count(self) -> int:
        return self.sale_count + self.void_count + self.refund_count


class DeadLetterPayload(models.Model):
    """Bad POS payloads that failed validation — for ops / replay later."""

    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    venue_code = models.CharField(max_length=32, blank=True)
    transaction_id = models.CharField(max_length=64, blank=True)
    payload = models.JSONField()
    errors = models.JSONField()
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]


class AlertAcknowledgement(models.Model):
    """
    Ops mute for a venue+alert type until expires_at (default: end of local day).
    """

    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="alert_acks")
    alert_type = models.CharField(max_length=64)
    acknowledged_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="alert_acks"
    )
    acknowledged_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["venue", "alert_type", "expires_at"]),
        ]
