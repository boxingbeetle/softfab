#!/bin/bash

# Figure out where PyLint is installed.
if [ -n "$PYLINT" ]; then
    if ! PYLINT=$(which "$PYLINT"); then
        exit 1
    fi
else
    if ! PYLINT=$(which pylint3 2> /dev/null); then
        if ! PYLINT=$(which pylint 2> /dev/null); then
            echo "Cannot find PyLint."
            echo ""
            echo "You can install PyLint using pip:"
            echo "  pip install --user pylint"
            echo ""
            exit 1
        fi
    fi
fi
echo "Using PyLint in $PYLINT"

# Figure out where our plugin directory is.
MYPATH=$(dirname "$0")
export PYTHONPATH="$MYPATH/tests/pylint"

exec "$PYLINT" "$@"
