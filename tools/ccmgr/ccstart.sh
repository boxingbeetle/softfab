#!/bin/bash

DBDIR="$PWD/db"
PID_FILE="$DBDIR/cc.pid"
LOG_FILE="$PWD/cc.log"

if [ -z $VIRTUAL_ENV ]; then
    echo "VENV is not running"
    exit 1
fi

if [ ! -d "$DBDIR" ]; then
    echo "$PWD is not a CC directory"
    exit 1
fi

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

softfab server --dir "$DBDIR" 2> "$LOG_FILE" &

if [ $? -eq 0 ]; then
    for count in $(seq 1 10)
    do
        if [ -f "$PID_FILE" ]; then
            break
        fi
        sleep 1
    done
    CC_PID=`cat "$PID_FILE"`
    echo "CC started ($CC_PID)"
else
    echo "Could not launch CC"
fi
