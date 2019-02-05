# SPDX-License-Identifier: BSD-3-Clause

from typing import ClassVar

from utils import ResultKeeper, SharedInstance, SingletonMeta
from xmlgen import xml

specialParameters = set([ 'sf.wrapper', 'sf.extractor', 'sf.timeout' ])
'''specialParameters will not be listed in the Parameters section
'''

class ParamMixin:
    '''Base class for objects that have inheritable parameters.
    '''

    @staticmethod
    def getParent(key):
        raise NotImplementedError

    def __init__(self):
        self.__parameters = {} # maps name to value
        self.__finalParameters = set()

    def __getParent(self, getFunc):
        if getFunc is None:
            getFunc = self.getParent
        parentName = self.getParentName()
        return paramTop if parentName is None else getFunc(parentName)

    def _addParameter(self, attributes):
        name = attributes['name']
        value = attributes.get('value')
        final = attributes.get('final') in ('True', 'true', '1')
        if name == 'sf.timeout' and value == '0':
            # COMPAT 2.x.x: takdefs without timeout used to store 0.
            return
        self.addParameter(name, value, final)

    def addParameter(self, name, value = None, final = False):
        if value is not None:
            if isinstance(value, str):
                self.__parameters[name] = value
            else:
                raise TypeError(type(value))
        if final:
            self.__finalParameters.add(name)

    def getParentName(self):
        '''Returns the name of the parent of this task definition,
        or None is this object has paramTop as its parent.
        '''
        return self._properties.get('parent')

    def getParameter(self, name, getParent = None):
        '''Returns the value of the parameter with the given name, or None if
        no such parameter exists.
        '''
        value = self.__parameters.get(name)
        if value is None:
            return self.__getParent(getParent).getParameter(name, getParent)
        else:
            return value

    def getParameters(self, getParent = None):
        '''Returns a dictionary containing the parameters from this level
        and its parents.
        '''
        params = self.__getParent(getParent).getParameters(getParent)
        params.update(self.getParametersSelf())
        return params

    def getParametersSelf(self):
        """Returns a dictionary containing the parameters only from this
        level, without inheriting values from the parent level.
        Most of the time getParameters (which does inherit) should be used
        instead, except when editing this level.
        """
        return dict(self.__parameters)

    def isFinal(self, parameter, getParent = None):
        '''Returns True if the parameter with the given name is final,
        False if it is not final (can be overridden).
        If the parameter does not exist, False is returned as well.
        '''
        return parameter in self.__finalParameters \
            or self.__getParent(getParent).isFinal(parameter, getParent)

    def getFinalSelf(self):
        '''Returns a set containing the names of the parameters that are
        declared final on this level.
        '''
        return set(self.__finalParameters)

    def _paramsToXML(self):
        params = ResultKeeper(lambda key: { 'name': key })
        for key, value in self.__parameters.items():
            params[key]['value'] = value
        for key in self.__finalParameters:
            params[key]['final'] = True
        for param in params.values():
            yield xml.parameter(**param)

class _ParamTop(ParamMixin, metaclass=SingletonMeta):
    '''Singleton for object at the top of the parameter inheritance hierarchy.
    '''
    instance = SharedInstance() # type: ClassVar[SharedInstance]

    @staticmethod
    def getParent(key):
        return None

    def __init__(self):
        ParamMixin.__init__(self)
        self._properties = {}
        self.addParameter('sf.summary', 'log.txt', False)

    def getParameter(self, name, getParent = None):
        return self.getParametersSelf().get(name)

    def getParameters(self, getParent = None):
        return self.getParametersSelf()

    def isFinal(self, parameter, getParent = None):
        return parameter in self.getFinalSelf()

paramTop = _ParamTop.instance
