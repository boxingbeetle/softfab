# SPDX-License-Identifier: BSD-3-Clause

from abc import abstractmethod
from collections import defaultdict
from functools import total_ordering
from typing import (
    TYPE_CHECKING, AbstractSet, DefaultDict, Dict, FrozenSet, Generic,
    Iterable, Iterator, List, MutableSet, Optional, Sequence, Tuple, TypeVar,
    Union, cast
)

from typing_extensions import Protocol

from softfab.setcalc import UnionFind, categorizedLists, union
from softfab.utils import Heap, ResultKeeper
from softfab.waiting import (
    BoundReason, ReasonForWaiting, checkBoundGroupRunner, checkGroupRunners
)

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from softfab.productdeflib import ProductDef
    from softfab.resourcelib import TaskRunner
    from softfab.taskrunlib import TaskRun
else:
    ProductDef = object
    TaskRunner = object
    TaskRun = object


class TaskProto(Protocol):
    def getName(self) -> str:
        ...
    def getInputs(self) -> AbstractSet[str]:
        ...
    def getOutputs(self) -> AbstractSet[str]:
        ...
    def getRunners(self) -> AbstractSet[str]:
        ...

class ProductProto(Protocol):
    def isLocal(self) -> bool:
        ...
    def setLocalAt(self, runnerId: str) -> None:
        ...

TaskT = TypeVar('TaskT', bound=TaskProto)
TaskElem = Union[TaskT, 'TaskGroup[TaskT]']

class TaskSet(Generic[TaskT]):

    def __init__(self) -> None:
        super().__init__()
        self._tasks: Dict[str, TaskT] = {}

    def isEmpty(self) -> bool:
        return not self._tasks

    def getInputSet(self) -> AbstractSet[str]:
        # TODO: This is equivalent to TaskGroup.getInputs.
        #       Any chances for generalizing?
        inputs: MutableSet[str] = set()
        outputs: MutableSet[str] = set()
        for task in self._tasks.values():
            inputs |= task.getInputs()
            outputs |= task.getOutputs()
        return inputs - outputs

    def _getMainGroup(self) -> 'TaskGroup[TaskT]':
        unionFind: UnionFind[Tuple[str, str]] = UnionFind()
        local: ResultKeeper[str, bool] = ResultKeeper(
            lambda prodName: self.getProductDef(prodName).isLocal()
            )
        for taskName, task in self._tasks.items():
            taskNode = ( 'task', taskName )
            unionFind.add(taskNode)
            for prodName in task.getInputs() | task.getOutputs():
                if local[prodName]:
                    prodNode = ( 'prod', prodName )
                    unionFind.add(prodNode)
                    unionFind.unite(prodNode, taskNode)

        def iterGroupedTasks() -> Iterator[TaskElem]:
            for group in unionFind.iterSets():
                nodesByType = categorizedLists(group)
                tasks = [ self._tasks[name] for name in nodesByType['task'] ]
                productNames = nodesByType['prod']
                if productNames:
                    locations = {
                        self.getProductLocation(prodName)
                        for prodName in productNames
                        }
                    locations.discard(None)
                    assert len(locations) <= 1
                    localAt = locations.pop() if locations else None
                    yield LocalGroup(self, tasks, localAt)
                else:
                    assert len(tasks) == 1
                    yield tasks[0]
        return _MainGroup(self, iterGroupedTasks())

    def getProducers(self, productName: str) -> Iterator[TaskT]:
        '''Returns an iterator which contains all task objects which have
        the given product as an output.
        '''
        for task in self._tasks.values():
            if productName in task.getOutputs():
                yield task

    def getConsumers(self, productName: str) -> Iterator[TaskT]:
        '''Returns an iterator which contains all task objects which have
        the given product as an input.
        '''
        for task in self._tasks.values():
            if productName in task.getInputs():
                yield task

    def getProductDef(self, name: str) -> ProductDef:
        '''Returns the definition of the product with the given name.
        Raises KeyError if there is no product with the given name.
        '''
        raise NotImplementedError

    def getProduct(self, name: str) -> ProductProto:
        raise NotImplementedError

    def getProductLocation(self, name: str) -> Optional[str]:
        '''Returns 'localAt' value for a local product, or None if the local
        product does not have a location yet.
        The "name" argument must be a name of a local product.
        Used in TaskSet._getMainGroup() only.
        '''
        raise NotImplementedError

    def getRunners(self) -> AbstractSet[str]:
        raise NotImplementedError

    def iterTaskNames(self) -> Iterator[str]:
        return iter(self._tasks.keys())

    def getTask(self, name: str) -> Optional[TaskT]:
        return self._tasks.get(name)

    def getTasks(self) -> Iterable[TaskT]:
        return self._tasks.values()

    def getTaskGroupSequence(self) -> Sequence[TaskElem]:
        '''Gets a sequence containing the tasks and subgroups in this task set,
        as much as possible in the order they will be executed.
        This sequence remains the same throughout the life cycle of a job, even
        if the predicted order later turns out to be different from the actual
        order.
        '''
        return self._getMainGroup().getTaskGroupSequence()

    def getTaskSequence(self) -> Sequence[TaskT]:
        '''Gets a sequence containing the tasks in this task set, as much as
        possible in the order they will be executed.
        This sequence remains the same throughout the life cycle of a job, even
        if the predicted order later turns out to be different from the actual
        order.
        '''
        return self._getMainGroup().getTaskSequence()

    def getDescription(self) -> str:
        """Create a user-readable description of what was done in this job.
        """
        descrList = [task.getName() for task in self.getTaskSequence()]
        maxLen = 130
        length = 0
        itemCount = 0
        for item in descrList:
            newLength = length + len(item) + 1
            if newLength > maxLen:
                break
            length = newLength
            itemCount += 1
        if itemCount < len(descrList):
            return ', '.join(descrList[ : itemCount]) + \
                ' ... [' + str(len(descrList) - itemCount) + ' more]'
        else:
            return ', '.join(descrList)

class PriorityABC(Protocol):

    @abstractmethod
    def getName(self) -> str: ...

    @abstractmethod
    def getPriority(self) -> int: ...

# Suppress mypy message about applying total_ordering to an abstract class.
#   https://github.com/python/mypy/issues/8539
@total_ordering # type: ignore[misc]
class PriorityMixin(PriorityABC):
    '''Mixin that orders objects primarily on the integer value returned by
    getPriority() and secondarily on the value returned by getName().
    '''

    @abstractmethod
    def getName(self) -> str: ...

    @abstractmethod
    def getPriority(self) -> int: ...

    def __hash__(self) -> int:
        return hash(self.getName())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PriorityMixin):
            return self.getName() == other.getName()
        else:
            return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, PriorityMixin):
            prioCmp = self.getPriority() - other.getPriority()
            if prioCmp == 0:
                return self.getName() < other.getName()
            else:
                return prioCmp < 0
        else:
            return NotImplemented

class TaskGroup(PriorityMixin, Generic[TaskT]):
    '''Abstract base class for task groups.
    TODO: TaskGroup is only subclassed by MainGroup and LocalGroup. The
          original idea was probably to introduce other subclasses later, but
          this is based on the assumption that these other subclasses will be
          either fully disjoint with local groups, or fully joint. In other
          words, it is a hierarchical approach which will only work if other
          group types are either never local, or always subgroups/supergroups
          of local groups.
          We have plans for composite tasks, which is a kind of task grouping,
          but which is independent of locality. For example, not all subtasks
          of a composite task have to be bound to the same Task Runner; also
          it is possible for some subtasks to share a bound Task Runner with
          tasks outside the composite.
          Another shortcoming of the current design is that it assumes each
          task has only one choice of storage pool for its input and outputs.
          This is currently true, as the only storage pool we support is an
          implicit one for each Task Runner (typically used to model the
          Factory PC's local hard disk). If we allow each Task Runner to be
          associated with multiple storage pools, a single task can be a member
          of multiple local groups, for example by consuming two local products,
          each of which comes from a different storage pool.
          All this means the current inheritance-based design is not future
          proof. It is not clear to me yet what the replacement design would
          look like, but it is clear that the hierarchical approach should be
          dropped.
    '''

    def __init__(self, parent: TaskSet[TaskT], tasks: Iterable[TaskElem]):
        super().__init__()
        self._parent = parent
        self.__tasks = {task.getName(): task for task in tasks}
        self.__inputs: Optional[FrozenSet[str]] = None
        self.__outputs: Optional[FrozenSet[str]] = None
        self.__priority: Optional[int] = None
        self.__taskGroupSequence: Optional[Sequence[TaskElem]] = None
        self.__taskSequence: Optional[Sequence[TaskT]] = None
        self.__neededCaps: Optional[AbstractSet[str]] = None

    def __computeSequences(self) -> None:
        # Precalculate which tasks produce which products.
        # Note: The tasks from _parent are flattened (no TaskGroups).
        remainingProducers: DefaultDict[str, MutableSet[str]] = \
                defaultdict(set)
        for parentTask in self._parent.getTasks():
            for productName in parentTask.getOutputs():
                remainingProducers[productName].add(parentTask.getName())

        tasksLeft: Dict[str, TaskElem] = dict(self.__tasks)
        availableProducts = set(self.getInputs())
        readyTasks = cast(Heap[TaskElem], Heap())
        mainSequence = []
        flatSequence: List[TaskT] = []
        flattened = False
        while True:
            while True:
                # Note: taskLeft is modified inside the loop, so it is
                #       essential to make a copy.
                for name, task in list(tasksLeft.items()):
                    if task.getInputs() <= availableProducts:
                        readyTasks.add(tasksLeft.pop(name))
                for task in readyTasks.iterPop():
                    if not flattened:
                        mainSequence.append(task)
                    if isinstance(task, TaskGroup):
                        flatTasks = task.getTaskSequence()
                    else:
                        flatTasks = (task,)
                    flatSequence.extend(flatTasks)
                    newProducts = task.getOutputs()
                    if newProducts:
                        for name in newProducts:
                            productDef = self._parent.getProductDef(name)
                            if productDef.isCombined():
                                producers = remainingProducers[name]
                                for subTask in flatTasks:
                                    producers.discard(subTask.getName())
                                available = not producers
                            else:
                                available = True
                            if available:
                                availableProducts.add(name)
                        break
                else:
                    # Heap is empty and no new products available.
                    break
            if not tasksLeft:
                break
            unreachableTasks = sorted(tasksLeft.values())
            if not flattened:
                mainSequence.extend(unreachableTasks)
                flattened = True
            innerTasks: Dict[str, TaskT] = {}
            for unreachable in unreachableTasks:
                if isinstance(unreachable, TaskGroup):
                    for inner in unreachable.getTaskSequence():
                        innerTasks[inner.getName()] = inner
                else:
                    innerTasks[unreachable.getName()] = unreachable
            if len(innerTasks) > len(tasksLeft):
                # At least one of the unreachable tasks is a task group.
                tasksLeft = cast(Dict[str, TaskElem], innerTasks)
            else:
                # All unreachable tasks are singular tasks, since our task
                # groups always contain 2 or more tasks.
                flatSequence.extend(cast(Sequence[TaskT], unreachableTasks))
                break

        self.__taskGroupSequence = tuple(mainSequence)
        self.__taskSequence = tuple(flatSequence)

    def getName(self) -> str:
        raise NotImplementedError

    def getChild(self, name: str) -> TaskElem:
        return self.__tasks[name]

    def getChildren(self) -> Iterable[TaskElem]:
        return iter(self.__tasks.values())

    def getPriority(self) -> int:
        if self.__priority is None:
            self.__priority = min(
                task.getPriority()
                for task in self.__tasks.values()
                )
        return self.__priority

    def getTaskGroupSequence(self) -> Sequence[TaskElem]:
        if self.__taskGroupSequence is None:
            self.__computeSequences()
            assert self.__taskGroupSequence is not None
        return self.__taskGroupSequence

    def getTaskSequence(self) -> Sequence[TaskT]:
        if self.__taskSequence is None:
            self.__computeSequences()
            assert self.__taskSequence is not None
        return self.__taskSequence

    def getInputs(self) -> AbstractSet[str]:
        if self.__inputs is None:
            inputs = union(
                task.getInputs() for task in self.__tasks.values()
                ) - self.getOutputs()
            self.__inputs = frozenset(inputs)
        return self.__inputs

    def getOutputs(self) -> AbstractSet[str]:
        if self.__outputs is None:
            outputs = union(
                task.getOutputs() for task in self.__tasks.values()
                )
            self.__outputs = frozenset(outputs)
        return self.__outputs

    def getNeededCaps(self) -> AbstractSet[str]:
        if self.__neededCaps is None:
            neededCaps = union(
                task.getNeededCaps() for task in self.__tasks.values()
                )
            self.__neededCaps = frozenset(neededCaps)
        return self.__neededCaps

    def assign(self, taskRunner: TaskRunner) -> Optional[TaskRun]:
        '''Tries to assign this task (group).
        Returns the assigned task, or None if no assignment was possible.
        '''
        raise NotImplementedError

    def checkRunners(self,
                     taskRunners: Sequence[TaskRunner],
                     whyNot: List[ReasonForWaiting]
                     ) -> None:
        """Checks whether this task (group) can be assigned to one of the given
        Task Runners. No actual assignment will occur.
        Reasons blocking the assignment will be appended to `whyNot`.
        """
        raise NotImplementedError

class _MainGroup(TaskGroup[TaskT]):
    '''The main group: all tasks in a job.
    '''

    def getName(self) -> str:
        return '/'

    def assign(self, taskRunner: TaskRunner) -> Optional[TaskRun]:
        for task in self.getTaskGroupSequence():
            assigned = task.assign(taskRunner)
            if assigned is not None:
                return assigned
        return None

    def checkRunners(self,
                     taskRunners: Sequence[TaskRunner],
                     whyNot: List[ReasonForWaiting]
                     ) -> None:
        mark = len(whyNot)
        for task in self.getTaskGroupSequence():
            task.checkRunners(taskRunners, whyNot)
            del whyNot[mark:]

class LocalGroup(TaskGroup[TaskT]):
    '''A group of tasks bound to the same Task Runner by their use of local
    products.
    '''

    def __init__(self,
                 parent: TaskSet[TaskT],
                 tasks: Iterable[TaskT],
                 localAt: Optional[str]
                 ):
        super().__init__(parent, tasks)
        self.__name: Optional[str] = None
        self.__runnerId: Optional[str] = None
        self.__runners: Optional[AbstractSet[str]] = None
        if localAt is not None:
            self.__setRunnerId(localAt)

    def __setRunnerId(self, runnerId: str) -> None:
        if self.__runnerId is None:
            # Bind this task group to the given Task Runner.
            self.__runnerId = runnerId
            for productName in self.getOutputs():
                product = self._parent.getProduct(productName)
                if product.isLocal():
                    product.setLocalAt(runnerId)
        elif self.__runnerId != runnerId:
            # TODO: make it impossible to enter conflicting parameters
            # and then replace this with a simple assertion
            raise ValueError(
                f'Conflicting local inputs in group "{self.getName()}": '
                f'"{self.__runnerId}" and "{runnerId}"'
                )

    def getName(self) -> str:
        if self.__name is None:
            # Name the task group after the alphabetically first task inside
            # it. Since each task has a unique name and belongs to at most one
            # task group, this creates a unique name for the task group.
            # The "/" at the end gives the task group a name that is different
            # from the task itself. It is placed at the end to make sure local
            # groups containing only one task are sorted in the same way as
            # single tasks.
            self.__name = min(
                task.getName()
                for task in self.getChildren()
                ) + '/'
        return self.__name

    def getRunnerId(self) -> Optional[str]:
        return self.__runnerId

    def canRunOn(self, runner: str) -> bool:
        allowed = self.__runners
        if allowed is None:
            jobRunners = self._parent.getRunners()
            for task in self.getChildren():
                runners = cast(TaskT, task).getRunners() or jobRunners
                if runners:
                    if allowed is None:
                        allowed = set(runners)
                    else:
                        allowed &= runners
            if allowed is None:
                allowed = set()
            self.__runners = allowed
        if allowed:
            return runner in allowed
        else:
            # No restrictions.
            return True

    def assign(self, taskRunner: TaskRunner) -> Optional[TaskRun]:
        boundRunnerId = self.__runnerId
        if boundRunnerId is None or boundRunnerId == taskRunner.getId():
            if self.getNeededCaps() <= taskRunner.capabilities:
                for task in self.getTaskGroupSequence():
                    assigned = task.assign(taskRunner)
                    if assigned is not None:
                        self.__setRunnerId(taskRunner.getId())
                        return assigned
        return None

    def checkRunners(self,
                     taskRunners: Sequence[TaskRunner],
                     whyNot: List[ReasonForWaiting]
                     ) -> None:
        boundRunnerId = self.__runnerId
        if boundRunnerId is None:
            candidates = taskRunners
            # Limit the candidates to those TRs with sufficient capabilities
            # to run all tasks in this group.
            candidates = checkGroupRunners(
                candidates, self.getNeededCaps(), whyNot
                )
        else:
            # Is the bound Task Runner in the list?
            for runner in taskRunners:
                if runner.getId() == boundRunnerId:
                    # Check whether this single candidate is suitable.
                    candidates = checkBoundGroupRunner(
                        runner, self.getNeededCaps(), whyNot
                        )
                    break
            else:
                candidates = []
                whyNot.append(BoundReason(boundRunnerId))

        # Try to assign all individual tasks.
        # This call is only made for its side effect:
        # to update TaskRun.__whyNot.
        mark = len(whyNot)
        for task in self.getChildren():
            task.checkRunners(candidates, whyNot)
            del whyNot[mark:]
