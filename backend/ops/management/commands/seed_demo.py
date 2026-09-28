"""
Seed 40 venues + an ops user for local demo.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from ops.models import Venue

CITIES = [
    "Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide",
    "Canberra", "Hobart", "Newcastle", "Geelong", "Gold Coast",
]
TYPES = ["pub", "restaurant", "function"]
NAMES = [
    "Harbour", "Crown", "Oak", "River", "Market", "Station", "Garden", "Lane",
    "Bridge", "Wharf", "Central", "Park", "Union", "Grand", "Royal", "Empire",
    "Plaza", "Corner", "Dock", "Hill", "Bay", "Street", "House", "Room",
    "Cellar", "Terrace", "Kitchen", "Bar", "Club", "Hall", "Yard", "Court",
    "Arcade", "Annex", "Lodge", "Inn", "Cafe", "Bistro", "Lounge", "Works",
]


class Command(BaseCommand):
    help = "Seed venues and create ops demo user (ops / ops1234)"

    def handle(self, *args, **options):
        created_venues = 0
        for i in range(1, 41):
            code = f"VEN-{i:02d}"
            name = f"{NAMES[i - 1]} {TYPES[(i - 1) % 3].title()}"
            _, was_created = Venue.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "city": CITIES[(i - 1) % len(CITIES)],
                    "venue_type": TYPES[(i - 1) % 3],
                    "is_active": True,
                },
            )
            if was_created:
                created_venues += 1

        user, user_created = User.objects.get_or_create(
            username="ops",
            defaults={"email": "ops@quantaco.local", "is_staff": True},
        )
        if user_created:
            user.set_password("ops1234")
            user.save()
        else:
            user.set_password("ops1234")
            user.save()

        token, _ = Token.objects.get_or_create(user=user)

        self.stdout.write(self.style.SUCCESS(
            f"Venues ready (new={created_venues}, total={Venue.objects.count()}). "
            f"Login: ops / ops1234. Token: {token.key}"
        ))
