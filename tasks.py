from pathlib import Path
from shutil import copyfile, rmtree

from invoke import UnexpectedExit, task

TOP_DIR = Path(__file__).parent
SRC_DIR = TOP_DIR / 'src'
SRC_ENV = {'PYTHONPATH': str(SRC_DIR)}
PYLINT_DIR = TOP_DIR / 'tests' / 'pylint'
PYLINT_ENV = {'PYTHONPATH': f'{SRC_DIR}:{PYLINT_DIR}'}

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

def write_results(results, results_path, append=False):
    """Write a results dictionary to file."""
    mode = 'a' if append else 'w'
    with open(results_path, mode, encoding='utf-8') as out:
        for key, value in results.items():
            out.write('%s=%s\n' % (key, value.replace('\\', '\\\\')))

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
def lint(c, src=None, rule=None, html=None, results=None, version=False):
    """Check sources with PyLint."""
    print('Checking sources with PyLint...')
    if version:
        c.run('pylint --version', env=PYLINT_ENV)
    if results is None:
        report_dir = Path(TOP_DIR)
    else:
        # We need to output JSON to produce the results file, but we also
        # need to report the issues, so we have to get those from the JSON
        # output and the easiest way to do so is to enable the HTML report.
        report_dir = Path(results).parent.resolve()
        html = report_dir / 'pylint.html'
    cmd = ['pylint']
    if rule is not None:
        cmd += [
            '--disable=all', '--enable=' + rule,
            '--persistent=n', '--score=n'
            ]
    if html is not None:
        html = Path(html).resolve()
        json_file = report_dir / 'pylint.json'
        cmd += ['--load-plugins=pylint_json2html',
                '--output-format=jsonextended',
                '>%s' % json_file]
    cmd.append(source_arg(src))
    with c.cd(str(TOP_DIR)):
        lint_result = c.run(' '.join(cmd),
                            env=PYLINT_ENV, warn=True, pty=results is None)
    if html is not None:
        with c.cd(str(TOP_DIR)):
            c.run(f'pylint-json2html -f jsonextended -o {html} {json_file}')
    if results is not None:
        import sys
        sys.path.append(str(PYLINT_DIR))
        from pylint_json2sfresults import gather_results
        results_dict = gather_results(json_file, lint_result.exited)
        results_dict['report'] = str(html)
        write_results(results_dict, results)

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
            args.append('--html-report ' + mypy_report)
        else:
            args.append('--html-report ' + str(report_dir / 'mypy-coverage'))
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
def unittest(c, suite=None, junit_xml=None, results=None, coverage=False):
    """Run unit tests."""
    test_dir = TOP_DIR / 'tests' / 'unit'
    if results is None:
        report_dir = test_dir
    else:
        report_dir = Path(results).parent.resolve()
        junit_xml = report_dir / 'pytest-report.xml'
    cmd = ['pytest']
    if coverage:
        cmd.append(f'--cov={SRC_DIR}')
        cmd.append(f"--cov-config={TOP_DIR / '.coveragerc'}")
        cmd.append('--cov-report=')
    if junit_xml is not None:
        cmd.append(f'--junit-xml={junit_xml}')
    if suite is None:
        cmd.append(str(test_dir))
    else:
        cmd.extend(str(path) for path in test_dir.glob(suite))
    with c.cd(str(report_dir)):
        c.run(' '.join(cmd), env=SRC_ENV, pty=results is None)
    if results is not None:
        results_dict = dict(report=str(junit_xml))
        if coverage:
            results_dict['output.COVERAGE.locator'] = \
                    str(report_dir / '.coverage')
        write_results(results_dict, results)

@task(post=[unittest, lint, types])
def test(c):
    """Run all tests."""

@task
def isort(c, src=None):
    """Sort imports."""
    print('Sorting imports...')
    with c.cd(str(TOP_DIR)):
        c.run('isort %s' % source_arg(src), pty=True)

@task
def run(c, host='localhost', port=8180, dbdir='run',
        auth=False, coverage=False):
    """Run a Control Center instance."""
    print(f'Starting Control Center at: http://{host}:{port}/')
    cmd = [
        'softfab', 'server',
        f'--listen tcp:interface={host}:port={port}',
        '--debug', '--insecure-cookie'
        ]
    if not auth:
        cmd.append('--no-auth')
    if coverage:
        runner = TOP_DIR / 'tests' / 'tools' / 'run_console_script.py'
        cmd = [
            'coverage', 'run',
            f"--rcfile={TOP_DIR / '.coveragerc'}",
            f'--source={SRC_DIR}',
            str(runner)
            ] + cmd
    db_path = Path(dbdir)
    if not db_path.is_absolute():
        db_path = TOP_DIR / db_path
    db_path.mkdir(exist_ok=True)
    pid_file = db_path / 'cc.pid'
    cmd = ['echo' ,'$$', f'>{pid_file}', '&&'] + cmd
    with c.cd(str(db_path)):
        c.run(' '.join(cmd), env=SRC_ENV, pty=True)

@task
def ape(c, host='localhost', port=8180, dbdir='run', results=None):
    db_path = Path(dbdir)
    if not db_path.is_absolute():
        db_path = TOP_DIR / db_path
    cmd = [
        'apetest',
        '--check', 'launch',
        '--cclog', str(db_path / 'cc-log.txt'),
        ]
    if results is None:
        report_dir = TOP_DIR.resolve()
    else:
        cmd += ['--result', str(Path(results).resolve())]
        report_dir = Path(results).parent.resolve()
    report = report_dir / 'ape-report.html'
    cmd += [f'http://localhost:{port}/', str(report)]
    with c.cd(str(TOP_DIR)):
        c.run(' '.join(cmd), pty=results is None)
    if results is not None:
        write_results({'report': str(report)}, results, append=True)
