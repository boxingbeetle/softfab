# SPDX-License-Identifier: BSD-3-Clause

'''The Atom Syndication Format is a feed format similar in purpose to RSS,
but much better defined.
Its specification is in RFC 4287:  http://tools.ietf.org/html/rfc4287
'''

from os.path import basename
from time import gmtime, strftime
from typing import Iterator

from softfab.ControlPage import ControlPage
from softfab.Page import PageProcessor
from softfab.UIPage import iterStyleSheets
from softfab.config import dbDir, homePage, rootURL
from softfab.databaselib import RecordObserver
from softfab.datawidgets import DataColumn, DataTable
from softfab.joblib import jobDB
from softfab.jobview import CommentPanel, JobsSubTable
from softfab.pagelinks import createJobURL, createUserDetailsURL
from softfab.projectlib import project
from softfab.querylib import CustomFilter, KeySorter, runQuery
from softfab.timelib import getTime
from softfab.timeview import formatDuration, formatTime
from softfab.userlib import checkPrivilege
from softfab.utils import pluralize
from softfab.version import version
from softfab.webgui import Table, cell, pageURL, row
from softfab.xmlgen import atom, xhtml

# TODO: Give each factory a truly unique ID.
factoryId = basename(dbDir)

class MostRecent(RecordObserver):
    '''Keeps a list of the N (N=50) most recent jobs.
    '''

    def __init__(self, db, key, number):
        RecordObserver.__init__(self)
        self.number = number
        query = [ CustomFilter(lambda job: job.hasFinalResult()),
            KeySorter([ key ], db) ]
        self.records = runQuery(query, db)[ : number]
        db.addObserver(self)

    def added(self, record):
        self.updated(record)

    def removed(self, record):
        assert False, 'job %s removed' % record.getId()

    def updated(self, record):
        if record.hasFinalResult():
            self.records.insert(0, record)
            self.records[self.number : ] = []

class JobResultColumn(DataColumn):
    label = 'Result'

    def presentCell(self, record, **kwargs):
        return record.getResult()

class SingleJobTable(JobsSubTable):
    #descriptionLink = False
    statusColumn = JobResultColumn.instance

    def __init__(self, job):
        self.__job = job
        JobsSubTable.__init__(self)

    def getRecordsToQuery(self, proc):
        return [ self.__job ]

class TasksTable(Table):
    columns = 'Task', 'Start Time', 'Duration', 'Summary', 'Result'

    def iterRows(self, *, proc, **kwargs):
        for task in proc.job.getTaskSequence():
            yield row(class_ = task.getResult())[
                task.getName(),
                formatTime(task['starttime']),
                cell(class_ = 'rightalign')[formatDuration(task.getDuration())],
                task.getSummaryHTML(),
                task.getResult()
                ]

class Feed_GET(ControlPage[ControlPage.Arguments, 'Feed_GET.Processor']):
    contentType = 'application/atom+xml; charset=UTF-8'

    def checkAccess(self, req):
        checkPrivilege(req.user, 'j/l')
        checkPrivilege(req.user, 'j/a')

    class Processor(PageProcessor):
        # N (where N=50) MostRecent & Completed Jobs
        recentJobs = MostRecent(jobDB, 'recent', 50)

        def process(self, req):
            jobs = list(self.recentJobs.records)

            # pylint: disable=attribute-defined-outside-init
            self.jobs = jobs
            self.tables = [ SingleJobTable(job) for job in jobs ]

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield from proc.tables

    def writeReply(self, response, proc):
        response.write('<?xml version="1.0" encoding="utf-8"?>')
        # Note: Using an "xml:base" attribute here and relative URLs in the rest
        #       of the feed works fine in Akregator (KDE4 version), but fails in
        #       Outlook 2007. Therefore we should only use absolute URLs.
        response.write(atom.feed(
            xmlns = 'http://www.w3.org/2005/Atom',
            )[
            self.presentFeed(proc)
            ])

    def presentFeed(self, proc):
        projectName = project['name']
        yield atom.title[ '%s SoftFab - Recent Jobs' % projectName ]
        yield atom.subtitle[
            'The most recent jobs running in the %s SoftFab' % projectName
            ]
        yield atom.id[ 'urn:softfab:%s:jobs' % factoryId ]
        yield atom.updated[ self.presentTime(getTime()) ]
        yield atom.generator(uri = homePage, version = version)[ 'SoftFab' ]
        # TODO: Akregator for KDE4 won't show the icon, no matter what I try.
        #       Might be related to Konqueror often losing the icon.
        yield atom.icon[ rootURL + 'styles/SoftFabIcon.png' ]
        #yield atom.link(
            #rel = 'shortcut icon',
            #href = rootURL + 'styles/SoftFabIcon.png',
            #type = 'image/png',
            #)
        # Link to the Control Center.
        yield atom.link(
            rel = 'alternate',
            href = rootURL + 'Home',
            type = 'text/html',
            )
        # Link to the feed itself.
        yield atom.link(
            rel = 'self',
            href = rootURL + pageURL(self.name, proc.args),
            type = 'application/atom+xml',
            )
        for job, jobTable in zip(proc.jobs, proc.tables):
            yield atom.entry[ self.presentJob(proc, job, jobTable) ]

    def presentJob(self, proc, job, jobTable):
        jobId = job.getId()
        jobResult = job.getResult()
        owner = job.getOwner()
        projectName = project['name']
        tasksTable = TasksTable.instance
        jobComment = CommentPanel(job.comment)
        proc.job = job
        yield atom.title[ '%s: %s' % ( job.getDescription(), jobResult ) ]
        yield atom.link(href = rootURL + createJobURL(jobId))
        yield atom.id[ 'softfab:%s/jobs/%s' % ( factoryId, jobId ) ]
        yield atom.published[ self.presentTime(job.getCreateTime()) ]
        # TODO: More accurate last-modified time.
        yield atom.updated[ self.presentTime(job.getCreateTime()) ]
        if owner is not None:
            yield atom.author[
                atom.name[ owner ],
                atom.uri[ rootURL + createUserDetailsURL(owner) ],
                ]
        else:
            yield atom.author[
                atom.name[ '%s SoftFab' % projectName ],
                atom.uri[ rootURL + createJobURL(jobId) ],
                ]
        # Note: The Atom spec requires all XHTML to be inside a single <div>.
        yield atom.summary(type = 'xhtml')[ xhtml.div[
            # TODO: Does xhtml.style work with other RSS readers too?
            xhtml.style[(
                '@import url(%s%s);' % (rootURL, sheet.getURL())
                for sheet in iterStyleSheets(proc)
                )],
            jobTable.present(proc=proc),
            xhtml.p[ self.presentJobInfo(job) ],
            tasksTable.present(proc=proc),
            jobComment.present(proc=proc),
            ] ]

    def presentJobInfo(self, job):
        # TODO: Make this a general function in jobview.py
        #       current code is copied from ShowReport.py
        jobId = job.getId()
        numTasks = len(job.getTaskSequence())
        configId = job.getConfigId()
        yield 'Job ', jobId, ' was created from ', (
            'scratch' if configId is None else (
                'configuration ', xhtml.b[ configId ]
                ),
            ' and contains ', str(numTasks), ' ', pluralize('task', numTasks),
            ':'
            )

    def presentTime(self, seconds):
        '''Present the given time stamp in seconds since the epoch in the format
        specified by RFC 3339.
        '''
        yield strftime('%Y-%m-%dT%H:%M:%SZ', gmtime(seconds))
