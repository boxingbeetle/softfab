# SPDX-License-Identifier: BSD-3-Clause

"""
Wraps the Twisted reactor in a way that makes it more friendly to mypy.

U{https://twistedmatrix.com/trac/ticket/9909}
"""

from typing import cast

from twisted.internet.interfaces import (
    IReactorCore, IReactorProcess, IReactorTime
)
import twisted.internet.reactor


class IReactor(IReactorCore, IReactorProcess, IReactorTime):
    """Combines the reactor interfaces that the Control Center uses."""

reactor = cast(IReactor, twisted.internet.reactor)
"""Twisted's default reactor, in a way mypy can deal with."""
