#!/bin/sh
# Start Poetry with Python 3.x as the default Python.

cd `dirname $0`

if ! test -e tools/python
then
    ln -s /usr/bin/python3 tools/python
fi

PATH="$PWD/tools:$PATH" exec poetry shell
