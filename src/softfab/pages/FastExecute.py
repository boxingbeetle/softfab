# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.configlib import configDB, iterConfigsByTag
from softfab.configview import SimpleConfigTable
from softfab.datawidgets import DataTable
from softfab.formlib import actionButtons, makeForm
from softfab.joblib import jobDB
from softfab.pageargs import EnumArg, PageArgs, RefererArg, SetArg, StrArg
from softfab.pagelinks import createJobsURL
from softfab.selectview import TagArgs
from softfab.utils import pluralize
from softfab.xmlgen import XMLContent, xhtml

from enum import Enum
from typing import Iterator

class FastConfigTable(SimpleConfigTable):
    # Disable tabs and sorting because links would drop the stored referers.
    tabOffsetField = None
    sortField = None
    showConflictAsError = True

    def getRecordsToQuery(self, proc):
        return proc.configs

class RefererArgs(PageArgs):
    configQuery = RefererArg('ConfigDetails')
    scheduleQuery = RefererArg('ScheduleDetails')

class PostArgs(RefererArgs):
    confirmedId = SetArg()

Actions = Enum('Actions', 'EXECUTE CANCEL')

class FastExecute_GET(FabPage['FastExecute_GET.Processor', 'FastExecute_GET.Arguments']):
    icon = 'IconExec'
    description = 'Execute Configurations'
    linkDescription = False

    class Arguments(TagArgs, RefererArgs):
        configId = StrArg(None)

    class Processor(PageProcessor):

        def process(self, req):
            configId = req.args.configId
            tagkey = req.args.tagkey
            tagvalue = req.args.tagvalue

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
            if configId is None and tagkey is None:
                raise PresentableError(xhtml.p[
                    'Either "configId" or "tagkey" + "tagvalue" is required.'
                    ])
            if configId is not None and tagkey is not None:
                raise PresentableError(xhtml.p[
                    'Providing both "configId" and "tagkey" + "tagvalue" '
                    'is not allowed.'
                    ])

            # pylint: disable=attribute-defined-outside-init
            if configId is None:
                # Look up tag key+value.
                self.configs = sorted(iterConfigsByTag(tagkey, tagvalue))
            else:
                # Look up configId.
                try:
                    self.configs = [ configDB[configId] ]
                except KeyError:
                    self.configs = []

    def checkAccess(self, req):
        req.checkPrivilege('c/l')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield FastConfigTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
        configs = proc.configs
        tagged = proc.args.configId is None
        if configs:
            numConfigs = len(configs)
            yield xhtml.p[
                'Create ',
                xhtml.b[ str(numConfigs), ' ', pluralize('job', numConfigs) ],
                ' from the ', pluralize('configuration', numConfigs),
                ' listed below?'
                ]
            yield makeForm(
                args = PostArgs(
                    # Args used by 'cancel':
                    RefererArgs.subset(proc.args),
                    # Args used by 'execute':
                    confirmedId = (config.getId() for config in configs)
                    )
                )[ xhtml.p[ actionButtons(Actions) ] ].present(proc=proc)
            yield FastConfigTable.instance.present(proc=proc)
        elif tagged:
            yield (
                xhtml.p[
                    'No configuration matches'
                    ' tag key ', xhtml.b[ proc.args.tagkey ],
                    ' and value ', xhtml.b[ proc.args.tagvalue ], '.'
                    ],
                self.backToReferer(proc.req)
                )
        else:
            yield (
                xhtml.p[
                    'No configuration named ', xhtml.b[ proc.args.configId ],
                    ' exists.'
                    ],
                self.backToReferer(proc.req)
                )

    def presentError(self, proc: Processor, message: str) -> XMLContent:
        yield message
        yield self.backToReferer(proc.req)

class FastExecute_POST(FabPage['FastExecute_POST.Processor', 'FastExecute_POST.Arguments']):
    icon = 'IconExec'
    description = 'Execute Configurations'
    linkDescription = False

    class Arguments(PostArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor):

        def process(self, req):
            action = req.args.action

            if action is Actions.CANCEL:
                raise Redirect(
                    req.args.refererURL or self.page.getParentURL(req)
                    )

            if action is Actions.EXECUTE:
                req.checkPrivilege('j/c', 'create jobs')

                # Create jobs.
                jobIds = []
                user = req.userName
                for configId in sorted(req.args.confirmedId):
                    # TODO: Configs that have disappeared or become invalid are
                    #       silently ignored. Since this is a rare situation,
                    #       it is a minor problem, but still bad behaviour.
                    try:
                        config = configDB[configId]
                    except KeyError:
                        pass
                    else:
                        if config.hasValidInputs():
                            job = config.createJob(user)
                            jobDB.add(job)
                            jobIds.append(job.getId())
                raise Redirect(createJobsURL(jobIds))

            assert False, action

    def checkAccess(self, req):
        req.checkPrivilege('c/l')

    def presentContent(self, proc: Processor) -> XMLContent:
        assert False
