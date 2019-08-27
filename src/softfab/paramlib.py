# SPDX-License-Identifier: BSD-3-Clause

from typing import Callable, Dict, Mapping, Optional, Set

from softfab.utils import ResultKeeper
from softfab.xmlgen import XMLAttributeValue, XMLContent, xml

specialParameters = set([ 'sf.wrapper', 'sf.extractor', 'sf.timeout' ])
'''specialParameters will not be listed in the Parameters section
'''

GetParent = Callable[[str], 'Parameterized']

class Parameterized:
    '''Interface for objects that have inheritable parameters.
    '''

    def getParameter(self,
                     name: str,
                     getParent: Optional[GetParent] = None
                     ) -> Optional[str]:
        '''Returns the value of the parameter with the given name, or None if
        no such parameter exists.
        '''
        raise NotImplementedError

    def getParameters(self,
                      getParent: Optional[GetParent] = None
                      ) -> Dict[str, str]:
        '''Returns a new dictionary containing the parameters from this level
        and its parents.
        '''
        raise NotImplementedError

    def getParametersSelf(self) -> Dict[str, str]:
        """Returns a new dictionary containing the parameters only from this
        level, without inheriting values from the parent level.
        Most of the time getParameters (which does inherit) should be used
        instead, except when editing this level.
        """
        raise NotImplementedError

    def isFinal(self,
                name: str,
                getParent: Optional[GetParent] = None
                ) -> bool:
        '''Returns True if the parameter with the given name is final,
        False if it is not final (can be overridden).
        If the parameter does not exist, False is returned as well.
        '''
        raise NotImplementedError

    def getFinalSelf(self) -> Set[str]:
        '''Returns a set containing the names of the parameters that are
        declared final on this level.
        '''
        raise NotImplementedError

class _ParamTop(Parameterized):
    '''Object at the top of a parameter inheritance hierarchy.

    It is immutable and contains no parameters.
    '''

    def getParameter(self,
                     name: str,
                     getParent: Optional[GetParent] = None
                     ) -> Optional[str]:
        return None

    def getParameters(self,
                      getParent: Optional[GetParent] = None
                      ) -> Dict[str, str]:
        return {}

    def getParametersSelf(self) -> Dict[str, str]:
        return {}

    def isFinal(self,
                name: str,
                getParent: Optional[GetParent] = None
                ) -> bool:
        return False

    def getFinalSelf(self) -> Set[str]:
        return set()

paramTop = _ParamTop()

class ParamMixin(Parameterized):
    '''Reuseable implementation of inheritable parameters.
    '''

    def __init__(self) -> None:
        self.__parameters = {} # type: Dict[str, str]
        self.__finalParameters = set() # type: Set[str]

    def getParent(self, getFunc: Optional[GetParent]) -> Parameterized:
        '''Returns the parameterized record one level above this one.
        '''
        raise NotImplementedError

    def _addParameter(self, attributes: Mapping[str, str]) -> None:
        name = attributes['name']
        value = attributes.get('value')
        final = attributes.get('final') in ('True', 'true', '1')
        self.addParameter(name, value, final)

    def addParameter(self,
                     name: str,
                     value: Optional[str] = None,
                     final: bool = False
                     ) -> None:
        if value is not None:
            self.__parameters[name] = value
        if final:
            self.__finalParameters.add(name)

    def getParameter(self,
                     name: str,
                     getParent: Optional[GetParent] = None
                     ) -> Optional[str]:
        value = self.__parameters.get(name)
        if value is None:
            return self.getParent(getParent).getParameter(name, getParent)
        else:
            return value

    def getParameters(self,
                      getParent: Optional[GetParent] = None
                      ) -> Dict[str, str]:
        params = self.getParent(getParent).getParameters(getParent)
        params.update(self.getParametersSelf())
        return params

    def getParametersSelf(self) -> Dict[str, str]:
        return dict(self.__parameters)

    def isFinal(self,
                name: str,
                getParent: Optional[GetParent] = None
                ) -> bool:
        return name in self.__finalParameters \
            or self.getParent(getParent).isFinal(name, getParent)

    def getFinalSelf(self) -> Set[str]:
        return set(self.__finalParameters)

    def _paramsToXML(self) -> XMLContent:
        def keyFunc(key: str) -> Dict[str, XMLAttributeValue]:
            return {'name': key}
        params = ResultKeeper(keyFunc)
        for key, value in self.__parameters.items():
            params[key]['value'] = value
        for key in self.__finalParameters:
            params[key]['final'] = True
        for param in params.values():
            yield xml.parameter(**param)
