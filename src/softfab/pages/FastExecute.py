# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import Any, ClassVar, Collection, Iterator, cast

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.configlib import Config, ConfigDB
from softfab.configview import SimpleConfigTable
from softfab.datawidgets import DataTable
from softfab.formlib import actionButtons, makeForm
from softfab.joblib import JobDB
from softfab.pageargs import EnumArg, PageArgs, RefererArg, SetArg, StrArg
from softfab.pagelinks import createJobsURL
from softfab.request import Request
from softfab.selectview import TagArgs
from softfab.userlib import UserDB
from softfab.users import User, checkPrivilege
from softfab.utils import pluralize
from softfab.xmlgen import XML, XMLContent, xhtml


class FastConfigTable(SimpleConfigTable):
    # Disable tabs and sorting because links would drop the stored referers.
    tabOffsetField = None
    sortField = None
    showConflictAsError = True
    showTargets = True
    showOwner = False

    def getRecordsToQuery(self, proc: PageProcessor) -> Collection[Config]:
        return cast(FastExecute_GET.Processor, proc).configs

class RefererArgs(PageArgs):
    configQuery = RefererArg('ConfigDetails')
    scheduleQuery = RefererArg('ScheduleDetails')

class PostArgs(RefererArgs):
    confirmedId = SetArg()

Actions = Enum('Actions', 'EXECUTE CANCEL')

class FastExecute_GET(FabPage['FastExecute_GET.Processor',
                              'FastExecute_GET.Arguments']):
    icon = 'IconExec'
    description = 'Execute Configurations'
    linkDescription = False

    class Arguments(TagArgs, RefererArgs):
        configId = StrArg(None)

    class Processor(PageProcessor['FastExecute_GET.Arguments']):

        configDB: ClassVar[ConfigDB]
        userDB: ClassVar[UserDB]

        async def process(self,
                          req: Request['FastExecute_GET.Arguments'],
                          user: User
                          ) -> None:
            configId = req.args.configId
            tagkey = req.args.tagkey
            tagvalue = req.args.tagvalue
            # pylint: disable=attribute-defined-outside-init

            # Tag key and value must be provided both or neither.
            if tagkey is None and tagvalue is not None:
                raise PresentableError(xhtml.p[
                    'Got "tagkey" without "tagvalue".'
                    ])
            if tagkey is not None and tagvalue is None:
                raise PresentableError(xhtml.p[
                    'Got "tagvalue" without "tagkey".'
                    ])

            # Either configId or tag key+value must be provided.
            if configId is None:
                if tagkey is None:
                    raise PresentableError(xhtml.p[
                        'Either "configId" or "tagkey" + "tagvalue" '
                        'is required.'
                        ])
                assert tagvalue is not None
                # Look up tag key+value.
                self.configs = sorted(
                    self.configDB.iterConfigsByTag(tagkey, tagvalue)
                    )
            else:
                if tagkey is not None:
                    raise PresentableError(xhtml.p[
                        'Providing both "configId" and "tagkey" + "tagvalue" '
                        'is not allowed.'
                        ])
                # Look up configId.
                try:
                    self.configs = [ self.configDB[configId] ]
                except KeyError:
                    self.configs = []

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'c/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable[Any]]:
        yield FastConfigTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(FastExecute_GET.Processor, kwargs['proc'])
        configs = proc.configs
        tagged = proc.args.configId is None
        if configs:
            numJobs = sum(len(config.targets) or 1 for config in configs)
            yield xhtml.p[
                'Create ',
                xhtml.b[ str(numJobs), ' ', pluralize('job', numJobs) ],
                ' from the ', pluralize('configuration', len(configs)),
                ' listed below?'
                ]
            yield makeForm(
                args = PostArgs(
                    # Args used by 'cancel':
                    RefererArgs.subset(proc.args),
                    # Args used by 'execute':
                    confirmedId = (config.getId() for config in configs)
                    )
                )[ xhtml.p[ actionButtons(Actions) ] ].present(**kwargs)
            yield FastConfigTable.instance.present(**kwargs)
        elif tagged:
            yield (
                xhtml.p[
                    'No configuration matches'
                    ' tag key ', xhtml.b[ proc.args.tagkey ],
                    ' and value ', xhtml.b[ proc.args.tagvalue ], '.'
                    ],
                self.backToReferer(proc.args)
                )
        else:
            yield (
                xhtml.p[
                    'No configuration named ', xhtml.b[ proc.args.configId ],
                    ' exists.'
                    ],
                self.backToReferer(proc.args)
                )

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        proc = cast(FastExecute_GET.Processor, kwargs['proc'])
        yield message
        yield self.backToReferer(proc.args)

class FastExecute_POST(FabPage['FastExecute_POST.Processor',
                               'FastExecute_POST.Arguments']):
    icon = 'IconExec'
    description = 'Execute Configurations'
    linkDescription = False

    class Arguments(PostArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor['FastExecute_POST.Arguments']):

        configDB: ClassVar[ConfigDB]
        jobDB: ClassVar[JobDB]

        async def process(self,
                          req: Request['FastExecute_POST.Arguments'],
                          user: User
                          ) -> None:
            action = req.args.action

            if action is Actions.CANCEL:
                page = cast('FastExecute_POST', self.page)
                raise Redirect(req.args.refererURL or
                               page.getParentURL(req.args))

            if action is Actions.EXECUTE:
                checkPrivilege(user, 'j/c', 'create jobs')

                # Create jobs.
                jobIds = []
                userName = user.name
                for configId in sorted(req.args.confirmedId):
                    # TODO: Configs that have disappeared or become invalid are
                    #       silently ignored. Since this is a rare situation,
                    #       it is a minor problem, but still bad behaviour.
                    try:
                        config = self.configDB[configId]
                    except KeyError:
                        pass
                    else:
                        if config.hasValidInputs():
                            jobDB = self.jobDB
                            for job in config.createJobs(userName):
                                jobDB.add(job)
                                jobIds.append(job.getId())
                raise Redirect(createJobsURL(jobIds))

            assert False, action

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'c/l')

    def presentContent(self, **kwargs: object) -> XMLContent:
        assert False
