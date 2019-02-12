from shutil import rmtree

from invoke import task

SRC_ENV = {'PYTHONPATH': 'src'}
PYLINT_ENV = {'PYTHONPATH': 'src:tests/pylint'}

@task
def clean(c):
    """Clean up our output."""
    print('Cleaning up...')
    rmtree('docs/output')

@task
def lint(c, src='src/softfab/*.py'):
    """Check sources with PyLint."""
    print('Checking sources with PyLint...')
    c.run('pylint %s' % src, env=PYLINT_ENV, pty=True)

@task
def run(c, host='localhost', port=8180):
    """Run a Control Center instance."""
    print('Starting Control Center at: http://%s:%d/' % (host, port))
    c.run('twist web'
            ' --listen tcp:interface=%s:port=%d'
            ' --class softfab.TwistedApp.Root' % (host, port),
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
