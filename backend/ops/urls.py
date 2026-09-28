from django.urls import path

from . import views

urlpatterns = [
    path("transactions/", views.ingest_transaction, name="ingest-transaction"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("venues/", views.list_venues, name="list-venues"),
    path("venues/<int:venue_id>/", views.venue_dashboard, name="venue-dashboard"),
    path("venues/<int:venue_id>/ack/", views.ack_alert, name="ack-alert"),
    path("stream/", views.stream_events, name="stream-events"),
]
