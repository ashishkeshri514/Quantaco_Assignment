from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import Transaction, TransactionItem, Venue
from .rollups import apply_rollup


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ["id", "code", "name", "city", "venue_type", "is_active"]


class TransactionItemSerializer(serializers.Serializer):
    item_id = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=128)
    qty = serializers.IntegerField(min_value=1)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)


class TransactionIngestSerializer(serializers.Serializer):
    venue_id = serializers.CharField(max_length=32, help_text="Venue code, e.g. VEN-01")
    transaction_id = serializers.CharField(max_length=64)
    timestamp = serializers.DateTimeField()
    type = serializers.ChoiceField(choices=Transaction.Type.choices)
    items = TransactionItemSerializer(many=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    staff_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")

    def validate_venue_id(self, value: str) -> str:
        if not Venue.objects.filter(code=value, is_active=True).exists():
            raise serializers.ValidationError(f"Unknown or inactive venue: {value}")
        return value

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value

    def create(self, validated_data):
        """
        Idempotent create: duplicate (venue, transaction_id) returns the existing row
        and sets self.context['duplicate'] = True for the view to return 200.
        """
        venue = Venue.objects.get(code=validated_data["venue_id"])
        items_data = validated_data.pop("items")
        validated_data.pop("venue_id")
        txn_id = validated_data["transaction_id"]

        existing = Transaction.objects.filter(venue=venue, transaction_id=txn_id).first()
        if existing:
            self.context["duplicate"] = True
            return existing

        try:
            with transaction.atomic():
                txn = Transaction.objects.create(venue=venue, **validated_data)
                TransactionItem.objects.bulk_create(
                    [
                        TransactionItem(
                            transaction=txn,
                            item_id=item["item_id"],
                            name=item["name"],
                            qty=item["qty"],
                            price=item["price"],
                        )
                        for item in items_data
                    ]
                )
                apply_rollup(txn)
        except IntegrityError:
            # Race: another worker inserted the same txn_id
            self.context["duplicate"] = True
            return Transaction.objects.get(venue=venue, transaction_id=txn_id)

        self.context["duplicate"] = False
        return txn


class AlertAckSerializer(serializers.Serializer):
    alert_type = serializers.ChoiceField(
        choices=["sales_drop", "void_refund_spike"],
    )
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)
