from __future__ import annotations

import json
import queue
import time

from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_GET
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from .events import bus
from .models import DeadLetterPayload, Venue
from .serializers import AlertAckSerializer, TransactionIngestSerializer, VenueSerializer
from .services import acknowledge_alert, group_summary, venue_detail


def _client_ip(request: Request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ingest_transaction(request: Request) -> Response:
    """
    POS ingest — idempotent on (venue_id, transaction_id).

    - 201 created
    - 200 duplicate (same payload key already stored; no double-count)
    - 400 validation error (also written to dead-letter)
    """
    serializer = TransactionIngestSerializer(data=request.data, context={})
    if not serializer.is_valid():
        raw = request.data if isinstance(request.data, dict) else {"_raw": str(request.data)}
        DeadLetterPayload.objects.create(
            venue_code=str(raw.get("venue_id", ""))[:32],
            transaction_id=str(raw.get("transaction_id", ""))[:64],
            payload=raw if isinstance(raw, dict) else {"_raw": str(raw)},
            errors=serializer.errors,
            source_ip=_client_ip(request),
        )
        return Response(
            {"detail": "Validation failed", "errors": serializer.errors, "dead_lettered": True},
            status=status.HTTP_400_BAD_REQUEST,
        )

    txn = serializer.save()
    duplicate = bool(serializer.context.get("duplicate"))

    if not duplicate:
        bus.publish(
            {
                "type": "transaction",
                "venue_id": txn.venue_id,
                "transaction_id": txn.transaction_id,
                "txn_type": txn.type,
                "total": float(txn.total),
                "timestamp": txn.timestamp.isoformat(),
            }
        )

    body = {
        "id": txn.id,
        "transaction_id": txn.transaction_id,
        "venue": txn.venue.code,
        "status": "duplicate" if duplicate else "created",
    }
    return Response(
        body,
        status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request: Request) -> Response:
    return Response(group_summary())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def venue_dashboard(request: Request, venue_id: int) -> Response:
    data = venue_detail(venue_id)
    if data is None:
        return Response({"detail": "Venue not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_venues(request: Request) -> Response:
    qs = Venue.objects.filter(is_active=True)
    return Response(VenueSerializer(qs, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ack_alert(request: Request, venue_id: int) -> Response:
    """Mute a venue alert type until end of local day."""
    ser = AlertAckSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    ack = acknowledge_alert(
        venue_id,
        ser.validated_data["alert_type"],
        request.user,
        note=ser.validated_data.get("note", ""),
    )
    if ack is None:
        return Response({"detail": "Venue not found."}, status=status.HTTP_404_NOT_FOUND)

    bus.publish({"type": "alert_ack", "venue_id": venue_id, "alert_type": ack.alert_type})
    return Response(
        {
            "venue_id": venue_id,
            "alert_type": ack.alert_type,
            "expires_at": ack.expires_at.isoformat(),
            "acknowledged_at": ack.acknowledged_at.isoformat(),
        }
    )


def _sse_stream():
    q = bus.subscribe()
    try:
        yield f"event: connected\ndata: {json.dumps({'ok': True})}\n\n"
        last_ping = time.time()
        while True:
            try:
                payload = q.get(timeout=1.0)
                # Distinguish event types when present
                try:
                    parsed = json.loads(payload)
                    etype = parsed.get("type", "transaction")
                except (TypeError, json.JSONDecodeError):
                    etype = "transaction"
                yield f"event: {etype}\ndata: {payload}\n\n"
            except queue.Empty:
                if time.time() - last_ping >= 15:
                    yield f"event: ping\ndata: {json.dumps({'ts': time.time()})}\n\n"
                    last_ping = time.time()
    finally:
        bus.unsubscribe(q)


@require_GET
def stream_events(request: HttpRequest) -> HttpResponse:
    """
    SSE endpoint as a plain Django view (not DRF).

    Why: EventSource sends Accept: text/event-stream; DRF content negotiation
    returns 406 unless we add a custom renderer.
    """
    raw = request.GET.get("token") or ""
    if not raw or not Token.objects.filter(key=raw).exists():
        return JsonResponse({"detail": "Invalid or missing token."}, status=401)

    response = StreamingHttpResponse(_sse_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
