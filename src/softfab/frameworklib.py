# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
from typing import (
    AbstractSet, Dict, Iterable, List, Mapping, Optional, Set, cast
)

from softfab.config import dbDir
from softfab.databaselib import DatabaseElem, VersionedDatabase
from softfab.paramlib import GetParent, ParamMixin, Parameterized, paramTop
from softfab.resreq import (
    ResourceClaim, ResourceSpec, taskRunnerResourceRefName
)
from softfab.restypelib import taskRunnerResourceTypeName
from softfab.xmlbind import XMLTag
from softfab.xmlgen import XMLContent, xml


class FrameworkFactory:
    @staticmethod
    def createTaskdef(attributes: Mapping[str, str]) -> 'Framework':
        return Framework(attributes)

class FrameworkDB(VersionedDatabase['Framework']):
    privilegeObject = 'fd'
    description = 'framework'
    uniqueKeys = ( 'id', )

    def __init__(self, baseDir: Path):
        super().__init__(baseDir, FrameworkFactory())

frameworkDB = FrameworkDB(dbDir / 'frameworks')

class TaskDefBase(XMLTag, ParamMixin, DatabaseElem):
    tagName = 'taskdef'

    def __init__(self, properties: Mapping[str, Optional[str]]):
        super().__init__(properties)
        self.__resources: List[ResourceSpec] = []
        self.__resourceClaim: Optional[ResourceClaim] = None

    def __getitem__(self, key: str) -> object:
        if key == 'parameters':
            return sorted(
                param for param in self.getParameters()
                if not param.startswith('sf.') and not self.isFinal(param)
                )
        return XMLTag.__getitem__(self, key)

    def _addResource(self, attributes: Dict[str, str]) -> ResourceSpec:
        if attributes['type'] == taskRunnerResourceTypeName:
            # COMPAT 2.16: Force reference name for TR.
            attributes['ref'] = taskRunnerResourceRefName
        spec = ResourceSpec(attributes)
        self.addResourceSpec(spec)
        return spec

    def addResourceSpec(self, spec: ResourceSpec) -> None:
        self.__resources.append(spec)
        self.__resourceClaim = None

    def addTaskRunnerSpec(self, capabilities: Iterable[str] = ()) -> None:
        self.addResourceSpec(ResourceSpec.create(
            taskRunnerResourceRefName, taskRunnerResourceTypeName, capabilities
            ))

    def getId(self) -> str:
        return cast(str, self['id'])

    def getParent(self, getFunc: Optional[GetParent]) -> Parameterized:
        raise NotImplementedError

    @property
    def resourceClaim(self) -> ResourceClaim:
        """The resource requirements for this task."""
        claim = self.__resourceClaim
        if claim is None:
            claim = ResourceClaim.create(self.__resources)
            self.__resourceClaim = claim
        return claim

    def _getContent(self) -> XMLContent:
        yield self._paramsToXML()
        yield self.__resources

class Framework(TaskDefBase):

    @staticmethod
    def create(name: str,
               inputs: Iterable[str],
               outputs: Iterable[str]
               ) -> 'Framework':
        properties = dict(
            id = name,
            )
        # pylint: disable=protected-access
        #   https://github.com/PyCQA/pylint/issues/2825
        framework = Framework(properties)
        framework.__inputs = set(inputs)
        framework.__outputs = set(outputs)
        return framework

    def __init__(self, properties: Mapping[str, str]):
        super().__init__(properties)
        self.__inputs: Set[str] = set()
        self.__outputs: Set[str] = set()

    def __getitem__(self, key: str) -> object:
        if key == 'inputs':
            return sorted(self.getInputs())
        elif key == 'outputs':
            return sorted(self.getOutputs())
        elif key == 'wrapper':
            return self.getParameters()['sf.wrapper']
        else:
            return TaskDefBase.__getitem__(self, key)

    def _addInput(self, attributes: Dict[str, str]) -> None:
        self.__inputs.add(attributes['name'])

    def _addOutput(self, attributes: Dict[str, str]) -> None:
        self.__outputs.add(attributes['name'])

    def getParent(self, getFunc: Optional[GetParent]) -> Parameterized:
        return paramTop

    def getParametersSelf(self) -> Dict[str, str]:
        params = super().getParametersSelf()
        params.setdefault('sf.wrapper', self.getId())
        return params

    def getFinalSelf(self) -> Set[str]:
        finals = super().getFinalSelf()
        finals.add('sf.wrapper')
        return finals

    def isFinal(self,
                name: str,
                getParent: Optional[GetParent] = None
                ) -> bool:
        return name == 'sf.wrapper' or super().isFinal(name, getParent)

    def getInputs(self) -> AbstractSet[str]:
        """Gets a set of the names of all products
        that are necessary as input for running this framework.
        """
        return self.__inputs

    def getOutputs(self) -> AbstractSet[str]:
        """Gets a set of the names of all products
        that can be produced by this framework.
        """
        return self.__outputs

    def _getContent(self) -> XMLContent:
        yield super()._getContent()
        for inp in self.__inputs:
            yield xml.input(name=inp)
        for out in self.__outputs:
            yield xml.output(name=out)
