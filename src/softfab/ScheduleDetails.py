# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from Page import PageProcessor
from RecordDelete import DeleteArgs
from config import enableSecurity
from configlib import configDB
from pagelinks import ConfigIdArgs, createConfigDetailsLink
from schedulelib import ScheduleRepeat, scheduleDB
from schedulerefs import ScheduleIdArgs
from scheduleview import (
    createLastJobLink, describeNextRun, getScheduleStatus, stringToListDays
    )
from selectview import TagArgs
from utils import pluralize
from webgui import PropertiesTable, Table, cell, pageLink, row
from xmlgen import xhtml

def statusDescription(scheduled):
    status = getScheduleStatus(scheduled)
    if status == 'error':
        return xhtml.br.join(
            ( 'configuration ', xhtml.b[ createConfigDetailsLink(configId) ],
              ' is inconsistent' )
            for configId in scheduled.getMatchingConfigIds()
            if not configDB[configId].hasValidInputs()
            )
    else:
        return {
            'running': 'jobs from last run have not finished yet',
            'warning': 'no matching configurations',
            'ok': 'waiting for next run',
            }.get(status, status)

class TagsTable(Table):
    columns = None, None
    style = 'hollow'
    def iterRows(self, proc, **kwargs):
        tagKey = proc.scheduled['tagKey']
        tagValue = proc.scheduled['tagValue']
        numMatches = len(proc.scheduled.getMatchingConfigIds())
        yield 'key:\u00A0', tagKey
        yield 'value:\u00A0', tagValue
        tagArgs = TagArgs(tagkey = tagKey, tagvalue = tagValue)
        yield cell(colspan = 2)[
            pageLink('LoadExecute', tagArgs)[ 'view' ],
            ' or ',
            pageLink('FastExecute', tagArgs)[ 'execute' ],
            ' %d matching configurations' % numMatches,
            ],

class DetailsTable(PropertiesTable):
    widgetId = 'detailsTable'
    autoUpdate = True

    def iterRows(self, proc, **kwargs):
        scheduled = proc.scheduled
        configId = scheduled['configId']
        if configId is None:
            yield 'Tag', TagsTable.instance.present(proc=proc, **kwargs)
        else:
            yield 'Configuration', (
                createConfigDetailsLink(configId, 'view'),
                ' or ',
                pageLink('FastExecute', ConfigIdArgs(configId = configId))[
                    'execute'
                    ],
                ' configuration "%s"' % configId
                )
        yield 'Last run', createLastJobLink(scheduled)
        yield 'Next run', describeNextRun(scheduled)
        yield 'Repeat', scheduled['sequence']
        if scheduled['sequence'] is ScheduleRepeat.WEEKLY:
            yield 'Days', ', '.join(stringToListDays(scheduled['days']))
        elif scheduled['sequence'] is ScheduleRepeat.CONTINUOUSLY:
            minDelay = scheduled['minDelay']
            yield 'Minimum delay', '%d %s' % (
                minDelay, pluralize('minute', minDelay)
                )
        elif scheduled['sequence'] is ScheduleRepeat.PASSIVE:
            yield 'Triggered', 'yes' if scheduled['trigger'] else 'no'
            yield 'CM triggers', xhtml.br.join(
                sorted(scheduled.getTagValues('sf.cmtrigger'))
                )
        if enableSecurity:
            yield 'Owner', scheduled.getOwner() or '-'
        yield 'Comment', xhtml.br.join(scheduled.comment.splitlines())
        yield row(class_ = getScheduleStatus(scheduled))[
            'Status', statusDescription(scheduled)
            ]

class ScheduleDetails(FabPage):
    icon = 'IconSchedule'
    description = 'Schedule Details'

    class Arguments(ScheduleIdArgs):
        pass

    class Processor(PageProcessor):

        def process(self, req):
            # pylint: disable=attribute-defined-outside-init
            self.scheduled = scheduleDB.get(req.args.id)

    def checkAccess(self, req):
        req.checkPrivilege('s/a')

    def iterWidgets(self, proc):
        yield DetailsTable

    def presentContent(self, proc):
        scheduleId = proc.args.id
        scheduled = proc.scheduled
        if scheduled is None:
            yield xhtml.p[
                'Schedule ', xhtml.b[ scheduleId ], ' does not exist.'
                ]
            return

        yield xhtml.h2[ 'Details of schedule ', xhtml.b[ scheduleId ], ':' ]
        yield DetailsTable.instance.present(proc=proc)
        yield xhtml.p[
            xhtml.br.join((
                pageLink('ScheduleEdit', proc.args)[
                    'Edit this Schedule'
                    ],
                pageLink('DelSchedule', DeleteArgs(id = scheduleId))[
                    'Delete this Schedule'
                    ]
                ))
            ]
