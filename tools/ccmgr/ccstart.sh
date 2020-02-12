#!/bin/bash

FACDIR="$PWD"
FACTORY=`basename "$FACDIR"`
DBDIR="$FACDIR/db"
PID_FILE="$DBDIR/cc.pid"
LOG_FILE="$FACDIR/$FACTORY.log"

if [ ! -d "$DBDIR" ]; then
    echo "$FACDIR is not a CC directory"
    exit 1
fi

if [ -f "$PID_FILE" ]; then
    CC_PID=`cat "$PID_FILE"`
    if [ -d "/proc/$CC_PID" ]; then
        echo "CC '$FACTORY' already running ($CC_PID)"
        exit 0
    else
        echo "Cleaned stale pid file ($CC_PID)"
        rm "$PID_FILE"
    fi
fi

if [ -z $VIRTUAL_ENV ]; then
    if [ ! -f "$FACDIR/venv/bin/activate" ]; then
        echo "Not possible to create VENV"
        exit 1
    fi
    source "$FACDIR"/venv/bin/activate
fi

softfab server --dir "$DBDIR" 2> "$LOG_FILE" &

if [ $? -eq 0 ]; then
    for count in $(seq 10); do
        if [ -f "$PID_FILE" ]; then
            break
        fi
        sleep 1
    done
    CC_PID=`cat "$PID_FILE"`
    REVISION=`pip list | grep softfab | sed 's/.\+-g//'`
    echo "CC '$FACTORY' revision '$REVISION' started ($CC_PID)"
else
    echo "Could not launch CC '$FACTORY'"
fi
