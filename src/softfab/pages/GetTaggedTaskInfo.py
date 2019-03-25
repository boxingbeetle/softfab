# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import PageProcessor
from softfab.joblib import getAllTasksWithId
from softfab.pageargs import DictArg, PageArgs, SetArg, StrArg
from softfab.response import Response
from softfab.taskdeflib import TaskDef, taskDefDB
from softfab.timeview import formatTimeAttr
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml


def filterTasks(tag, owner):
    # In "selected", each tag key is mapped to a dictionary which maps the
    # canonical versions of selected tag values to a list of all the task
    # definitions that have that particular tag.
    selected = {}
    for tagKey, tagValues in tag.items():
        selected[tagKey] = dict(
            ( TaskDef.cache.toCanonical(tagKey, value)[0], [] )
            for value in tagValues
            )

    def createDefRunPair(taskDef):
        taskId = taskDef.getId()
        # Determine latest run of this task.
        taskTimes = (
            ( task['starttime'], task )
            for task in getAllTasksWithId(taskId)
            if task.isDone() and (
                not owner or owner == task['owner']
                )
            )
        try:
            starttime_, task = max(taskTimes)
        except ValueError:
            task = None
        return taskDef, task

    # TODO: This code should be generic enough to move to another module,
    #       such as selectlib or databaselib.
    # TODO: It would be faster to operate on sets than to iterate through
    #       a list and then query for each element.
    #       Maybe not for small numbers, but definitely for large numbers.
    for taskDef in taskDefDB:
        for tagKey, tagged in selected.items():
            if taskDef.hasTagKey(tagKey):
                for tagValue, tasks in tagged.items():
                    if taskDef.hasTagValue(tagKey, tagValue):
                        tasks.append(createDefRunPair(taskDef))

    return selected

class GetTaggedTaskInfo_GET(ControlPage['GetTaggedTaskInfo_GET.Arguments',
                                        'GetTaggedTaskInfo_GET.Processor']):

    class Arguments(PageArgs):
        tag = DictArg(SetArg())
        owner = StrArg(None)

    class Processor(PageProcessor['GetTaggedTaskInfo_GET.Arguments']):

        def process(self, req, user):
            # pylint: disable=attribute-defined-outside-init
            self.selected = filterTasks(req.args.tag, req.args.owner)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'td/l', 'list task definitions')
        checkPrivilege(user, 'td/a', 'access task definitions')
        checkPrivilege(user, 't/l', 'list tasks')
        checkPrivilege(user, 't/a', 'access tasks')

    def writeReply(self, response: Response, proc: Processor) -> None:
        def taskToXML(task):
            if task is not None:
                run = task.getLatestRun()
                yield xml.run(
                    execstate = run['state'],
                    result = run.getResult(),
                    alert = run.getAlert(),
                    summary = run.getSummary(),
                    starttime = formatTimeAttr(run['starttime']),
                    duration = run.getDuration(),
                    report = run.getURL(),
                    owner = run['owner'],
                    )

        def taggedToXML(tagKey, tagged):
            for tagValue, tasks in tagged.items():
                cvalue, dvalue = TaskDef.cache.toCanonical(
                    tagKey, tagValue
                    )
                assert cvalue == tagValue
                yield xml('tag-value')(name = dvalue)[(
                    xml.taskdef(name = taskDef.getId())[
                        xml.title[ taskDef.getTitle() ],
                        xml.description[ taskDef.getDescription() ],
                        taskToXML(task)
                        ]
                    for taskDef, task in tasks
                    )]
        response.write(
            xml.info[(
                xml('tag-key')(name = tagKey)[ taggedToXML(tagKey, tagged) ]
                for tagKey, tagged in proc.selected.items()
                )].flattenIndented()
            )
