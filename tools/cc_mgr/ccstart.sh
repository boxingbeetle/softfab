#!/bin/bash

DBDIR="$PWD/run"
PID_FILE="$DBDIR/cc.pid"
LOG_FILE="$PWD/pg1.log"

if [ -f "$PID_FILE" ]; then
    CC_PID=`cat "$PID_FILE"`
    if [ -d "/proc/$PID" ]; then
        echo "CC already running ($CC_PID)"
        exit 0
    else
        echo "Cleaned stale pid file ($CC_PID)"
        rm "$PID_FILE"
    fi
fi

if [ -z $POETRY_ACTIVE ]; then
    echo "Poetry is not running"
    exit 1
fi

softfab server --dir "$DBDIR" 2> "$LOG_FILE" &
#poetry run sh -c 'softfab server --dir '"$DBDIR"' 2> '"$LOG_FILE"' &'

if [ $? -eq 0 ] && [ -d "/proc/$CC_PID" ]; then
    echo "CC started ($CC_PID)"
else
    echo "Could not launch CC"
fi
