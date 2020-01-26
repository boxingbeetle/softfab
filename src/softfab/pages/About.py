# SPDX-License-Identifier: BSD-3-Clause

from platform import python_version
from typing import Iterator, cast

from passlib import __version__ as passlibVersion
from twisted import __version__ as twistedVersion

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.notification import sendmail
from softfab.projectlib import getBootTime, project
from softfab.timeview import formatTime
from softfab.userlib import User
from softfab.utils import parseVersion
from softfab.version import VERSION as softFabVersion
from softfab.webgui import Table, docLink
from softfab.xmlgen import XMLContent, xhtml

try:
    from pytz import VERSION as pytzVersion
except ImportError:
    pytzVersion = 'not installed'

class About_GET(FabPage[FabPage.Processor, FabPage.Arguments]):
    icon = 'IconHome'
    description = 'About'

    def checkAccess(self, user: User) -> None:
        pass

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield xhtml.h3[ 'Status' ]
        yield StatusTable.instance.present(**kwargs)

        yield xhtml.h3[ 'Installation' ]
        yield InstallationTable.instance.present(**kwargs)

        proc = cast(FabPage.Processor, kwargs['proc'])
        yield xhtml.h3[ 'Web Browser' ]
        yield BrowserTable.instance.present(**kwargs)
        yield (
            xhtml.p[ 'Raw user agent string:' ],
            xhtml.pre(style = 'white-space: pre-wrap')[
                proc.req.userAgent.rawUserAgent
                ]
            )

        yield xhtml.h3[ 'Documentation' ]
        yield (
            xhtml.p[
                'The complete set of SoftFab documentation can be found '
                'on the ', docLink('/')['documentation pages'],
                '.'
                ]
            )

class StatusTable(Table):
    columns = None, None

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        yield 'Up since', (
            formatTime(getBootTime())
            )
        dbVersion = project.dbVersion
        yield 'Database version', (
            dbVersion
            if parseVersion(dbVersion)[:2] == parseVersion(softFabVersion)[:2]
            else xhtml.span(style = 'color: red')[
                dbVersion + ' (database must be upgraded)'
                ]
            )

class InstallationTable(Table):
    columns = None, None

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        yield 'SoftFab version:', softFabVersion
        yield 'Twisted version:', twistedVersion
        yield 'twisted.mail package:', (
            'not installed' if sendmail is None else 'installed'
            )
        yield 'Passlib version:', passlibVersion
        yield 'pytz version:', pytzVersion
        yield 'Python version:', python_version()

class BrowserTable(Table):
    columns = None, None

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(PageProcessor, kwargs['proc'])
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
