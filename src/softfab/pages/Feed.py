# SPDX-License-Identifier: BSD-3-Clause

'''The Atom Syndication Format is a feed format similar in purpose to RSS,
but much better defined.
Its specification is in RFC 4287:  http://tools.ietf.org/html/rfc4287
'''

from os.path import basename
from time import gmtime, strftime
from typing import Any, ClassVar, Collection, Iterator, List

from softfab.ControlPage import ControlPage
from softfab.Page import PageProcessor
from softfab.StyleResources import styleRoot
from softfab.UIPage import factoryStyleSheet
from softfab.compat import NoReturn
from softfab.config import dbDir, rootURL
from softfab.configlib import ConfigDB
from softfab.databaselib import RecordObserver
from softfab.datawidgets import DataColumn, DataTable
from softfab.joblib import Job, JobDB
from softfab.jobview import CommentPanel, JobsSubTable, presentJobCaption
from softfab.pagelinks import createJobURL, createUserDetailsURL
from softfab.projectlib import project
from softfab.querylib import CustomFilter, KeySorter, RecordProcessor, runQuery
from softfab.request import Request
from softfab.response import Response
from softfab.schedulelib import ScheduleDB
from softfab.taskview import taskSummary
from softfab.timelib import getTime
from softfab.timeview import formatDuration, formatTime
from softfab.userlib import User, UserDB, checkPrivilege
from softfab.version import HOMEPAGE, VERSION
from softfab.webgui import Table, cell, pageURL, row
from softfab.xmlgen import XMLContent, atom, xhtml

# TODO: Give each factory a truly unique ID.
factoryId = basename(dbDir)

class MostRecent(RecordObserver[Job]):
    '''Keeps a list of the N (N=50) most recent completed jobs.
    Unlike the Home page, we only care about jobs with have a final result.
    '''

    def __init__(self, db: JobDB, key: str, number: int):
        super().__init__()
        self.number = number
        query: List[RecordProcessor] = [
            CustomFilter(Job.hasFinalResult),
            KeySorter.forDB([key], db)
            ]
        self.records = runQuery(query, db)[ : number]
        db.addObserver(self)

    def added(self, record: Job) -> None:
        self.updated(record)

    def removed(self, record: Job) -> NoReturn:
        assert False, f'job {record.getId()} removed'

    def updated(self, record: Job) -> None:
        if record.hasFinalResult():
            self.records.insert(0, record)
            self.records[self.number : ] = []

class JobResultColumn(DataColumn[Job]):
    label = 'Result'

    def presentCell(self, record: Job, **kwargs: object) -> XMLContent:
        return record.result

class SingleJobTable(JobsSubTable):
    #descriptionLink = False
    statusColumn = JobResultColumn.instance

    def __init__(self, job: Job):
        self.__job = job
        super().__init__()

    def getRecordsToQuery( # pylint: disable=unused-argument
                          self, proc: PageProcessor) -> Collection[Job]:
        return [ self.__job ]

class TasksTable(Table):
    columns = 'Task', 'Start Time', 'Duration', 'Summary', 'Result'

    def iterRows(self, **kwargs: Any) -> Iterator[XMLContent]:
        job: Job = kwargs['job']
        for task in job.getTaskSequence():
            yield row(class_ = task.result)[
                task.getName(),
                formatTime(task.startTime),
                cell(class_ = 'rightalign')[formatDuration(task.getDuration())],
                taskSummary(task),
                task.result
                ]

class Feed_GET(ControlPage[ControlPage.Arguments, 'Feed_GET.Processor']):
    contentType = 'application/atom+xml; charset=UTF-8'

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'j/l')
        checkPrivilege(user, 'j/a')

    class Processor(PageProcessor[ControlPage.Arguments]):

        configDB: ClassVar[ConfigDB]
        jobDB: ClassVar[JobDB]
        scheduleDB: ClassVar[ScheduleDB]
        userDB: ClassVar[UserDB]
        _mostRecent: ClassVar[MostRecent]

        @property
        def recentJobs(self) -> MostRecent:
            try:
                return getattr(self, '_mostRecent')
            except AttributeError:
                mostRecent = MostRecent(self.jobDB, 'recent', 50)
                self.__class__._mostRecent = mostRecent # pylint: disable=protected-access
                return mostRecent

        async def process(self,
                          req: Request['Feed_GET.Arguments'],
                          user: User
                          ) -> None:
            jobs = list(self.recentJobs.records)

            # pylint: disable=attribute-defined-outside-init
            self.jobs = jobs
            self.tables = [ SingleJobTable(job) for job in jobs ]

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Any]]:
        yield from proc.tables

    async def writeReply(self, response: Response, proc: Processor) -> None:
        response.write('<?xml version="1.0" encoding="utf-8"?>')
        # Note: Using an "xml:base" attribute here and relative URLs in the rest
        #       of the feed works fine in Akregator (KDE4 version), but fails in
        #       Outlook 2007. Therefore we should only use absolute URLs.
        response.writeXML(atom.feed(
            xmlns = 'http://www.w3.org/2005/Atom',
            )[
            self.presentFeed(proc, rootURL)
            ])

    def presentFeed(self, proc: Processor, ccURL: str) -> XMLContent:
        projectName = project.name
        yield atom.title[ f'{projectName} SoftFab - Recent Jobs' ]
        yield atom.subtitle[
            f'The most recent jobs running in the {projectName} SoftFab'
            ]
        yield atom.id[ f'urn:softfab:{factoryId}:jobs' ]
        yield atom.updated[ self.presentTime(getTime()) ]
        yield atom.generator(uri=HOMEPAGE, version=VERSION)[ 'SoftFab' ]
        # TODO: Akregator for KDE4 won't show the icon, no matter what I try.
        #       Might be related to Konqueror often losing the icon.
        yield atom.icon[ ccURL + 'styles/SoftFabIcon.png' ]
        #yield atom.link(
            #rel = 'shortcut icon',
            #href = ccURL + 'styles/SoftFabIcon.png',
            #type = 'image/png',
            #)
        # Link to the Control Center.
        yield atom.link(
            rel = 'alternate',
            href = ccURL + 'Home',
            type = 'text/html',
            )
        # Link to the feed itself.
        yield atom.link(
            rel = 'self',
            href = ccURL + pageURL(self.name, proc.args),
            type = 'application/atom+xml',
            )
        for job, jobTable in zip(proc.jobs, proc.tables):
            yield atom.entry[ self.presentJob(proc, ccURL, job, jobTable) ]

    def presentJob(self,
                   proc: Processor,
                   ccURL: str,
                   job: Job,
                   jobTable: SingleJobTable
                   ) -> XMLContent:
        jobId = job.getId()
        jobResult = job.result
        owner = job.owner
        projectName = project.name
        jobComment = CommentPanel(job.comment)
        yield atom.title[ f'{job.getDescription()}: ', jobResult ]
        yield atom.link(href = ccURL + createJobURL(jobId))
        yield atom.id[ f'softfab:{factoryId}/jobs/{jobId}' ]
        yield atom.published[ self.presentTime(job.getCreateTime()) ]
        # TODO: More accurate last-modified time.
        yield atom.updated[ self.presentTime(job.getCreateTime()) ]
        if owner is not None:
            yield atom.author[
                atom.name[ owner ],
                atom.uri[ ccURL + createUserDetailsURL(owner) ],
                ]
        else:
            yield atom.author[
                atom.name[ f'{projectName} SoftFab' ],
                atom.uri[ ccURL + createJobURL(jobId) ],
                ]
        # Note: The Atom spec requires all XHTML to be inside a single <div>.
        styleURL = ccURL + styleRoot.relativeURL
        presentationArgs = dict(proc=proc, styleURL=styleURL)
        yield atom.summary(type = 'xhtml')[ xhtml.div[
            # TODO: Does xhtml.style work with other RSS readers too?
            xhtml.style[(
                f'@import url({styleURL}/{factoryStyleSheet.path});'
                )],
            jobTable.present(**presentationArgs),
            xhtml.p[ presentJobCaption(proc.configDB, job) ],
            TasksTable.instance.present(job=job, **presentationArgs),
            jobComment.present(**presentationArgs),
            ] ]

    def presentTime(self, seconds: int) -> str:
        '''Present the given time stamp in seconds since the epoch in the format
        specified by RFC 3339.
        '''
        return strftime('%Y-%m-%dT%H:%M:%SZ', gmtime(seconds))
