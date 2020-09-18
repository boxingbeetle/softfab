# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the command line interface."""

from urllib.parse import parse_qs, urlparse
import json

from click import Group
from click.testing import CliRunner
from passlib.apache import HtpasswdFile
from pytest import fixture, mark
from twisted.internet.endpoints import UNIXClientEndpoint
from twisted.internet.testing import MemoryReactorClock
from twisted.test.iosim import connect, makeFakeClient, makeFakeServer
from twisted.web.client import Agent
from twisted.web.iweb import IAgentEndpointFactory
from zope.interface import implementer

from softfab import cmdline
from softfab.roles import roleNames
from softfab.site import ControlSocket
from softfab.TwistedRoot import SoftFabRoot
from softfab.TwistedUtil import runCoroutine


# Support code to invoke command line interface inside a test case:

@implementer(IAgentEndpointFactory)
class FixedEndpointFactory:
    """Factory that always returns the same endpoint."""

    def __init__(self, endpoint):
        self.endpoint = endpoint

    def endpointForURI(self, uri):
        return self.endpoint


class TickingClockReactor(MemoryReactorClock):
    """An extended MemoryReactor that also runs all callbacks added with
    callLater().
    """

    def run(self):
        self.callWhenRunning(self.runClock)
        super().run()

    def runClock(self):
        while self.running and self.calls:
            nextTime = self.calls[0].getTime()
            self.advance(nextTime - self.seconds())

class MemoryOptions:
    """An alternative implementation of GlobalOptions that uses a reactor
    that is more suitable for testing.
    """

    def __init__(self):
        self.reactor = TickingClockReactor()

    @property
    def agent(self):
        reactor = self.reactor
        clientEndpoint = UNIXClientEndpoint(reactor, '/dev/null')
        endpointFactory = FixedEndpointFactory(clientEndpoint)
        return Agent.usingEndpointFactory(reactor, endpointFactory)

    def urlForPath(self, path):
        return f'http://test/{path}'

async def execute(reactor, dbDir):
    root = SoftFabRoot(dbDir, reactor=None, anonOperator=False)
    await root.startup()

    clientInfo, = reactor.unixClients
    clientFactory = clientInfo[1]
    serverFactory = ControlSocket(root.apiRoot)

    clientProtocol = clientFactory.buildProtocol(None)
    serverProtocol = serverFactory.buildProtocol(None)
    serverTransport = makeFakeServer(serverProtocol)
    clientTransport = makeFakeClient(clientProtocol)

    pump = connect(serverProtocol, serverTransport,
                   clientProtocol, clientTransport,
                   debug=False)
    pump.flush()

def find_command(words):
    """Find the Click (sub)command that corresponds to the given words.

    Return a pair of the Command object and the remaining words (arguments).
    Raise LookupError if the given words do not specify a command.
    """
    group = cmdline.main
    idx = 0
    while idx < len(words):
        command = group.get_command(None, words[idx])
        idx += 1
        if command is None:
            break
        elif isinstance(command, Group):
            group = command
        else:
            return command, words[idx:]
    raise LookupError(f"no such command: {' '.join(words[:idx])}")

class SoftFabCLI:
    runner = CliRunner()

    def __init__(self, db_path):
        self.db_path = db_path

    def run(self, *words):
        command, args = find_command(words)

        # Reactors cannot be restarted, so use a fresh one for every command.
        globalOptions = MemoryOptions()
        reactor = globalOptions.reactor
        executer = execute(reactor, self.db_path)
        reactor.callWhenRunning(runCoroutine, reactor, executer)

        try:
            return self.runner.invoke(command, args,
                                      catch_exceptions=False,
                                      obj=globalOptions)
        finally:
            # If a command ends without making an API call, execute() is not
            # awaited. We close it to avoid a RuntimeWarning.
            executer.close()

    def add_password(self, name):
        """Add a (poor) password to the password file for the given user."""
        passwordFile = HtpasswdFile(str(self.db_path / 'passwords'))
        passwordFile.set_password(name, f'{name[::-1]}')
        passwordFile.save()

    def has_password(self, name):
        """Does an entry for the given user exist in the password file?"""
        passwordFile = HtpasswdFile(str(self.db_path / 'passwords'))
        return passwordFile.get_hash(name) is not None

    def has_token(self, token_id):
        """Does a token with the given ID exist?"""
        return (self.db_path / 'tokens' / f'{token_id}.xml').is_file()

@fixture
def cli(tmp_path):
    return SoftFabCLI(tmp_path)


# Functions that run commands and check results:

def check_no_user(cli, name):
    """Check that no user with the given name exists."""
    result = cli.run('user', 'show', name)
    assert result.exit_code == 1
    assert result.output == f"softfab: User not found: {name}\n"
    assert not cli.has_password(name)

def check_user_role(cli, name, role, password=True):
    """Check that a user with the given name exists and has the given role."""
    result = cli.run('user', 'show', name, '--json')
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {'name': name, 'role': role}
    assert cli.has_password(name) == password

def add_user(cli, name, role=None, duplicate=False):
    """Add a user account."""
    command = ['user', 'add', name]
    if role is None:
        role = 'user'
    else:
        command += ['--role', role]
    result = cli.run(*command)
    if duplicate:
        assert result.exit_code == 1
        assert result.output == f"softfab: User already exists: {name}\n"
    else:
        assert result.exit_code == 0
        assert result.output == f"softfab: {role.title()} account '{name}' created\n"
        cli.add_password(name)

def remove_user(cli, name, force=True, exists=True):
    """Remove a user account."""
    command = ['user', 'remove', name]
    if force:
        command += ['--force']
    result = cli.run(*command)
    if force:
        if exists:
            assert result.exit_code == 0
            assert result.output == f"softfab: Account '{name}' removed\n"
        else:
            assert result.exit_code == 1
            assert result.output == f"softfab: User not found: {name}\n"
    else:
        assert result.exit_code == 2
        assert result.output.startswith("softfab: Account was NOT removed\n")

def block_user(cli, name, exists=True):
    """Block a user account."""
    result = cli.run('user', 'block', name)
    if exists:
        assert result.exit_code == 0
        assert result.output == f"softfab: Account '{name}' blocked\n"
    else:
        assert result.exit_code == 1
        assert result.output == f"softfab: User not found: {name}\n"

def set_role(cli, name, role, exists=True):
    """Change the role of a user account."""
    command = ['user', 'role', name, role]
    result = cli.run(*command)
    if exists:
        assert result.exit_code == 0
        assert result.output == f"softfab: Role of account '{name}' set to '{role}'\n"
    else:
        assert result.exit_code == 1
        assert result.output == f"softfab: User not found: {name}\n"

def check_reset_password(cli, name, exists=True):
    """Reset a user's password."""
    command = ['user', 'reset', name]
    result = cli.run(*command)
    if exists:
        assert result.exit_code == 0
        lines = result.output.strip().split('\n')
        assert lines[0] == f"softfab: Password of account '{name}' was reset"
        url = urlparse(lines[-1])
        assert url.path.endswith('/SetPassword'), url
        query = parse_qs(url.query)
        assert query.keys() == {'token', 'secret'}, url
        tokenId, = query['token']
        assert cli.has_token(tokenId), tokenId
        assert not cli.has_password(name)
        return tokenId
    else:
        assert result.exit_code == 1
        assert result.output == f"softfab: User not found: {name}\n"
        return None


# Test cases:

@mark.parametrize('role', sorted(roleNames) + [None])
def test_create_user(cli, role):
    # Add a user.
    check_no_user(cli, 'alice')
    add_user(cli, 'alice', role)
    check_user_role(cli, 'alice', role or 'user')

    # Attempt to add the same user again.
    add_user(cli, 'alice', role, duplicate=True)

def test_remove_user(cli):
    # Attempt to remove user that never existed.
    remove_user(cli, 'alice', force=False)
    remove_user(cli, 'alice', exists=False)
    check_no_user(cli, 'alice')

    # Add user and remove them.
    add_user(cli, 'bob', 'user')
    check_user_role(cli, 'bob', 'user')
    remove_user(cli, 'bob', force=False)
    check_user_role(cli, 'bob', 'user')
    remove_user(cli, 'bob')
    check_no_user(cli, 'bob')

    # Attempt to remove a user that was already removed.
    remove_user(cli, 'bob', force=False)
    remove_user(cli, 'bob', exists=False)
    check_no_user(cli, 'bob')

def test_block_user(cli):
    # Add user and block them.
    add_user(cli, 'dave', 'operator')
    check_user_role(cli, 'dave', 'operator')
    block_user(cli, 'dave')
    check_user_role(cli, 'dave', 'inactive', password=False)

    # Block the same user again; should succeed with no effect.
    block_user(cli, 'dave')
    check_user_role(cli, 'dave', 'inactive', password=False)

    # Attempt to block user that never existed.
    block_user(cli, 'alice', exists=False)
    check_no_user(cli, 'alice')

def test_user_role(cli):
    # Change role of existing user.
    add_user(cli, 'alice', 'guest')
    check_user_role(cli, 'alice', 'guest')
    set_role(cli, 'alice', 'inactive')
    check_user_role(cli, 'alice', 'inactive')

    # Attempt to change role of non-existing user.
    set_role(cli, 'bob', 'operator', exists=False)

def test_reset_password(cli):
    # Add user and reset their password.
    add_user(cli, 'alice')
    token1 = check_reset_password(cli, 'alice')

    # Reset the password again; should produce a new token.
    token2 = check_reset_password(cli, 'alice')
    assert token1 != token2
    assert not cli.has_token(token1)

    # Block user; should remove token.
    block_user(cli, 'alice')
    assert not cli.has_token(token2)

    # Attempt to reset password of non-existing user.
    check_reset_password(cli, 'bob', exists=False)

def test_bad_user_name(cli):
    # Attempt to add user with an invalid name.
    result = cli.run('user', 'add', 'robert/../tables')
    assert result.exit_code == 1
    assert result.output == f'softfab: Invalid character in user name "robert/../tables"\n'
