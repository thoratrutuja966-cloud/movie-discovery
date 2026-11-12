#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py migrate --fake-initial --noinput
python manage.py loaddata discovery/fixtures/demo_catalog.json
python manage.py collectstatic --noinput
