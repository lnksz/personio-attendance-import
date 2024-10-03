#!/bin/bash
# log a detailed report CSV from TOGGL passed in as $1

export TOGGL_PASS="$(pass show toggl-pass | tr -d '\n')"
export PERSO_PASS="$(pass show personio-pass | tr -d '\n')"
export LOGURU_LEVEL='info'

SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $SCRIPTDIR

uv run ./main.py -i "$1"
