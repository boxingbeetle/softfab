# SPDX-License-Identifier: BSD-3-Clause

from typing import (
    AbstractSet, Dict, Iterable, List, Mapping, Optional, Tuple, cast
)

from softfab.ControlPage import ControlPage
from softfab.Page import PageProcessor
from softfab.joblib import Task, getAllTasksWithId
from softfab.pageargs import DictArg, DictArgInstance, PageArgs, SetArg, StrArg
from softfab.request import Request
from softfab.response import Response
from softfab.taskdeflib import TaskDef, taskDefDB
from softfab.timeview import formatTimeAttr
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import XMLContent, xml

DefRunPair = Tuple[TaskDef, Optional[Task]]

def filterTasks(
        tag: Mapping[str, Iterable[str]],
        owner: Optional[str]
        ) -> Mapping[str, Mapping[str, Iterable[DefRunPair]]]:
    # In "selected", each tag key is mapped to a dictionary which maps the
    # canonical versions of selected tag values to a list of all the task
    # definitions that have that particular tag.
    selected: Dict[str, Dict[str, List[DefRunPair]]] = {}
    for tagKey, tagValues in tag.items():
        selected[tagKey] = {
            TaskDef.cache.toCanonical(tagKey, value)[0]: []
            for value in tagValues
            }

    def createDefRunPair(taskDef: TaskDef) -> DefRunPair:
        taskId = taskDef.getId()
        # Determine latest run of this task.
        taskTimes = (
            ( task.startTime, task )
            for task in getAllTasksWithId(taskId)
            if task.isDone() and (
                not owner or owner == task['owner']
                )
            )
        task: Optional[Task]
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

        async def process(self,
                          req: Request['GetTaggedTaskInfo_GET.Arguments'],
                          user: User
                          ) -> None:
            # pylint: disable=attribute-defined-outside-init
            self.selected = filterTasks(
                cast(DictArgInstance[AbstractSet[str]], req.args.tag),
                req.args.owner
                )

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'td/l', 'list task definitions')
        checkPrivilege(user, 'td/a', 'access task definitions')
        checkPrivilege(user, 't/l', 'list tasks')
        checkPrivilege(user, 't/a', 'access tasks')

    async def writeReply(self, response: Response, proc: Processor) -> None:
        def taskToXML(task: Optional[Task]) -> XMLContent:
            if task is not None:
                run = task.getLatestRun()
                yield xml.run(
                    # pylint: disable=protected-access
                    execstate = run._getState(),
                    result = run.result,
                    alert = run.getAlert(),
                    summary = run.getSummary(),
                    starttime = formatTimeAttr(run.startTime),
                    duration = run.getDuration(),
                    report = run.getURL(),
                    owner = task.getJob().owner,
                    )

        def taggedToXML(
                tagKey: str,
                tagged: Mapping[str, Iterable[DefRunPair]]
                ) -> XMLContent:
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
        response.writeXML(
            xml.info[(
                xml('tag-key')(name = tagKey)[ taggedToXML(tagKey, tagged) ]
                for tagKey, tagged in proc.selected.items()
                )]
            )
