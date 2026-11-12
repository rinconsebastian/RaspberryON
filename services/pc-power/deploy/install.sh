#!/bin/bash
# Crea/actualiza el venv del servicio. Lo ejecuta platform/remote-install.sh en la Raspberry.
# --system-site-packages: reutiliza python3-gpiozero y python3-lgpio instalados con apt.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -x venv/bin/python ] || python3 -m venv --system-site-packages venv
venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt
chmod -R a+rX venv
