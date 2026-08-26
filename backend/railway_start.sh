#!/usr/bin/env bash
# Railway start command (see railway.json). collectstatic already ran
# during the build phase (no DB needed for that); migrate runs here, at
# boot, since it needs the database and Django migrations are idempotent
# -- safe to run on every deploy/restart. `exec` hands off to gunicorn so
# it receives Railway's shutdown signal directly, instead of a wrapping
# shell swallowing it.
set -o errexit

python manage.py migrate
exec gunicorn config.wsgi:application --bind 0.0.0.0:"$PORT"
