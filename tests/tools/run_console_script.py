#!/usr/bin/env python3

'''
Run a distutils-compatible console script.

The coverage tool cannot start shell scripts, so we need a pure Python way
of executing console scripts.
'''

import sys
from pkg_resources import working_set

group = 'console_scripts'

def print_scripts():
    print('', file=sys.stderr)
    print('Available scripts:', file=sys.stderr)
    for entry in working_set.iter_entry_points(group):
        print('  ', entry, file=sys.stderr)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: run_console_script.py name ...', file=sys.stderr)
        print_scripts()
        sys.exit(2)

    name = sys.argv[1]
    entries = list(working_set.iter_entry_points(group, name))
    if not entries:
        print('Script not found:', name, file=sys.stderr)
        print_scripts()
        sys.exit(1)

    entry = entries[0]
    func = entry.load()
    del sys.argv[0]
    func()
