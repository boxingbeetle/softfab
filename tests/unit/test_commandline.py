# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the command line interface."""

import json

from click import Group
from click.testing import CliRunner
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

@fixture
def run_cmd(tmp_path):
    runner = CliRunner()

    def invoke(*words):
        command, args = find_command(words)

        # Reactors cannot be restarted, so use a fresh one for every command.
        globalOptions = MemoryOptions()
        reactor = globalOptions.reactor
        reactor.callWhenRunning(runCoroutine, reactor,
                                execute(reactor, tmp_path))

        return runner.invoke(command, args,
                             catch_exceptions=False,
                             obj=globalOptions)
    return invoke


# Functions that run commands and check results:

def check_no_user(run_cmd, name):
    """Check that no user with the given name exists."""
    result = run_cmd('user', 'show', name)
    assert result.exit_code == 1
    assert result.output == f"softfab: User not found: {name}\n"

def check_user_role(run_cmd, name, role):
    """Check that a user with the given name exists and has the given role."""
    result = run_cmd('user', 'show', name, '--json')
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {'name': name, 'role': role}

def add_user(run_cmd, name, role=None):
    """Add a user."""
    command = ['user', 'add', name]
    if role is None:
        role = 'user'
    else:
        command += ['--role', role]
    result = run_cmd(*command)
    assert result.exit_code == 0
    assert result.output == f"softfab: {role.title()} account '{name}' created\n"


# Test cases:

@mark.parametrize('role', list(roleNames) + [None])
def test_create_user(run_cmd, role):
    check_no_user(run_cmd, 'alice')
    add_user(run_cmd, 'alice', role)
    check_user_role(run_cmd, 'alice', role or 'user')
