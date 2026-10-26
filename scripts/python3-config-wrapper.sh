#!/usr/bin/env bash
# Venvs inherit VIRTUAL_ENV, which makes Debian's python3-config point at the
# venv include directory even though CPython headers remain system-owned.
unset VIRTUAL_ENV
exec "${TASK4_SYSTEM_PYTHON_CONFIG:-/usr/bin/python3-config}" "$@"
