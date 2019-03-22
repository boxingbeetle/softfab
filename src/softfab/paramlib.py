# SPDX-License-Identifier: BSD-3-Clause

from typing import Callable, ClassVar, Dict, Mapping, Optional, Set

from softfab.utils import ResultKeeper, SharedInstance, SingletonMeta
from softfab.xmlgen import XMLAttributeValue, XMLContent, xml

specialParameters = set([ 'sf.wrapper', 'sf.extractor', 'sf.timeout' ])
'''specialParameters will not be listed in the Parameters section
'''

GetParent = Optional[Callable[[str], 'ParamMixin']]

class ParamMixin:
    '''Base class for objects that have inheritable parameters.
    '''

    @staticmethod
    def getParent(key: str) -> 'ParamMixin':
        raise NotImplementedError

    def __init__(self) -> None:
        self.__parameters = {} # type: Dict[str, str]
        self.__finalParameters = set() # type: Set[str]

    def __getParent(self, getFunc: GetParent) -> 'ParamMixin':
        if getFunc is None:
            getFunc = self.getParent
        parentName = self.getParentName()
        if parentName is None:
            return paramTop
        else:
            return getFunc(parentName)
        #return paramTop if parentName is None else getFunc(parentName)

    def _addParameter(self, attributes: Dict[str, str]) -> None:
        name = attributes['name']
        value = attributes.get('value')
        final = attributes.get('final') in ('True', 'true', '1')
        if name == 'sf.timeout' and value == '0':
            # COMPAT 2.x.x: takdefs without timeout used to store 0.
            return
        self.addParameter(name, value, final)

    def addParameter(self,
                     name: str,
                     value: Optional[str] = None,
                     final: bool = False
                     ) -> None:
        if value is not None:
            if isinstance(value, str):
                self.__parameters[name] = value
            else:
                raise TypeError(type(value))
        if final:
            self.__finalParameters.add(name)

    def getParentName(self) -> Optional[str]:
        '''Returns the name of the parent of this task definition,
        or None is this object has paramTop as its parent.
        '''
        properties = getattr(self, '_properties') # type: Dict[str, str]
        return properties.get('parent')

    def getParameter(self,
                     name: str,
                     getParent: GetParent = None
                     ) -> Optional[str]:
        '''Returns the value of the parameter with the given name, or None if
        no such parameter exists.
        '''
        value = self.__parameters.get(name)
        if value is None:
            return self.__getParent(getParent).getParameter(name, getParent)
        else:
            return value

    def getParameters(self,
                      getParent: GetParent = None
                      ) -> Dict[str, str]:
        '''Returns a dictionary containing the parameters from this level
        and its parents.
        '''
        params = self.__getParent(getParent).getParameters(getParent)
        params.update(self.getParametersSelf())
        return params

    def getParametersSelf(self) -> Dict[str, str]:
        """Returns a dictionary containing the parameters only from this
        level, without inheriting values from the parent level.
        Most of the time getParameters (which does inherit) should be used
        instead, except when editing this level.
        """
        return dict(self.__parameters)

    def isFinal(self,
                name: str,
                getParent: GetParent = None
                ) -> bool:
        '''Returns True if the parameter with the given name is final,
        False if it is not final (can be overridden).
        If the parameter does not exist, False is returned as well.
        '''
        return name in self.__finalParameters \
            or self.__getParent(getParent).isFinal(name, getParent)

    def getFinalSelf(self) -> Set[str]:
        '''Returns a set containing the names of the parameters that are
        declared final on this level.
        '''
        return set(self.__finalParameters)

    def _paramsToXML(self) -> XMLContent:
        params = ResultKeeper[str, Dict[str, XMLAttributeValue]](
            lambda key: { 'name': key }
            ) # type: Dict[str, Dict[str, XMLAttributeValue]]
        for key, value in self.__parameters.items():
            params[key]['value'] = value
        for key in self.__finalParameters:
            params[key]['final'] = True
        for param in params.values():
            yield xml.parameter(**param)

class _ParamTop(ParamMixin, metaclass=SingletonMeta):
    '''Singleton for object at the top of the parameter inheritance hierarchy.
    '''
    instance = SharedInstance() # type: ClassVar[SharedInstance[_ParamTop]]

    @staticmethod
    def getParent(key: str) -> 'ParamMixin':
        assert False

    def __init__(self) -> None:
        ParamMixin.__init__(self)
        self._properties = {} # type: Mapping[str, str]
        self.addParameter('sf.summary', 'log.txt', False)

    def getParameter(self,
                     name: str,
                     getParent: GetParent = None
                     ) -> Optional[str]:
        return self.getParametersSelf().get(name)

    def getParameters(self,
                      getParent: GetParent = None
                      ) -> Dict[str, str]:
        return self.getParametersSelf()

    def isFinal(self, name: str, getParent: GetParent = None) -> bool:
        return name in self.getFinalSelf()

paramTop = _ParamTop.instance
