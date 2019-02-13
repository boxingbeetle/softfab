# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.projectlib import getBootTime, project
from softfab.timeview import formatTime
from softfab.utils import parseVersion
from softfab.version import version as softFabVersion
from softfab.webgui import Table, docLink
from softfab.xmlgen import xhtml

from passlib import __version__ as passlibVersion
from twisted import __version__ as twistedVersion

from platform import python_version

try:
    import twisted.mail.smtp # pylint: disable=unused-import
except ImportError:
    twistedMail = False
else:
    twistedMail = True

try:
    from pytz import VERSION as pytzVersion
except ImportError:
    pytzVersion = 'not installed'

try:
    from pygraphviz import __version__ as pyGraphvizVersion
except ImportError:
    pyGraphvizVersion = 'not installed'

class About(FabPage):
    icon = 'IconHome'
    description = 'About'

    def checkAccess(self, req):
        pass

    def presentContent(self, proc):
        yield xhtml.h2[ 'Status' ]
        yield StatusTable.instance.present(proc=proc)

        yield xhtml.h2[ 'Installation' ]
        yield InstallationTable.instance.present(proc=proc)

        yield xhtml.h2[ 'Web Browser' ]
        yield BrowserTable.instance.present(proc=proc)
        yield (
            xhtml.p[ 'Raw user agent string:' ],
            xhtml.pre(style = 'white-space: pre-wrap')[
                proc.req.userAgent.rawUserAgent
                ]
            )

        yield xhtml.h2[ 'Documentation' ]
        yield (
            xhtml.p[
                'The complete set of SoftFab documentation can be found on the ',
                docLink('/')['documentation pages'],
                '.'
                ]
            )

class StatusTable(Table):
    columns = None, None

    def iterRows(self, **kwargs):
        yield 'Up since', (
            formatTime(getBootTime())
            )
        dbVersion = project['version']
        yield 'Database version', (
            dbVersion
            if parseVersion(dbVersion)[:2] == parseVersion(softFabVersion)[:2]
            else xhtml.span(style = 'color: red')[
                dbVersion + ' (database must be upgraded)'
                ]
            )

class InstallationTable(Table):
    columns = None, None

    def iterRows(self, **kwargs):
        yield 'SoftFab version:', softFabVersion
        yield 'Twisted version:', twistedVersion
        yield 'twisted.mail package:', (
            'installed' if twistedMail else 'not installed'
            )
        yield 'Passlib version:', passlibVersion
        yield 'PyGraphviz version:', pyGraphvizVersion
        yield 'pytz version:', pytzVersion
        yield 'Python version:', python_version()

class BrowserTable(Table):
    columns = None, None

    def iterRows(self, proc, **kwargs):
        userAgent = proc.req.userAgent
        yield 'Browser:', userAgent.family or 'unknown'
        versionTuple = userAgent.version
        if versionTuple is None:
            version = 'unknown'
        else:
            version = '.'.join(str(i) for i in versionTuple)
        yield 'Version:', version
        yield 'Operating system:', userAgent.operatingSystem or 'unknown'
        yield 'Accepts XHTML:', 'yes' if userAgent.acceptsXHTML else 'no'
