# SPDX-License-Identifier: BSD-3-Clause

from platform import python_version
from typing import Iterator, List, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor
from softfab.packaging import dependencies, getDistribution
from softfab.projectlib import getBootTime, project
from softfab.timeview import formatTime
from softfab.userlib import User
from softfab.utils import parseVersion
from softfab.version import VERSION as softFabVersion
from softfab.webgui import Column, Table, docLink, maybeLink
from softfab.xmlgen import XMLContent, xhtml


class About_GET(FabPage[FabPage.Processor, FabPage.Arguments]):
    icon = 'IconHome'
    description = 'About'

    def checkAccess(self, user: User) -> None:
        pass

    def presentContent(self, **kwargs: object) -> XMLContent:
        yield xhtml.h2[ 'SoftFab ', softFabVersion ]

        yield xhtml.h3[ 'Status' ]
        yield StatusTable.instance.present(**kwargs)

        yield xhtml.h3[ 'Installation' ]
        yield xhtml.p[
            'This Control Center runs on the following '
            'open source software:'
            ]
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
    packageColumn = Column('Package')
    versionColumn = Column('Version', cellStyle='centeralign')
    descriptionColumn = Column('Description')

    def showVersions(self, **kwargs: object) -> bool:
        proc = cast(FabPage.Processor, kwargs['proc'])
        return proc.user.hasPrivilege('sysver')

    def iterColumns(self, **kwargs: object) -> Iterator[Column]:
        yield self.packageColumn
        if self.showVersions(**kwargs):
            yield self.versionColumn
        yield self.descriptionColumn

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        showVersions = self.showVersions(**kwargs)

        names = list(dependencies('softfab'))
        names.append('Python')
        names.sort(key=str.casefold)

        for name in names:
            if name == 'Python':
                version = python_version()
                url = 'https://www.python.org/'
                desc = "An interpreted, interactive, " \
                       "object-oriented programming language"
            else:
                dist = getDistribution(name)
                if dist is None:
                    continue
                version = dist.version
                metadata = dist.metadata
                url = metadata['Home-page']
                desc = metadata['Summary'].rstrip('.')

            row: List[XMLContent]
            row = [ maybeLink(url)[name] ]
            if showVersions:
                row.append(version)
            row.append(desc)
            yield row

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
