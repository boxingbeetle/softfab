from invoke import task

SRC_ENV = {'PYTHONPATH': 'src/softfab'}
PYLINT_ENV = {'PYTHONPATH': 'tests/pylint'}

@task
def lint(c):
    """Check sources with PyLint."""
    print('Checking sources with PyLint...')
    c.run('pylint src/softfab/*.py', env=PYLINT_ENV, pty=True)

@task
def run(c, host='localhost', port=8180):
    """Run a Control Center instance."""
    print('Starting Control Center at: http://%s:%d/' % (host, port))
    c.run('twist web'
            ' --listen tcp:interface=%s:port=%d'
            ' --class TwistedApp.Root' % (host, port),
            env=SRC_ENV, pty=True)
