# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from functools import total_ordering
from pathlib import Path
from typing import (
    TYPE_CHECKING, AbstractSet, DefaultDict, Dict, Iterable, Iterator, List,
    Mapping, MutableSet, Optional, Sequence, Tuple, Union, cast
)

from typing_extensions import Protocol

from softfab.databaselib import DBRecord, Database, RecordObserver
from softfab.frameworklib import Framework, FrameworkDB
from softfab.joblib import Job, JobFactory
from softfab.productdeflib import ProductDef, ProductDefDB, ProductType
from softfab.restypelib import ResTypeDB
from softfab.selectlib import SelectableRecordABC, TagCache
from softfab.taskdeflib import TaskDefDB
from softfab.taskgroup import (
    LocalGroup, PriorityMixin, TaskGroup, TaskSet, TaskT
)
from softfab.tasklib import ResourceRequirementsMixin, TaskRunnerSet
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLAttributeValue, XMLContent, xml

if TYPE_CHECKING:
    from softfab.resourcelib import ResourceDB
    from softfab.taskdeflib import TaskDef
else:
    ResourceDB = object
    TaskDef = object


class _ObserverProxy(RecordObserver[DBRecord]):

    def __init__(self, subjectDb: Database[DBRecord]):
        super().__init__()
        # Mapping from configId to set of keys observed by that config.
        self.__subjects: DefaultDict[str, MutableSet[str]] = \
            defaultdict(set)
        # Mapping from key to dictionary of configs that observe that key.
        self.__observers: DefaultDict[str, Dict[str, Config]] = \
            defaultdict(dict)
        # Listen to all modifications on the given database.
        subjectDb.addObserver(self)

    def addObserver(self, key: str, cfg: 'Config') -> None:
        configId = cfg.getId()
        self.__subjects[configId].add(key)
        self.__observers[key][configId] = cfg

    def delObserver(self, key: str, cfg: 'Config') -> None:
        configId = cfg.getId()
        self.__subjects[configId].remove(key)
        del self.__observers[key][configId]

    def delAllObservers(self, cfg: 'Config') -> None:
        configId = cfg.getId()
        keys = self.__subjects.get(configId)
        if keys is None:
            # Note: For a config which contains no products, the key set is
            #       empty, which means addObserver was not called, so the
            #       configId is not known to us.
            return
        # The key set will be changed by delObserver, so copy it into a list.
        for key in list(keys):
            self.delObserver(key, cfg)
        assert len(self.__subjects[configId]) == 0
        del self.__subjects[configId]

    def added(self, record: DBRecord) -> None:
        pass

    def removed(self, record: DBRecord) -> None:
        self.updated(record)

    def updated(self, record: DBRecord) -> None:
        configs = self.__observers.get(record.getId())
        if configs is not None:
            for cfg in list(configs.values()):
                cfg._invalidate() # pylint: disable=protected-access

class _DescriptionCache:
    """This doesn't cache the description itself: instead, it informs
    each registered Config when to invalidate its cached description.
    """

    def __init__(self, configFactory: 'ConfigFactory'):
        self.__pdObserver = _ObserverProxy(configFactory.productDefDB)
        self.__fdObserver = _ObserverProxy(configFactory.frameworkDB)
        self.__tdObserver = _ObserverProxy(configFactory.taskDefDB)

    def register(self, config: 'Config') -> None:
        frameworks = {}
        for task in config.getTasks():
            self.__tdObserver.addObserver(task.getName(), config)
            framework = task.getDef().getFramework()
            frameworks[framework.getId()] = framework
        products: MutableSet[str] = set()
        for frameworkId, framework in frameworks.items():
            self.__fdObserver.addObserver(frameworkId, config)
            products |= framework.getInputs() | framework.getOutputs()
        for product in products:
            self.__pdObserver.addObserver(product, config)

    def unregister(self, config: 'Config') -> None:
        self.__tdObserver.delAllObservers(config)
        self.__fdObserver.delAllObservers(config)
        self.__pdObserver.delAllObservers(config)

class ProductDefLookup(Protocol):
    """Function that looks up a product definition."""

    def __call__(self, key: str) -> Optional[ProductDef]: ...

class _Param(XMLTag):
    tagName = 'param'

class Task(XMLTag, TaskRunnerSet, PriorityMixin, ResourceRequirementsMixin):
    tagName = 'task'
    intProperties = ('priority', )

    @staticmethod
    def create(name: str,
               priority: int,
               taskDef: TaskDef,
               parameters: Mapping[str, str]
               ) -> 'Task':
        properties: Dict[str, XMLAttributeValue] = dict(
            name = name,
            priority = priority,
            )

        task = Task(properties, taskDef)
        # pylint: disable=protected-access
        for paramName, value in parameters.items():
            task._addParam(dict(name = paramName, value = value))
        return task

    def __init__(self,
                 attributes: Mapping[str, XMLAttributeValue],
                 taskDef: TaskDef
                 ):
        super().__init__(attributes)
        self._properties.setdefault('priority', 0)
        self.__taskDef = taskDef
        self.__params: Dict[str, _Param] = {}

    def _addParam(self, attributes: Mapping[str, str]) -> None:
        param = _Param(attributes)
        self.__params[cast(str, param['name'])] = param

    def getName(self) -> str:
        return cast(str, self._properties['name'])

    def getDef(self) -> TaskDef:
        return self.__taskDef

    def getFramework(self) -> Framework:
        return self.getDef().getFramework()

    def getPriority(self) -> int:
        return cast(int, self._properties['priority'])

    def getParameter(self, name: str) -> Optional[str]:
        param = self.__params.get(name)
        return None if param is None else cast(str, param.get('value'))

    def getParameters(self) -> Dict[str, str]:
        '''Returns a new dictionary containing the parameters of this task.
        '''
        return {
            name: cast(str, param.get('value'))
            for name, param in self.__params.items()
            }

    def getVisibleParameters(self) -> Dict[str, str]:
        '''Returns a new dictionary of parameters to be shown to the user:
        final and reserved parameters are not included.
        '''
        taskDef = self.getDef()
        parameters = taskDef.getParameters()
        parameters.update(self.getParameters())
        return {
            key: value
            for key, value in parameters.items()
            if not key.startswith('sf.') and not taskDef.isFinal(key)
            }

    def getInputs(self) -> AbstractSet[str]:
        return self.getFramework().getInputs()

    def getOutputs(self) -> AbstractSet[str]:
        return self.getFramework().getOutputs()

    def _getContent(self) -> XMLContent:
        yield from self.__params.values()
        yield self.runnersAsXML()

@total_ordering
class Input(XMLTag):
    '''
    TODO: Refactor this code: this class should offer the same interface
          as the productlib.Product class, but there is no mechanism that
          guarantees that.
    TODO: isLocal() and getType() return "safe" values when the product
          definition no longer exists; this works well in practice, but it
          would be cleaner if these methods could not be called at all if
          the product definition has been deleted.
    '''

    tagName = 'input'

    def __init__(self,
                 attributes: Mapping[str, XMLAttributeValue],
                 productDefLookup: ProductDefLookup
                 ):
        super().__init__(attributes)
        self.__productDefLookup = productDefLookup

    def __hash__(self) -> int:
        return hash(self.getName())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Input):
            return self.getName() == other.getName()
        else:
            return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Input):
            return self.getName() < other.getName()
        else:
            return NotImplemented

    def getName(self) -> str:
        return cast(str, self._properties['name'])

    def isLocal(self) -> bool:
        productDef = self.__productDefLookup(self.getName())
        return False if productDef is None else productDef.isLocal()

    def getType(self) -> ProductType:
        productDef = self.__productDefLookup(self.getName())
        return ProductType.TOKEN if productDef is None else productDef.getType()

    def getLocator(self) -> Optional[str]:
        return cast(str, self._properties.get('locator'))

    def setLocator(self, locator: str, localAt: Optional[str] = None) -> None:
        self._properties['locator'] = locator
        if localAt is not None:
            self._properties['localAt'] = localAt
        elif 'localAt' in self._properties:
            del self._properties['localAt']

    def storeLocator(self, locator: str, taskName: str) -> None: # pylint: disable=unused-argument
        self._properties['locator'] = locator

    def getLocalAt(self) -> Optional[str]:
        return cast(Optional[str], self._properties.get('localAt'))

    def setLocalAt(self, runnerId: str) -> None:
        assert runnerId is not None
        self._properties['localAt'] = runnerId

    def clone(self) -> 'Input':
        return Input(self._properties, self.__productDefLookup)

class Output:
    '''Dummy class for output products.
    In a configuration we do not care about outputs, but it is possible their
    locality will be initialised if they belong to the same local group as
    one of the inputs.
    '''

    def __init__(self, productDef: ProductDef):
        super().__init__()
        self.__productDef = productDef

    def isLocal(self) -> bool:
        return self.__productDef.isLocal()

    def setLocalAt(self, runnerId: str) -> None:
        assert runnerId is not None

class TaskSetWithInputs(TaskSet[TaskT]):

    _productDefLookup: ProductDefLookup

    def __init__(self) -> None:
        super().__init__()
        self._inputs: Dict[str, Input] = {}

    # Mark class as abstract:
    def getRunners(self) -> AbstractSet[str]:
        raise NotImplementedError

    def getInput(self, name: str) -> Optional[Input]:
        return self._inputs.get(name)

    def getInputs(self) -> Iterable[Input]:
        return self._inputs.values()

    def getProductDef(self, name: str) -> ProductDef:
        # Get the latest version. This must always exist, since deletion of
        # in-use product definitions is blocked.
        productDef = self._productDefLookup(name)
        assert productDef is not None, name
        return productDef

    def getProductLocation(self, name: str) -> Optional[str]:
        product = self.getInput(name)
        return None if product is None else product.getLocalAt()

    def getInputsGrouped(
            self
            ) -> List[Tuple[Optional[LocalGroup[TaskT]], List[Input]]]:
        '''Returns inputs grouped by "locality". The return value is a list
        of 2-element tuples, which contain local group or None as the first
        element and list of Product objects as the second one. Each inner list
        contains products that are local at the same Task Runner location. For
        global products the inner list contains a single element and the local
        group is None.
        '''
        grouped = []
        ungrouped = set()
        inputSet = self.getInputSet()
        for task in self._getMainGroup().getChildren(): \
                # type: Union[TaskGroup[TaskT], TaskT]
            if isinstance(task, TaskGroup):
                group: Optional[MutableSet[Input]] = set()
            else:
                group = None
            for inpName in task.getInputs():
                if inpName in inputSet:
                    inpObj = self._inputs.get(inpName)
                    if inpObj is None:
                        inpObj = Input({'name': inpName},
                                       self._productDefLookup)
                    if group is not None and inpObj.isLocal():
                        group.add(inpObj)
                    else:
                        ungrouped.add(inpObj)
            if group:
                assert isinstance(task, LocalGroup)
                grouped.append(( task, sorted(group) ))
        return cast(
            List[Tuple[Optional[LocalGroup[TaskT]], List[Input]]],
            [ ( None, [ item ] ) for item in sorted(ungrouped) ]
            ) + sorted(grouped)

    def hasLocalInputs(self) -> bool:
        return any(inp.isLocal() for inp in self._inputs.values())

class Config(XMLTag, TaskRunnerSet, TaskSetWithInputs[Task],
             SelectableRecordABC):
    tagName = 'config'
    boolProperties = ('trselect',)

    def __init__(self,
                 attributes: Mapping[str, XMLAttributeValue],
                 jobFactory: JobFactory,
                 descriptionCache: _DescriptionCache,
                 productDefLookup: ProductDefLookup
                 ):
        # Note: if the "comment" tag is empty, the XML parser does not call the
        #       <text> handler, so we have to use '' rather than None here.
        super().__init__(attributes)
        self.__descriptionCache = descriptionCache
        self._productDefLookup = productDefLookup
        self.__jobFactory = jobFactory
        self._targets: MutableSet[str] = set()
        self._comment = ''
        self._params: Dict[str, str] = {}
        self.__description: Optional[str] = None

    def _updateInputs(self) -> None:
        '''This should be called after tasks are added, to recompute which
        inputs this configuration has.
        '''
        self._inputs = {
            item: self._inputs.get(item, Input({'name': item},
                                               self._productDefLookup))
            for item in self.getInputSet()
            }

    def getId(self) -> str:
        return cast(str, self._properties['name'])

    @property
    def targets(self) -> AbstractSet[str]:
        """Targets for which jobs should be created.

        This can include old targets that were active when this configuration
        was created but are no longer active.
        """
        return self._targets

    @property
    def owner(self) -> Optional[str]:
        """The owner of this configuration, or None if it does not have
        an owner.
        """
        return cast(Optional[str], self._properties.get('owner'))

    @property
    def comment(self) -> str:
        """Gets user-specified comment string for this job configuration.
        Comment string may contain newlines.
        """
        return self._comment

    def __getitem__(self, key: str) -> object:
        if key == 'owner':
            return self.owner
        elif key == 'comment':
            return self._comment
        elif key == 'description':
            return self.getDescription()
        elif key == 'nrtasks':
            return len(self._tasks)
        elif key == 'targets':
            return sorted(self._targets)
        else:
            return XMLTag.__getitem__(self, key)

    def _addTarget(self, attributes: Mapping[str, str]) -> None:
        self._targets.add(attributes['name'])

    def _addTask(self, attributes: Mapping[str, str]) -> Task:
        name = attributes['name']
        taskDef = self.__jobFactory.taskDefDB[name]
        task = Task(attributes, taskDef)
        self._tasks[name] = task
        return task

    def _addInput(self, attributes: Mapping[str, str]) -> None:
        inp = Input(attributes, self._productDefLookup)
        self._inputs[inp.getName()] = inp

    def _addParam(self, attributes: Mapping[str, str]) -> None:
        self._params[attributes['name']] = attributes['value']

    def _textComment(self, text: str) -> None:
        self._comment = text

    def getProduct(self, name: str) -> Union[Input, Output]:
        inp = self._inputs.get(name)
        if inp is None:
            productDef = self._productDefLookup(name)
            assert productDef is not None, name
            return Output(productDef)
        else:
            return inp

    # So far used for testing only
    def getParams(self) -> Dict[str, str]:
        return dict(self._params)

    def getParameter(self, name: str) -> Optional[str]:
        return self._params.get(name)

    def isConsistent(self, resTypeDB: ResTypeDB) -> bool:
        """Returns True iff this configuration can be instantiated.
        It is possible for a configuration to be consistent when it is
        created but become inconsistent due to definitions changing,
        for example due to conflicting resource requirements.
        """
        refToType: Dict[str, str] = {}
        for task in self._tasks.values():
            for spec in task.resourceClaim:
                typeName = spec.typeName
                if not typeName.startswith('sf.'):
                    if resTypeDB[typeName].jobExclusive:
                        ref = spec.reference
                        if refToType.setdefault(ref, typeName) != typeName:
                            return False
        return True

    def iterInputConflicts(self) -> Iterator[str]:
        for inputName in self.getInputSet():
            pd = self.getProductDef(inputName)
            inp = self._inputs.get(inputName)
            if pd['type'] != ProductType.TOKEN and inp is None:
                yield f'missing locator for input "{inputName}"'
            if pd.isLocal() and (inp is None or inp.get('localAt') is None):
                yield f'missing \'local at\' for input "{inputName}"'

    def hasValidInputs(self) -> bool:
        """Returns True iff this configuration can be instantiated without
        overriding inputs.
        """
        return not any(self.iterInputConflicts())

    def createJobs( # pylint: disable=dangerous-default-value
            # We only read the default dictionaries.
            self,
            owner: Optional[str],
            comment: Optional[str] = None,
            locators: Mapping[str, str] = {},
            params: Mapping[str, str] = {},
            localAt: Mapping[str, str] = {},
            taskParameters: Mapping[str, Mapping[str, str]] = {}
            ) -> Iterator[Job]:
        if owner is None:
            owner = self.owner
        if comment is None:
            comment = self._comment
        jobParams = dict(self._params)
        jobParams.update(params)

        jobFactory = self.__jobFactory

        for target in cast(Sequence[Optional[str]],
                           sorted(self.targets)) or [None]:
            job = jobFactory.newJob(
                # configId is empty string when executing from scratch
                configId = self.getId() or None,
                target = target,
                owner = owner,
                comment = comment,
                jobParams = jobParams,
                runners = self._runners
                )

            for task in self.getTaskSequence():
                taskParams = taskParameters.get(task.getName(), {})
                newTask = job._newTask( # pylint: disable=protected-access
                        task.getName(), task.getPriority(), task.getRunners())
                for key, defValue in task.getDef().getParameters().items():
                    value = taskParams.get(key)
                    if value is None:
                        value = task.getParameter(key)
                    if value is None:
                        value = defValue
                    newTask.addParameter(key, value)

            for index, item in enumerate(self.getInputSet()):
                inp = self._inputs.get(item)
                job.setInputLocator(
                    item,
                    locators.get(item, inp and inp.getLocator() or ''),
                    localAt.get(item) or (
                        None if inp is None else inp.getLocalAt()
                        ),
                    f'SF_USER_INPUT_{index:d}'
                    )

            yield job

    def _getContent(self) -> XMLContent:
        for target in self._targets:
            yield xml.target(name=target)
        if self._comment:
            yield xml.comment[ self._comment ]
        yield from self._tasks.values()
        yield from self._inputs.values()
        for name, value in self._params.items():
            yield xml.param(name = name, value = value)
        yield self.runnersAsXML()
        yield self.tags.toXML()

    def getDescription(self) -> str:
        if self.__description is None:
            self.__description = super().getDescription()
            self.__descriptionCache.register(self)
        return self.__description

    def _invalidate(self) -> None:
        self.__descriptionCache.unregister(self)
        self.__description = None

    def _unload(self) -> None:
        self.__descriptionCache.unregister(self)

class ConfigFactory:

    jobFactory: JobFactory
    frameworkDB: FrameworkDB
    taskDefDB: TaskDefDB
    productDefDB: ProductDefDB

    __descriptionCache: Optional[_DescriptionCache] = None

    @property
    def descriptionCache(self) -> _DescriptionCache:
        if self.__descriptionCache is None:
            self.__descriptionCache = _DescriptionCache(self)
        return self.__descriptionCache

    def createConfig(self, attributes: Mapping[str, str]) -> Config:
        return Config(attributes, self.jobFactory, self.descriptionCache,
                      self.productDefDB.get)

    def newConfig(self,
                  name: str,
                  targets: Iterable[str],
                  owner: Optional[str],
                  trselect: bool,
                  comment: str,
                  jobParams: Mapping[str, str],
                  tasks: Iterable[Task],
                  runners: Iterable[str]
                  ) -> Config:
        properties = dict(
            name = name,
            owner = owner,
            trselect = trselect,
            )

        config = Config(properties, self.jobFactory, self.descriptionCache,
                        self.productDefDB.get)
        # pylint: disable=protected-access
        config._targets = set(targets)
        config._comment = comment
        config._params = dict(jobParams)
        config._setRunners(runners)
        for task in tasks:
            config._tasks[task.getName()] = task
        config._updateInputs()
        return config

class ConfigDB(Database[Config]):
    privilegeObject = 'c'
    description = 'configuration'
    uniqueKeys = ( 'name', )

    factory: ConfigFactory
    tagCache: TagCache

    def __init__(self, baseDir: Path):
        super().__init__(baseDir, ConfigFactory())

    def iterConfigsByTag(self, key: str, value: str) -> Iterator[Config]:
        for config in self:
            if config.tags.hasTagValue(key, value):
                yield config
