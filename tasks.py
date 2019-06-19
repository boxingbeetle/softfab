from pathlib import Path
from os import makedirs, remove
from shutil import rmtree

from invoke import UnexpectedExit, task

TOP_DIR = Path(__file__).parent
SRC_ENV = {'PYTHONPATH': '{}/src'.format(TOP_DIR)}
PYLINT_ENV = {'PYTHONPATH': '{0}/src:{0}/tests/pylint'.format(TOP_DIR)}

mypy_report = 'mypy-report'

def source_arg(pattern):
    """Converts a source pattern to a command line argument."""
    if pattern is None:
        paths = (TOP_DIR / 'src' / 'softfab').glob('**/*.py')
    else:
        paths = Path.cwd().glob(pattern)
    return ' '.join(str(path) for path in paths)

def remove_dir(path):
    """Recursively removes a directory."""
    if path.exists():
        rmtree(str(path))

@task
def clean(c):
    """Clean up our output."""
    print('Cleaning up...')
    remove_dir(TOP_DIR / mypy_report)
    remove_dir(TOP_DIR / 'docs' / 'output')

@task
def lint(c, src=None, rule=None):
    """Check sources with PyLint."""
    print('Checking sources with PyLint...')
    args = []
    if rule is not None:
        args += [
            '--disable=all', '--enable=' + rule,
            '--persistent=n', '--score=n'
            ]
    args.append(source_arg(src))
    with c.cd(str(TOP_DIR)):
        c.run('pylint %s' % ' '.join(args), env=PYLINT_ENV, pty=True)

@task
def types(c, src=None, clean=False, report=False):
    """Check sources with mypy."""
    if clean:
        print('Clearing mypy cache...')
        remove_dir(TOP_DIR / '.mypy_cache')
    print('Checking sources with mypy...')
    args = []
    if report:
        remove_dir(TOP_DIR / mypy_report)
        args.append('--html-report ' + mypy_report)
    args.append(source_arg(src))
    with c.cd(str(TOP_DIR)):
        try:
            c.run('mypy %s' % ' '.join(args), env=SRC_ENV, pty=True)
        except UnexpectedExit as ex:
            if ex.result.exited < 0:
                print(ex)

@task
def isort(c, src=None):
    """Sort imports."""
    print('Sorting imports...')
    with c.cd(str(TOP_DIR)):
        c.run('isort %s' % source_arg(src), pty=True)

@task
def livedocs(c, host='localhost', port=5000):
    """Serve editable version of documentation."""
    with c.cd(str(TOP_DIR / 'docs')):
        c.run('lektor serve --host %s --port %d' % (host, port), pty=True)

@task
def docs(c):
    """Build documentation."""
    with c.cd(str(TOP_DIR / 'docs')):
        c.run('lektor build --output-path output', pty=True)
    print('Created documentation in: docs/output')

@task
def run(c, host='localhost', port=8180, auth=False):
    """Run a Control Center instance."""
    print('Starting Control Center at: http://%s:%d/' % (host, port))
    root = 'debugAuth' if auth else 'debug'
    makedirs('run/', exist_ok=True)
    with c.cd(str(TOP_DIR / 'run')):
        c.run('twist web'
                ' --listen tcp:interface=%s:port=%d'
                ' --class softfab.TwistedApp.%s' % (host, port, root),
                env=SRC_ENV, pty=True)
