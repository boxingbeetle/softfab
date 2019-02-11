"""Web application for orchestrating build and test execution.

You can read about SoftFab on its
[home page](https://boxingbeetle.com/tools/softfab/).
What follows here is a quick tour of the code.

Overview
========

SoftFab consists of a *Control Center*, which is the web application that
users interact with, and one or more *Task Runners*, which are agents that
handle execution of build and test tasks. The code you are looking at now
is the Control Center.

The Control Center runs under [Twisted](https://twistedmatrix.com/),
an event-driven networking engine. This means that requests are handled
asynchronously: whenever the Control Center has to wait for data,
it registers an event handler (using Twisted's `deferred` mechanism)
and execution returns to Twisted's event loop (`reactor`).

TODO: More tour.
"""
