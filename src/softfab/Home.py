# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from StyleResources import styleRoot
from Page import PageProcessor
from databaselib import RecordObserver
from joblib import jobDB
from jobview import JobsSubTable
from querylib import KeySorter, runQuery
from webgui import docLink, pageLink, pageURL
from xmlgen import xhtml

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
        assert False, 'job %s removed' % record.getId()

    def updated(self, record):
        pass

class RecentJobsTable(JobsSubTable):
    widgetId = 'recentJobsTable'
    autoUpdate = True

    def getRecordsToQuery(self, proc):
        return proc.recentJobs.records

class Home(FabPage):
    icon = 'IconHome'
    description = 'Home'
    children = [
        'LoadExecute', 'ReportIndex', 'ResourceIndex', 'ScheduleIndex',
        'Configure'
        ]
    feedIcon = styleRoot.addIcon('feed-icon-14x14')

    class Processor(PageProcessor):
        recentJobs = MostRecent(jobDB, 'recent', 50)

    def checkAccess(self, req):
        req.checkPrivilege('j/l')

    def iterWidgets(self, proc):
        yield RecentJobsTable

    def iterDataTables(self, proc):
        yield RecentJobsTable.instance

    def presentHeadParts(self, proc):
        yield FabPage.presentHeadParts(self, proc)
        yield xhtml.link(
            rel = 'alternate',
            type = 'application/atom+xml',
            href = pageURL('Feed'),
            title = 'SoftFab Jobs Atom Feed',
            )

    def presentContent(self, proc):
        atomFeedLink = pageLink('Feed')[
            self.feedIcon.present(proc=proc)
            ]
        yield xhtml.h2[ 'Recent Jobs ', atomFeedLink ]
        yield RecentJobsTable.instance.present(proc=proc)

        if len(jobDB) < 20:
            yield xhtml.p[
                'For help to get started, please read the ',
                docLink('/reference/user_manual/')[ 'User Manual' ],
                ' or go to the general ',
                docLink('/')[ 'Documentation page' ], '.'
                ]
