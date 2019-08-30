# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, Optional

from softfab.FabPage import FabPage, LinkBarButton
from softfab.Page import PageProcessor
from softfab.StyleResources import styleRoot
from softfab.databaselib import RecordObserver
from softfab.datawidgets import DataTable
from softfab.joblib import jobDB
from softfab.jobview import JobsSubTable
from softfab.querylib import KeySorter, runQuery
from softfab.userlib import User, checkPrivilege
from softfab.webgui import Widget, docLink, pageLink, pageURL
from softfab.xmlgen import XMLContent, xhtml


class MostRecent(RecordObserver):
    '''Keeps a list of the N most recent jobs.
    '''

    def __init__(self, db, key, number):
        RecordObserver.__init__(self)
        self.number = number
        query = [ KeySorter([ key ], db) ]
        self.records = runQuery(query, db)[ : number]
        db.addObserver(self)

    def added(self, record):
        self.records.insert(0, record)
        self.records[self.number : ] = []

    def removed(self, record):
        assert False, f'job {record.getId()} removed'

    def updated(self, record):
        pass

class RecentJobsTable(JobsSubTable):
    widgetId = 'recentJobsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc):
        return proc.recentJobs.records

class Home_GET(FabPage['Home_GET.Processor', FabPage.Arguments]):
    icon = 'IconHome'
    description = 'Home'
    children = [
        'LoadExecute', 'ReportIndex', 'ResourceIndex', 'ScheduleIndex',
        'Configure'
        ]
    feedIcon = styleRoot.addIcon('feed-icon')(
        alt='Feed', title='Atom feed', width=17, height=17
        )
    docsButton = LinkBarButton('Docs', 'docs/', styleRoot.addIcon('IconHome'))

    class Processor(PageProcessor[FabPage.Arguments]):
        recentJobs = MostRecent(jobDB, 'recent', 50)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/l')

    def iterChildButtons(self,
                         args: Optional[FabPage.Arguments]
                         ) -> Iterator[LinkBarButton]:
        yield from super().iterChildButtons(args)
        yield self.docsButton

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        yield RecentJobsTable.instance

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield RecentJobsTable.instance

    def presentHeadParts(self, **kwargs: object) -> XMLContent:
        yield super().presentHeadParts(**kwargs)
        yield xhtml.link(
            rel = 'alternate',
            type = 'application/atom+xml',
            href = pageURL('Feed'),
            title = 'SoftFab Jobs Atom Feed',
            )

    def presentContent(self, **kwargs: object) -> XMLContent:
        atomFeedLink = pageLink('Feed')[
            self.feedIcon.present(**kwargs)
            ]
        yield xhtml.h3[ 'Recent Jobs ', atomFeedLink ]
        yield RecentJobsTable.instance.present(**kwargs)

        if len(jobDB) < 20:
            yield xhtml.p[
                'For help to get started, please read the ',
                docLink('/start/')[ 'Getting Started' ],
                ' section of the documentation.'
                ]
