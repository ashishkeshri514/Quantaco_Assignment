from django.contrib import admin

from .models import (
    AlertAcknowledgement,
    DeadLetterPayload,
    HourlyRollup,
    Transaction,
    TransactionItem,
    Venue,
)


class TransactionItemInline(admin.TabularInline):
    model = TransactionItem
    extra = 0


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "city", "venue_type", "is_active")
    search_fields = ("code", "name", "city")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("transaction_id", "venue", "type", "total", "timestamp")
    list_filter = ("type", "venue")
    search_fields = ("transaction_id",)
    inlines = [TransactionItemInline]


@admin.register(HourlyRollup)
class HourlyRollupAdmin(admin.ModelAdmin):
    list_display = (
        "venue",
        "hour_start",
        "hour_of_day",
        "sales_total",
        "sale_count",
        "void_count",
        "refund_count",
    )
    list_filter = ("hour_of_day",)


@admin.register(DeadLetterPayload)
class DeadLetterAdmin(admin.ModelAdmin):
    list_display = ("received_at", "venue_code", "transaction_id", "source_ip")
    readonly_fields = ("received_at", "payload", "errors")


@admin.register(AlertAcknowledgement)
class AlertAckAdmin(admin.ModelAdmin):
    list_display = ("venue", "alert_type", "acknowledged_by", "acknowledged_at", "expires_at")
