#!/usr/bin/env bash
# Render build command (see render.yaml). Runs with the working directory
# set to this file's own directory (Render's `rootDir: backend`), so all
# paths below are relative to backend/ -- exactly like running these by
# hand locally.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
