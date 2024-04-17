#!/bin/bash

export TOGGL_PASS="$(pass show toggl-pass | tr -d '\n')"
export PERSO_PASS="$(pass show personio-pass | tr -d '\n')"

SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $SCRIPTDIR

. ./venv/bin/activate
./main.py
deactivate
