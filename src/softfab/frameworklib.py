# SPDX-License-Identifier: BSD-3-Clause

from softfab.config import dbDir
from softfab.databaselib import DatabaseElem, VersionedDatabase
from softfab.paramlib import ParamMixin
from softfab.resreq import (
    ResourceClaim, ResourceSpec, taskRunnerResourceRefName
    )
from softfab.restypelib import taskRunnerResourceTypeName
from softfab.xmlbind import XMLTag
from softfab.xmlgen import xml

class FrameworkFactory:
    @staticmethod
    def createTaskdef(attributes):
        return Framework(attributes)

class FrameworkDB(VersionedDatabase):
    baseDir = dbDir + '/frameworks'
    factory = FrameworkFactory()
    privilegeObject = 'fd'
    description = 'framework'
    uniqueKeys = ( 'id', )
frameworkDB = FrameworkDB()

class TaskDefBase(ParamMixin, XMLTag, DatabaseElem):
    tagName = 'taskdef'

    @staticmethod
    def getParent(key):
        return frameworkDB[key]

    def __init__(self, properties):
        ParamMixin.__init__(self)
        XMLTag.__init__(self, properties)
        DatabaseElem.__init__(self)
        self.__resources = []
        self.__resourceClaim = None

    def __getitem__(self, key):
        if key == 'extract':
            return self.getParameter('sf.extractor') in ('True', 'true')
        elif key == 'parameters':
            return sorted(
                param for param in self.getParameters()
                if not param.startswith('sf.') and not self.isFinal(param)
                )
        return XMLTag.__getitem__(self, key)

    def _addResource(self, attributes):
        if attributes['type'] == taskRunnerResourceTypeName:
            # COMPAT 2.16: Force reference name for TR.
            attributes['ref'] = taskRunnerResourceRefName
        spec = ResourceSpec(attributes)
        self.addResourceSpec(spec)
        return spec

    def addResourceSpec(self, spec):
        self.__resources.append(spec)
        self.__resourceClaim = None

    def addTaskRunnerSpec(self, capabilities=()):
        self.addResourceSpec(ResourceSpec.create(
            taskRunnerResourceRefName, taskRunnerResourceTypeName, capabilities
            ))

    def getId(self):
        return self['id']

    @property
    def resourceClaim(self):
        """The resource requirements for this task."""
        claim = self.__resourceClaim
        if claim is None:
            claim = ResourceClaim.create(self.__resources)
            self.__resourceClaim = claim
        return claim

    def _getContent(self):
        yield self._paramsToXML()
        yield self.__resources

class Framework(TaskDefBase):

    @staticmethod
    def create(name, inputs, outputs):
        properties = dict(
            id = name,
            )
        framework = Framework(properties)
        framework.__inputs = set(inputs)
        framework.__outputs = set(outputs)
        return framework

    def __init__(self, properties):
        TaskDefBase.__init__(self, properties)
        self.__inputs = set()
        self.__outputs = set()

    def __getitem__(self, key):
        if key == 'inputs':
            return sorted(self.getInputs())
        elif key == 'outputs':
            return sorted(self.getOutputs())
        elif key == 'wrapper':
            return self.getParameters()['sf.wrapper']
        else:
            return TaskDefBase.__getitem__(self, key)

    def _addInput(self, attributes):
        self.__inputs.add(attributes['name'])

    def _addOutput(self, attributes):
        self.__outputs.add(attributes['name'])

    def getParametersSelf(self):
        params = super().getParametersSelf()
        params.setdefault('sf.wrapper', self.getId())
        return params

    def getFinalSelf(self):
        finals = super().getFinalSelf()
        finals.add('sf.wrapper')
        return finals

    def isFinal(self, parameter, getParent = frameworkDB.__getitem__):
        return parameter in ('sf.wrapper', 'sf.extractor') \
            or super().isFinal(parameter, getParent)

    def getInputs(self):
        """Gets a set of the names of all products
        that are necessary as input for running this framework.
        """
        return self.__inputs

    def getOutputs(self):
        """Gets a set of the names of all products
        that can be produced by this framework.
        """
        return self.__outputs

    def _getContent(self):
        yield from super()._getContent()
        for inp in self.__inputs:
            yield xml.input(name=inp)
        for out in self.__outputs:
            yield xml.output(name=out)

def anyExtract():
    '''Returns True iff there is any framework that requires extraction.
    '''
    return any(framework['extract'] for framework in frameworkDB)
