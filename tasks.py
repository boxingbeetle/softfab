from pathlib import Path
from os import makedirs
from shutil import copyfile, rmtree

from invoke import UnexpectedExit, call, task

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
    remove_dir(TOP_DIR / 'tr' / 'derived')

@task
def build_tr(c):
    """Build Task Runner."""
    with c.cd(str(TOP_DIR / 'tr')):
        c.run('ant jar', pty=True)
    copyfile(
        str(TOP_DIR / 'tr' / 'derived' / 'bin' / 'taskrunner.jar'),
        str(TOP_DIR / 'src' / 'softfab' / 'static' / 'taskrunner.jar')
        )

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
def types(c, src=None, clean=False, report=False, results=None):
    """Check sources with mypy."""
    if clean:
        print('Clearing mypy cache...')
        remove_dir(TOP_DIR / '.mypy_cache')
    print('Checking sources with mypy...')
    report_dir = None if results is None else Path(results).parent.resolve()
    args = []
    if report:
        if report_dir is None:
            remove_dir(TOP_DIR / mypy_report)
            args.append('--xml-report ' + mypy_report)
        else:
            args.append('--xml-report ' + str(report_dir / 'mypy-coverage'))
    args.append(source_arg(src))
    out_path = None if report_dir is None else report_dir / 'mypy-log.txt'
    out_stream = None if out_path is None \
                      else open(out_path, 'w', encoding='utf-8')
    try:
        with c.cd(str(TOP_DIR)):
            try:
                c.run('mypy %s' % ' '.join(args),
                      env=SRC_ENV, out_stream=out_stream, pty=True)
            except UnexpectedExit as ex:
                if ex.result.exited < 0:
                    print(ex)
    finally:
        if out_stream is not None:
            out_stream.close()
    if results is not None:
        errors = 0
        with open(out_path, 'r', encoding='utf-8') as log:
            for line in log:
                if ' error: ' in line:
                    errors += 1
        with open(results, 'w', encoding='utf-8') as out:
            out.write(f'result={"warning" if errors else "ok"}\n')
            out.write(f'summary=mypy found {errors} errors\n')
            out.write(f'report.{0 if errors else 2}={out_path}\n')
            if report:
                out.write(f'report.1={report_dir}/mypy-coverage\n')

@task
def isort(c, src=None):
    """Sort imports."""
    print('Sorting imports...')
    with c.cd(str(TOP_DIR)):
        c.run('isort %s' % source_arg(src), pty=True)

@task
def run(c, host='localhost', port=8180, auth=False, coverage=False):
    """Run a Control Center instance."""
    print(f'Starting Control Center at: http://{host}:{port}/')
    root = 'debugAuth' if auth else 'debug'
    makedirs('run/', exist_ok=True)
    cmd = [
        'twist', 'web',
        f'--listen tcp:interface={host}:port={port}',
        f'--class softfab.TwistedApp.{root}'
        ]
    if coverage:
        runner = TOP_DIR / 'tests' / 'tools' / 'run_console_script.py'
        cmd = ['coverage', 'run', '--source=../src', str(runner)] + cmd
    with c.cd(str(TOP_DIR / 'run')):
        c.run(' '.join(cmd), env=SRC_ENV, pty=True)
