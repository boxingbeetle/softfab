#!/bin/sh
# Start Poetry with Python 3.x as the default Python.

cd `dirname $0`

test -d tools/venv3 || virtualenv -p python3 tools/venv3

test -d tools/venv3 && PATH="$PWD/tools/venv3/bin:$PATH" exec poetry shell
