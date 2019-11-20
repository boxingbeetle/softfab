#!/bin/bash

PID_FILE="run/cc.pid"
KILLED="no"

if [ -f "$PID_FILE" ]; then
    CC_PID=`cat "$PID_FILE"`
    
	if [ -d "/proc/$CC_PID" ]; then
        # Shut down Control Center.
        echo "Shutting down CC..."
        kill -s SIGTERM "$CC_PID"
        for count in $(seq 1 10)
        do
            sleep 1
            test -d "/proc/$CC_PID" || break
        done
        if [ -d "/proc/$CC_PID" ]; then
            echo "Graceful shutdown failed, now killing CC."
            kill -s SIGKILL "$CC_PID"
        fi
		KILLED="yes"
	else
		echo "Cleaned stale pid file ($CC_PID)"
	fi
	rm "$PID_FILE"
fi

if [ "$KILLED" == "yes" ]; then
	echo "CC shut down ($CC_PID)"
else
	echo "CC was not running"
fi
