# SPDX-License-Identifier: BSD-3-Clause

from config import dbDir
from databaselib import Database, DatabaseElem, RecordObserver
from frameworklib import frameworkDB
from joblib import Job
from productdeflib import ProductType, productDefDB
from projectlib import project
from restypelib import resTypeDB
from selectlib import Selectable, ObservingTagCache
from taskdeflib import taskDefDB
from taskgroup import PriorityMixin, TaskSet
from tasklib import ResourceRequirementsMixin, TaskRunnerSet
from xmlbind import XMLTag
from xmlgen import xml

from collections import defaultdict
from functools import total_ordering

class _ObserverProxy(RecordObserver):

    def __init__(self, subjectDb):
        RecordObserver.__init__(self)
        # Mapping from configId to set of keys observed by that config.
        self.__subjects = defaultdict(set)
        # Mapping from key to dictionary of configs that observe that key.
        self.__observers = defaultdict(dict)
        # Listen to all modifications on the given database.
        subjectDb.addObserver(self)

    def addObserver(self, key, cfg):
        configId = cfg.getId()
        self.__subjects[configId].add(key)
        self.__observers[key][configId] = cfg

    def delObserver(self, key, cfg):
        configId = cfg.getId()
        self.__subjects[configId].remove(key)
        del self.__observers[key][configId]

    def delAllObservers(self, cfg):
        configId = cfg.getId()
        keys = self.__subjects.get(configId)
        if keys is None:
            # Note: For a config which contains no products, the key set is
            #       empty, which means addObserver was not called, so the
            #       configId is not known to us (bug 225).
            return
        # The key set will be changed by delObserver, so copy it into a list.
        for key in list(keys):
            self.delObserver(key, cfg)
        assert len(self.__subjects[configId]) == 0
        del self.__subjects[configId]

    def added(self, record):
        pass

    def removed(self, record):
        self.updated(record)

    def updated(self, record):
        configs = self.__observers.get(record.getId())
        if configs is not None:
            for cfg in list(configs.values()):
                cfg._invalidate() # pylint: disable=protected-access

_pdObserver = _ObserverProxy(productDefDB)
_fdObserver = _ObserverProxy(frameworkDB)
_tdObserver = _ObserverProxy(taskDefDB)

class _ConfigFactory:
    @staticmethod
    def createConfig(attributes):
        return Config(attributes)

class _ConfigDB(Database):
    baseDir = dbDir + '/configs'
    factory = _ConfigFactory()
    privilegeObject = 'c'
    description = 'configuration'
    uniqueKeys = ( 'name', )
configDB = _ConfigDB()

class _Param(XMLTag):
    tagName = 'param'

class Task(PriorityMixin, ResourceRequirementsMixin, XMLTag, TaskRunnerSet):
    tagName = 'task'
    intProperties = ('priority', )

    @staticmethod
    def create(name, priority, parameters):
        properties = dict(
            name = name,
            priority = priority,
            )

        task = Task(properties)
        # pylint: disable=protected-access
        for paramName, value in parameters.items():
            task._addParam(dict(name = paramName, value = value))
        return task

    def __init__(self, attributes):
        XMLTag.__init__(self, attributes)
        TaskRunnerSet.__init__(self)
        self._properties.setdefault('priority', 0)
        self.__params = {}

    def _addParam(self, attributes):
        param = _Param(attributes)
        self.__params[param['name']] = param

    def isGroup(self):
        return False

    def getName(self):
        return self._properties['name']

    def getDef(self):
        return taskDefDB[self._properties['name']]

    def getFramework(self):
        return self.getDef().getFramework()

    def getPriority(self):
        return self._properties['priority']

    def getParameter(self, name):
        param = self.__params.get(name)
        return None if param is None else param.get('value')

    def getParameters(self):
        '''Returns a new dictionary containing the parameters of this task.
        '''
        return dict(
            ( name, param.get('value') )
            for name, param in self.__params.items()
            )

    def getVisibleParameters(self):
        '''Returns a new dictionary of parameters to be shown to the user:
        final and reserved parameters are not included.
        '''
        taskDef = self.getDef()
        parameters = taskDef.getParameters()
        parameters.update(self.getParameters())
        return dict(
            ( key, value )
            for key, value in parameters.items()
            if not key.startswith('sf.') and not taskDef.isFinal(key)
            )

    def getInputs(self):
        return self.getFramework().getInputs()

    def getOutputs(self):
        return self.getFramework().getOutputs()

    def _getContent(self):
        yield from self.__params.values()
        yield self.runnersAsXML()

@total_ordering
class _Input(XMLTag):
    '''
    TODO: Refactor this code, see bug 261 for details.
          The root of the problem is that this class should offer the same
          interface as the productlib.Product class, but there is no mechanism
          that guarantees that.
    TODO: isLocal() and getType() return "safe" values when the product
          definition no longer exists; this works well in practice, but it
          would be cleaner if these methods could not be called at all if
          the product definition has been deleted.
    '''

    tagName = 'input'

    def __hash__(self):
        return hash(self._properties['name'])

    def __eq__(self, other):
        if isinstance(other, _Input):
            return self._properties['name'] == other['name']
        else:
            return NotImplemented

    def __lt__(self, other):
        if isinstance(other, _Input):
            return self._properties['name'] < other['name']
        else:
            return NotImplemented

    def isLocal(self):
        productDef = productDefDB.get(self._properties['name'])
        return False if productDef is None else productDef.isLocal()

    def getType(self):
        productDef = productDefDB.get(self._properties['name'])
        return ProductType.TOKEN if productDef is None else productDef['type']

    def setLocator(self, locator, localAt = None):
        self._properties['locator'] = locator
        if localAt is not None:
            self._properties['localAt'] = localAt
        elif 'localAt' in self._properties:
            del self._properties['localAt']

    def storeLocator(self, locator, taskName): # pylint: disable=unused-argument
        self._properties['locator'] = locator

    def getLocalAt(self):
        return self._properties.get('localAt')

    def setLocalAt(self, runnerId):
        assert runnerId is not None
        self._properties['localAt'] = runnerId

    def clone(self):
        return _Input(self._properties)

class _Output:
    '''Dummy class for output products.
    In a configuration we do not care about outputs, but it is possible their
    locality will be initialised if they belong to the same local group as
    one of the inputs.
    '''

    def __init__(self, name):
        self.__productDef = productDefDB[name]

    def isLocal(self):
        return self.__productDef.isLocal()

    def setLocalAt(self, runnerId):
        assert runnerId is not None

class TaskSetWithInputs(TaskSet):

    def __init__(self):
        TaskSet.__init__(self)
        self._inputs = {}

    def getInput(self, name):
        return self._inputs.get(name)

    def getInputs(self):
        return self._inputs.values()

    def getProductDef(self, name):
        # Get the latest version.
        return productDefDB[name]

    def getProductLocation(self, name):
        product = self.getInput(name)
        return None if product is None else product.get('localAt')

    def getInputsGrouped(self):
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
        for task in self._getMainGroup().getChildren():
            group = set() if task.isGroup() else None
            for inpName in task.getInputs():
                if inpName in inputSet:
                    inpObj = self._inputs.get(inpName)
                    if inpObj is None:
                        inpObj = _Input({ 'name': inpName })
                    if group is not None and inpObj.isLocal():
                        group.add(inpObj)
                    else:
                        ungrouped.add(inpObj)
            if group:
                grouped.append(( task, sorted(group) ))
        return [ ( None, [ item ] ) for item in sorted(ungrouped) ] + \
            sorted(grouped)

    def hasLocalInputs(self):
        return any(inp.isLocal() for inp in self._inputs.values())

class Config(
    TaskSetWithInputs, TaskRunnerSet, XMLTag, Selectable, DatabaseElem
    ):
    tagName = 'config'
    boolProperties = ('trselect',)
    cache = ObservingTagCache(
        configDB,
        # pylint: disable=unnecessary-lambda
        # The lambda construct is essential, since "project" redirects its
        # members to a new object when it is database entry gets updated.
        lambda: project.getTagKeys()
        )

    @staticmethod
    def create(
        name, target, owner, trselect, comment, jobParams, tasks, runners
        ):
        properties = dict(
            name = name,
            target = target,
            owner = owner,
            trselect = trselect,
            )

        config = Config(properties)
        # pylint: disable=protected-access
        config.__comment = comment
        config.__params = dict(jobParams)
        config._setRunners(runners)
        for task in tasks:
            config._tasks[task['name']] = task
        config.__updateInputs()
        return config

    def __init__(self, attributes):
        # Note: if the "comment" tag is empty, the XML parser does not call the
        #       <text> handler, so we have to use '' rather than None here.
        TaskSetWithInputs.__init__(self)
        TaskRunnerSet.__init__(self)
        XMLTag.__init__(self, attributes)
        Selectable.__init__(self)
        DatabaseElem.__init__(self)
        self.__comment = ''
        self.__params = {}
        self.__description = None

    def __updateInputs(self):
        '''This should be called after tasks are added, to recompute which
        inputs this configuration has.
        '''
        self._inputs = dict(
            ( item, self._inputs.get(item, _Input({ 'name': item })) )
            for item in self.getInputSet()
            )

    def getId(self):
        return self._properties['name']

    def getOwner(self):
        return self._properties.get('owner')

    @property
    def comment(self):
        """Gets user-specified comment string for this job configuration.
        Comment string may contain newlines.
        """
        return self.__comment

    def __getitem__(self, key):
        if key == 'owner':
            return self.getOwner()
        elif key == 'comment':
            return self.__comment
        elif key == 'description':
            return self.getDescription()
        elif key == 'nrtasks':
            return len(self._tasks)
        else:
            return XMLTag.__getitem__(self, key)

    def _addTask(self, attributes):
        task = Task(attributes)
        self._tasks[task['name']] = task
        return task

    def _addInput(self, attributes):
        inp = _Input(attributes)
        self._inputs[inp['name']] = inp

    def _addParam(self, attributes):
        self.__params[attributes['name']] = attributes['value']

    def _textComment(self, text):
        self.__comment = text

    def getProduct(self, name):
        inp = self._inputs.get(name)
        if inp is None:
            return _Output(name)
        else:
            return inp

    # So far used for testing only
    def getParams(self):
        return dict(self.__params)

    def getParameter(self, name):
        return self.__params.get(name)

    def isConsistent(self):
        """Returns True iff this configuration can be instantiated.
        It is possible for a configuration to consistent when it is created
        but become inconsistent due to definitions changing, for example
        due to conflicting resource requirements.
        """
        refToType = {}
        for task in self._tasks.values():
            for spec in task.resourceClaim:
                typeName = spec.typeName
                if not typeName.startswith('sf.'):
                    if resTypeDB[typeName]['perjob']:
                        ref = spec.reference
                        if refToType.setdefault(ref, typeName) != typeName:
                            return False
        return True

    def iterInputConflicts(self):
        for inputName in self.getInputSet():
            pd = self.getProductDef(inputName)
            inp = self._inputs.get(inputName)
            if pd['type'] != ProductType.TOKEN and inp is None:
                yield 'missing locator for input "%s"' % inputName
            if pd.isLocal() and (inp is None or inp.get('localAt') is None):
                yield 'missing \'local at\' for input "%s"' % inputName

    def hasValidInputs(self):
        """Returns True iff this configuration can be instantiated without
        overriding inputs.
        """
        return not any(self.iterInputConflicts())

    def createJob(
        # pylint: disable=dangerous-default-value
        # We only read the default dictionaries.
        self, owner, comment = None,
        locators = {}, params = {}, localAt = {},
        taskParameters = None
        ):
        jobParams = dict(self.__params)
        jobParams.update(params)

        job = Job.create(
            # configId is empty string when executing from scratch
            configId = self.getId() or None,
            target = self._properties['target'],
            owner = self._properties.get('owner') if owner is None else owner,
            comment = comment or self.__comment,
            jobParams = jobParams,
            runners = self._runners,
            )

        for task in self.getTaskSequence():
            if taskParameters:
                taskParams = taskParameters.get(task['name'])
            else:
                taskParams = None
            newTask = job.addTask(
                task['name'], task['priority'], task.getRunners()
                )
            for key, defValue in task.getDef().getParameters().items():
                if taskParams:
                    value = taskParams.get(key)
                else:
                    value = None
                if value is None:
                    value = task.getParameter(key)
                if value is None:
                    value = defValue
                newTask.addParameter(key, value)

        for index, item in enumerate(self.getInputSet()):
            inp = self._inputs.get(item)
            job.setInputLocator(
                item,
                locators.get(item, inp and inp.get('locator') or ''),
                localAt.get(item) or inp and inp.get('localAt'),
                'SF_USER_INPUT_%d' % index
                )

        return job

    def _getContent(self):
        if self.__comment:
            yield xml.comment[ self.__comment ]
        yield from self._tasks.values()
        yield from self._inputs.values()
        for name, value in self.__params.items():
            yield xml.param(name = name, value = value)
        yield self.runnersAsXML()
        yield self._tagsAsXML()

    def getDescription(self):
        if self.__description is None:
            self.__description = TaskSet.getDescription(self)
            self.__registerNotify()
        return self.__description

    def _invalidate(self):
        self.__unregisterNotify()
        self.__description = None

    def _unload(self):
        self.__unregisterNotify()

    def __registerNotify(self):
        frameworks = {}
        for task in self.getTasks():
            _tdObserver.addObserver(task.getName(), self)
            framework = task.getDef().getFramework()
            frameworks[framework.getId()] = framework
        products = set()
        for frameworkId, framework in frameworks.items():
            _fdObserver.addObserver(frameworkId, self)
            products |= framework.getInputs() | framework.getOutputs()
        for product in products:
            _pdObserver.addObserver(product, self)

    def __unregisterNotify(self):
        for proxy in (_tdObserver, _fdObserver, _pdObserver):
            proxy.delAllObservers(self)

def iterConfigsByTag(key, value):
    cvalue, dvalue_ = Config.cache.toCanonical(key, value)
    for config in configDB:
        if config.hasTagValue(key, cvalue):
            yield config

# Force loading of DB, so TagCache is filled with all existing tag values.
# TODO: Is there an alternative?
configDB.preload()
