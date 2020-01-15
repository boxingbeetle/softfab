#!/bin/bash

FACDIR="$PWD"
FACTORY=`basename "$FACDIR"`
DBDIR="$FACDIR/db"
PID_FILE="$DBDIR/cc.pid"

KILLED="no"

if [ ! -d "$DBDIR" ]; then
    echo "$FACDIR is not a CC directory"
    exit 1
fi

if [ -f "$PID_FILE" ]; then
    CC_PID=`cat "$PID_FILE"`

    if [ -d "/proc/$CC_PID" ]; then
        # Shut down Control Center.
        echo "Shutting down CC '$FACTORY'..."
        kill -s SIGTERM "$CC_PID"
        for count in $(seq 10); do
            if [ ! -d "/proc/$CC_PID" ]; then
                break
            fi
            sleep 1
        done
        if [ -d "/proc/$CC_PID" ]; then
            echo "Graceful shutdown failed, now killing CC '$FACTORY'."
            kill -s SIGKILL "$CC_PID"
        fi
        KILLED="yes"
    else
        echo "Cleaned stale pid file ($CC_PID)"
    fi
fi

if [ "$KILLED" == "yes" ]; then
    echo "CC '$FACTORY' shut down ($CC_PID)"
else
    echo "CC '$FACTORY' was not running"
fi
