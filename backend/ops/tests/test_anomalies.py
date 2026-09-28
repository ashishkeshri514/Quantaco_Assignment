from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ops.events import bus
from ops.models import DeadLetterPayload, HourlyRollup, Transaction, TransactionItem, Venue
from ops.rollups import apply_rollup
from ops.services import acknowledge_alert, detect_alerts, group_summary


class AnomalyTests(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(
            code="VEN-99", name="Test Pub", city="Sydney", venue_type="pub"
        )

    def _sale(self, when, total="100.00"):
        txn = Transaction.objects.create(
            venue=self.venue,
            transaction_id=f"T-{when.timestamp()}-{total}-{id(when)}",
            timestamp=when,
            type=Transaction.Type.SALE,
            total=Decimal(total),
            staff_id="S1",
        )
        TransactionItem.objects.create(
            transaction=txn, item_id="I1", name="Beer", qty=1, price=Decimal(total)
        )
        apply_rollup(txn)
        return txn

    def test_sales_drop_flagged(self):
        now = timezone.now()
        for i in range(5):
            self._sale(now - timedelta(hours=1, minutes=10 + i), "80.00")
        self._sale(now - timedelta(minutes=20), "20.00")

        alerts = detect_alerts(now).get(self.venue.id, [])
        types = {a["type"] for a in alerts}
        self.assertIn("sales_drop", types)

    def test_void_spike_flagged(self):
        now = timezone.now()
        for i in range(4):
            txn = Transaction.objects.create(
                venue=self.venue,
                transaction_id=f"V-{i}",
                timestamp=now - timedelta(minutes=5 + i),
                type=Transaction.Type.VOID,
                total=Decimal("10.00"),
                staff_id="S1",
            )
            apply_rollup(txn)
        self._sale(now - timedelta(minutes=2), "40.00")

        alerts = detect_alerts(now).get(self.venue.id, [])
        types = {a["type"] for a in alerts}
        self.assertIn("void_refund_spike", types)

    def test_group_summary_ranks_venues(self):
        other = Venue.objects.create(
            code="VEN-98", name="Other", city="Melbourne", venue_type="restaurant"
        )
        now = timezone.now()
        self._sale(now - timedelta(minutes=1), "50.00")
        txn = Transaction.objects.create(
            venue=other,
            transaction_id="T-other",
            timestamp=now - timedelta(minutes=1),
            type=Transaction.Type.SALE,
            total=Decimal("200.00"),
            staff_id="S2",
        )
        apply_rollup(txn)
        summary = group_summary()
        self.assertEqual(summary["venues"][0]["code"], "VEN-98")
        self.assertGreaterEqual(summary["total_sales"], 250.0)

    def test_ack_hides_alert(self):
        now = timezone.now()
        for i in range(5):
            self._sale(now - timedelta(hours=1, minutes=10 + i), "80.00")
        self._sale(now - timedelta(minutes=20), "20.00")
        user = User.objects.create_user("ops2", password="x")
        acknowledge_alert(self.venue.id, "sales_drop", user)
        alerts = detect_alerts(now).get(self.venue.id, [])
        types = {a["type"] for a in alerts}
        self.assertNotIn("sales_drop", types)


class IngestTests(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(
            code="VEN-01", name="Harbour Pub", city="Sydney", venue_type="pub"
        )
        self.user = User.objects.create_user("ops", password="ops1234")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _payload(self, txn_id="TXN-1", **overrides):
        body = {
            "venue_id": "VEN-01",
            "transaction_id": txn_id,
            "timestamp": timezone.now().isoformat(),
            "type": "sale",
            "items": [{"item_id": "I1", "name": "Beer", "qty": 1, "price": "9.50"}],
            "total": "9.50",
            "staff_id": "S1",
        }
        body.update(overrides)
        return body

    def test_ingest_creates_rollup(self):
        res = self.client.post("/api/transactions/", self._payload(), format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "created")
        self.assertEqual(HourlyRollup.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_ingest_idempotent(self):
        p = self._payload("TXN-DUP")
        self.assertEqual(self.client.post("/api/transactions/", p, format="json").status_code, 201)
        res = self.client.post("/api/transactions/", p, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "duplicate")
        self.assertEqual(Transaction.objects.count(), 1)
        # rollup not double-counted
        rollup = HourlyRollup.objects.get()
        self.assertEqual(rollup.sale_count, 1)

    def test_bad_payload_dead_lettered(self):
        res = self.client.post(
            "/api/transactions/",
            {"venue_id": "NOPE", "transaction_id": "X"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertTrue(res.data.get("dead_lettered"))
        self.assertEqual(DeadLetterPayload.objects.count(), 1)

    def test_ack_endpoint(self):
        now = timezone.now()
        for i in range(5):
            txn = Transaction.objects.create(
                venue=self.venue,
                transaction_id=f"S-{i}",
                timestamp=now - timedelta(hours=1, minutes=10 + i),
                type=Transaction.Type.SALE,
                total=Decimal("80"),
                staff_id="S1",
            )
            apply_rollup(txn)
        txn = Transaction.objects.create(
            venue=self.venue,
            transaction_id="weak",
            timestamp=now - timedelta(minutes=10),
            type=Transaction.Type.SALE,
            total=Decimal("10"),
            staff_id="S1",
        )
        apply_rollup(txn)
        res = self.client.post(
            f"/api/venues/{self.venue.id}/ack/",
            {"alert_type": "sales_drop"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["alert_type"], "sales_drop")


class SSEBusTests(TestCase):
    def test_publish_reaches_subscriber(self):
        q = bus.subscribe()
        try:
            bus.publish({"type": "transaction", "transaction_id": "x"})
            payload = q.get(timeout=2)
            self.assertIn("transaction", payload)
        finally:
            bus.unsubscribe(q)
