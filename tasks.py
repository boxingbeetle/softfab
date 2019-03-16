from os import getcwd, makedirs, remove
from os.path import exists
from shutil import rmtree

from invoke import task

CWD = getcwd()
SRC_ENV = {'PYTHONPATH': '{}/src'.format(CWD)}
PYLINT_ENV = {'PYTHONPATH': '{0}/src:{0}/tests/pylint'.format(CWD)}

all_sources = 'src/softfab/*.py src/softfab/pages/*.py'
mypy_report = 'mypy-report'

def remove_dir(path):
    """Recursively removes a directory."""
    if exists(path):
        rmtree(path)

@task
def clean(c):
    """Clean up our output."""
    print('Cleaning up...')
    remove_dir(mypy_report)
    remove_dir('docs/output')

@task
def lint(c, src=all_sources, rule=None):
    """Check sources with PyLint."""
    print('Checking sources with PyLint...')
    args = []
    if rule is not None:
        args += ['--disable=all', '--enable=' + rule]
    args.append(src)
    c.run('pylint %s' % ' '.join(args), env=PYLINT_ENV, pty=True)

@task
def types(c, src=all_sources, clean=False, report=False):
    """Check sources with mypy."""
    if clean:
        print('Clearing mypy cache...')
        remove_dir('.mypy_cache')
    print('Checking sources with mypy...')
    args = ['--ignore-missing-imports']
    if report:
        remove_dir(mypy_report)
        args.append('--html-report ' + mypy_report)
    args.append(src)
    c.run('mypy %s' % ' '.join(args), env=SRC_ENV, pty=True)

@task
def isort(c, src=all_sources):
    """Sort imports."""
    print('Sorting imports...')
    c.run('isort %s' % src, pty=True)

@task
def run(c, host='localhost', port=8180, auth=False):
    """Run a Control Center instance."""
    print('Starting Control Center at: http://%s:%d/' % (host, port))
    root = 'debugAuth' if auth else 'debug'
    makedirs('run/', exist_ok=True)
    with c.cd('run'):
        c.run('twist web'
                ' --listen tcp:interface=%s:port=%d'
                ' --class softfab.TwistedApp.%s' % (host, port, root),
                env=SRC_ENV, pty=True)

@task
def livedocs(c, host='localhost', port=5000):
    """Serve editable version of documentation."""
    with c.cd('docs'):
        c.run('lektor serve --host %s --port %d' % (host, port), pty=True)

@task
def docs(c):
    """Build documentation."""
    with c.cd('docs'):
        c.run('lektor build --output-path output', pty=True)
    print('Created documentation in: docs/output')
