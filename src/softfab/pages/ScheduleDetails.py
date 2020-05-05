# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError
from softfab.RecordDelete import DeleteArgs
from softfab.configlib import configDB
from softfab.pagelinks import ConfigIdArgs, createConfigDetailsLink
from softfab.projectlib import project
from softfab.request import Request
from softfab.schedulelib import ScheduleRepeat, Scheduled, scheduleDB
from softfab.schedulerefs import ScheduleIdArgs
from softfab.scheduleview import (
    createLastJobLink, describeNextRun, getScheduleStatus, stringToListDays
)
from softfab.selectview import TagArgs
from softfab.userlib import User, checkPrivilege
from softfab.utils import pluralize
from softfab.webgui import PropertiesTable, Table, Widget, cell, pageLink, row
from softfab.xmlgen import XML, XMLContent, xhtml


def statusDescription(scheduled: Scheduled) -> XMLContent:
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

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(ScheduleDetails_GET.Processor, kwargs['proc'])
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
            f' {numMatches:d} matching configurations',
            ],

class DetailsTable(PropertiesTable):
    widgetId = 'detailsTable'
    autoUpdate = True

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(ScheduleDetails_GET.Processor, kwargs['proc'])
        scheduled = proc.scheduled
        configId = scheduled.configId
        if configId is None:
            yield 'Tag', TagsTable.instance.present(**kwargs)
        else:
            yield 'Configuration', (
                createConfigDetailsLink(configId, 'view'),
                ' or ',
                pageLink('FastExecute', ConfigIdArgs(configId = configId))[
                    'execute'
                    ],
                f' configuration "{configId}"'
                )
        yield 'Last run', createLastJobLink(scheduled)
        yield 'Next run', describeNextRun(scheduled)
        repeat = scheduled.repeat
        yield 'Repeat', repeat
        if repeat is ScheduleRepeat.WEEKLY:
            yield 'Days', ', '.join(stringToListDays(scheduled.dayFlags))
        elif repeat is ScheduleRepeat.CONTINUOUSLY:
            minDelay = scheduled.minDelay
            yield 'Minimum delay', \
                f"{minDelay:d} {pluralize('minute', minDelay)}"
        elif repeat is ScheduleRepeat.TRIGGERED:
            yield 'Triggered', 'yes' if scheduled['trigger'] else 'no'
            yield 'Triggers', xhtml.br.join(
                sorted(scheduled.getTagValues('sf.trigger'))
                )
        if project.showOwners:
            yield 'Owner', scheduled.owner or '-'
        yield 'Comment', xhtml.br.join(scheduled.comment.splitlines())
        yield row(class_ = getScheduleStatus(scheduled))[
            'Status', statusDescription(scheduled)
            ]

class ScheduleDetails_GET(FabPage['ScheduleDetails_GET.Processor',
                                  'ScheduleDetails_GET.Arguments']):
    icon = 'IconSchedule'
    description = 'Schedule Details'

    class Arguments(ScheduleIdArgs):
        pass

    class Processor(PageProcessor[ScheduleIdArgs]):

        async def process(self,
                          req: Request[ScheduleIdArgs],
                          user: User
                          ) -> None:
            scheduleId = req.args.id
            try:
                # pylint: disable=attribute-defined-outside-init
                self.scheduled = scheduleDB[scheduleId]
            except KeyError:
                raise PresentableError(xhtml[
                    'Schedule ', xhtml.b[ scheduleId ], ' does not exist.'
                    ])

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 's/a')

    def iterWidgets(self, proc: Processor) -> Iterator[Widget]:
        yield DetailsTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ScheduleDetails_GET.Processor, kwargs['proc'])
        scheduleId = proc.args.id

        yield xhtml.h3[ 'Details of schedule ', xhtml.b[ scheduleId ], ':' ]
        yield DetailsTable.instance.present(**kwargs)
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

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        yield xhtml.p[ message ]
