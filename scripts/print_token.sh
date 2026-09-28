#!/usr/bin/env bash
# Convenience: print the ops auth token
set -euo pipefail
cd "$(dirname "$0")/../backend"
../.venv/bin/python - <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
u = User.objects.get(username="ops")
t, _ = Token.objects.get_or_create(user=u)
print(t.key)
PY
