#!/bin/bash
# log a detailed report CSV from TOGGL passed in as $1

export TOGGL_PASS="$(pass show toggl-pass | tr -d '\n')"
export PERSO_PASS="$(pass show personio-pass | tr -d '\n')"
export LOGURU_LEVEL='INFO'

SCRIPTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd $SCRIPTDIR

attempt=1
max_attempts=10

while [ $attempt -le $max_attempts ]; do
	uv run ./main.py -i "$1"
	status=$?
	if [ $status -eq 0 ]; then
		exit 0
	fi

	if [ $attempt -lt $max_attempts ]; then
		sleep 1
	fi

	attempt=$((attempt + 1))
done

exit $status
