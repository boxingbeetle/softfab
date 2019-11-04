#!/usr/bin/env python3

'''
Run a distutils-compatible console script.

The coverage tool cannot start shell scripts, so we need a pure Python way
of executing console scripts.
'''

import sys

# On Python 3.8+, use importlib.metadata from the standard library.
# On older versions, a compatibility package can be installed from PyPI.
try:
    import importlib.metadata as importlib_metadata
except ImportError:
    import importlib_metadata


group = 'console_scripts'

def print_scripts():
    print('', file=sys.stderr)
    print('Available scripts:', file=sys.stderr)
    entry_map = {
        entry.name: entry.value
        for entry in importlib_metadata.entry_points()[group]
        }
    for name in sorted(entry_map):
        print(f'  {name} = {entry_map[name]}', file=sys.stderr)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: run_console_script.py name ...', file=sys.stderr)
        print_scripts()
        sys.exit(2)

    name = sys.argv[1]
    entries = [
        entry
        for entry in importlib_metadata.entry_points()[group]
        if entry.name == name
        ]
    if not entries:
        print('Script not found:', name, file=sys.stderr)
        print_scripts()
        sys.exit(1)

    entry = entries[0]
    func = entry.load()
    del sys.argv[0]
    func()
