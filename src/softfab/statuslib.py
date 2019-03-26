# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from typing import ClassVar, Type

from twisted.internet.interfaces import IPushProducer
from zope.interface import implementer

from softfab.databaselib import Database, RecordObserver
from softfab.utils import SharedInstance, abstract
from softfab.xmlgen import xml


class StatusModel:
    '''A piece of Control Center state that can be observed.
    Objects of this type act as nodes in the model tree.

    Models can come and go at runtime and their availability can change
    between Control Center versions. We do not try to predict which models
    can or cannot exist in the future; instead we report "this model does
    not currently exist" if the model is not found.

    There is no distinction in type between leaf nodes and inner nodes, since
    for a non-existing model it is impossible to say whether or not it is a
    leaf; also a model that is a leaf in this Control Center version might
    become an inner node in a future version (aspects as separate children).

    Except for the root node, model node objects only exist if there are open
    views on them.
    '''

    @classmethod
    def getChildClass(cls):
        '''If all children of this model class belong to the same class,
        returns that class.
        If the children can belong to different classes, returns "object".
        If models of this class are always leaf nodes, returns None.
        '''
        raise NotImplementedError

    @classmethod
    def supportsFormat(cls, fmt):
        '''Returns True iff this model supports the given format.
        See _getFormatter() for details about the naming convention for
        formatting methods.
        '''
        return hasattr(cls, 'format' + fmt.capitalize())

    def __init__(self, modelId, parent):
        '''Creates a status model.
        Subclasses should be aware that this constructor calls the
        _registerForUpdates() method, so if that method requires some fields
        to be initialised, that initialisation must be done before the
        call to the superclass constructor.
        '''
        self.__modelId = modelId
        parentPath = None if parent is None else parent.getPath()
        self.__modelPath = (
            parentPath + '/' + modelId if parentPath else (modelId or '')
            )
        self.__parent = parent
        self._children = {}
        self.__views = {}
        self._registerForUpdates()

    def __iter__(self):
        return self._iterKeys()

    def __replaceModel(self, key, oldModel, newModel):
        '''Replaces "oldModel" by "newModel", preserving the subscribed views.
        Used when switching an AbsentModel for a real model or vice versa.
        TODO: If we want to support replacement of non-leaf models, we should
              recursively replace the child models too.
        '''
        # PyLint does not understand that "oldModel" and "newModel" are of
        # the same class as "self".
        # pylint: disable=protected-access

        # Sanity check on arguments.
        # Since this is a private method, we can use asserts for this.
        assert isinstance(oldModel, StatusModel)
        assert isinstance(newModel, StatusModel)
        assert oldModel.__parent is newModel.__parent is self
        assert oldModel.__modelId == newModel.__modelId == key

        # Replace child node.
        assert self._children[key] is oldModel
        self._destroyModel(key)
        self._children[key] = newModel
        # Migrate views.
        assert newModel.__views == {}
        newModel.__views = oldModel.__views
        oldModel.__views = {}

        # Tell the viewers about the new model.
        for view in newModel.__views.values():
            view._replaceModel(newModel)

    def _createModel(self, key):
        '''Creates a model object for the given key.
        Raises KeyError if there is no child model associated with the given
        key; this is also the default implementation.
        If you override this, also override _iterKeys().
        '''
        raise KeyError(key)

    def _iterKeys(self):
        '''Iterates through the keys of the child models.
        The default implementation is the empty iteration.
        If you override this, also override _createModel().
        '''
        return iter(())

    def _destroyModel(self, key):
        '''Called to remove a reference to a model object that has no views.
        This allows the model object to be garbage collected.
        When new views are created, the model will be refetched from its parent.
        '''
        #print 'removing', key, 'from', self._children
        model = self._children[key]
        del self._children[key]
        model._unregisterForUpdates() # pylint: disable=protected-access
        model.__parent = None

    def _getFormatter(self, fmt):
        '''Returns a callable that formats this model in the given format.
        If the format is not supported, a formatter is returned that produces
        an XML fragment indicating that the format is not supported.

        Formatters are located by a naming convention: the method implementing
        format "foo" must be named "formatFoo". Such a method should take no
        arguments other than "self" and return an XML fragment.
        '''
        return getattr(self, 'format' + fmt.capitalize(), self.noFormat)

    def _modelAdded(self, key):
        '''A subclass must call this method every time a new child model
        becomes available.
        It is not necessary to call this method for the child models that are
        available when this model was constructed.
        '''
        absentModel = self._children.get(key)
        if absentModel is not None:
            assert isinstance(absentModel, AbsentModel)
            # Someone has been observing the model since before it existed.
            self.__replaceModel(key, absentModel, self._createModel(key))

    def _modelRemoved(self, key):
        '''A subclass must call this method every time an existing child model
        becomes unavailable.
        '''
        model = self._children.get(key)
        if model is not None:
            assert not isinstance(model, AbsentModel)
            # Someone was observing the model.
            self.__replaceModel(key, model, AbsentModel(key, self))

    def _notify(self):
        for view in self.__views.values():
            view.update()

    def _registerForUpdates(self):
        '''Subclasses should override this to register themselves to the
        relevant database updates.
        '''
        raise NotImplementedError

    def _unregisterForUpdates(self):
        '''Subclasses should override this to undo the registrations done by
        the _registerForUpdates method.
        '''
        raise NotImplementedError

    def getId(self):
        return self.__modelId

    def getPath(self):
        return self.__modelPath

    def getChild(self, key):
        #print 'lookup:', key, 'in', self._children
        try:
            return self.getExistingChild(key)
        except KeyError:
            model = AbsentModel(key, self)
            self._children[key] = model
            return model

    def getExistingChild(self, key):
        '''Like getChild(), but raises KeyError if no child exists for the
        given key.
        '''
        try:
            return self._children[key]
        except KeyError:
            # Note: _createModel() can raise KeyError.
            #       The default implementation does so unconditionally,
            #       which is why PyLint thinks it doesn't return anything.
            model = self._createModel(key) # pylint: disable=assignment-from-no-return
            self._children[key] = model
            return model

    def createView(self, fmt):
        '''Gets a view on this model.
        '''
        view = self.__views.get(fmt)
        if view is None:
            view = StatusView(self, fmt)
            self.__views[fmt] = view
        return view

    def destroyView(self, fmt):
        del self.__views[fmt]
        #print 'remaining views on model "%s": %s' % (
        #    self.__modelPath, sorted(self.__views.keys())
        #    )
        if len(self.__views) == 0:
            # pylint: disable=protected-access
            self.__parent._destroyModel(self.__modelId)

    # TODO: Write generic formatters for child add/remove/modify.

    def noFormat(self):
        '''Formatter method used when the desired format is not supported.
        '''
        return xml.nosuchformat

class AbsentModel(StatusModel):
    '''Handles views on non-existing models.
    Keeps the list of views of a model, in case it becomes available later.
    '''

    @classmethod
    def getChildClass(cls):
        return object # The safe answer.

    def _registerForUpdates(self):
        # Non-existing models are never updated.
        pass

    def _unregisterForUpdates(self):
        pass

    def noFormat(self):
        # Make it clear that the reason we do not support any formats is that
        # the model node was not found. Otherwise, someone debugging a client
        # might start searching in the wrong direction.
        return xml.nosuchmodel

class DBStatusModelGroup(StatusModel, RecordObserver, ABC):
    '''A status model group based on a database.
    '''
    childClass = abstract # type: ClassVar[Type[StatusModel]]
    db = abstract # type: ClassVar[Database]

    @classmethod
    def getChildClass(cls):
        return cls.childClass

    def __init__(self, modelId, parent):
        StatusModel.__init__(self, modelId, parent)
        RecordObserver.__init__(self)

    def _createModel(self, key):
        return self.childClass(key, self)

    def _iterKeys(self):
        return self.db.keys()

    def _registerForUpdates(self):
        self.db.addObserver(self)

    def _unregisterForUpdates(self):
        self.db.removeObserver(self)

    def added(self, record):
        self._modelAdded(record.getId())

    def updated(self, record):
        child = self._children.get(record.getId())
        if child is not None:
            self._monitoredRecordUpdated(child, record)

    def removed(self, record):
        self._modelRemoved(record.getId())

    def _monitoredRecordUpdated(self, model, record):
        '''Can be overridden to be informed when a record of which the
        associated model is being monitored changes state.
        '''

class StatusModelRegistry(StatusModel):
    '''A central location where status models can be registered and looked up.
    Acts as the root of the model tree.
    '''
    instance = SharedInstance() # type: ClassVar[SharedInstance]

    @classmethod
    def getChildClass(cls):
        return object

    def __init__(self):
        StatusModel.__init__(self, None, None)
        self.__modelBuilders = {}

    def __walkModelPath(self, modelPath):
        for modelId in modelPath.split('/'):
            if modelId != '':
                yield modelId

    def _createModel(self, key):
        return self.__modelBuilders[key](key, self)

    def _iterKeys(self):
        return iter(self.__modelBuilders.keys())

    def _registerForUpdates(self):
        pass

    def _unregisterForUpdates(self):
        pass

    def addModelGroup(self, cls, name):
        self.__modelBuilders[name] = cls
        self._modelAdded(name)

    def getModel(self, modelPath):
        '''Looks up a model using the given model path: a slash-separated
        list of model IDs, starting at the root of the model tree.
        If the model does not exist, an AbsentModel instance is returned.
        '''
        model = self
        for modelId in self.__walkModelPath(modelPath):
            model = model.getChild(modelId)
        return model

    def getExistingModel(self, modelPath):
        '''Looks up a model using the given model path: a slash-separated
        list of model IDs, starting at the root of the model tree.
        If the model does not exist, KeyError is raised.
        '''
        model = self
        for modelId in self.__walkModelPath(modelPath):
            model = model.getExistingChild(modelId)
        return model

class StatusView:
    '''A particular formatting of a model's state.
    TODO: Instances of this class will not be cleaned up if addClient is never
          called on them. Although that will not happen in the current code,
          it is not an ideal design.
    '''

    def __init__(self, model, fmt):
        self.__model = model
        self.__format = fmt
        self.__formatter = model._getFormatter(fmt) # pylint: disable=protected-access
        self.__clients = []

    def __formatUpdate(self):
        # TODO: It is possible that the model has changed, but that the
        #       formatted result is still the same, for example because an
        #       aspect of the model that is not included in the formatting
        #       was the only aspect that changed. In these cases, it would
        #       be more efficient to not send an update to the clients.
        return xml.update(model = self.__model.getPath())[ self.__formatter() ]

    def _replaceModel(self, model):
        self.__model = model
        self.__formatter = \
            model._getFormatter(self.__format) # pylint: disable=protected-access
        # The new model is likely to have a different status.
        self.update()

    def addClient(self, client):
        '''Adds a client to which status updates will be sent.
        The initial status is also sent as an update.
        '''
        self.__clients.append(client)
        client.update(self.__formatUpdate())

    def removeClient(self, client):
        '''Removes a client to which status updates were sent.
        '''
        self.__clients.remove(client)
        if len(self.__clients) == 0:
            self.__model.destroyView(self.__format)
            self.__formatter = None

    def update(self):
        message = self.__formatUpdate()
        for client in self.__clients:
            client.update(message)

@implementer(IPushProducer)
class StatusViewClient:
    '''A client that monitors a status view.
    An object of this type can be constructed in the Processor, but it will
    not write to the request object until the presentation phase starts, as
    signalled by calling the startProducing() method.
    '''

    def __init__(self, response, view):
        self.__response = response
        self.__statusView = view

    def update(self, message):
        self.__response.writeXML(message)
        #print 'written:', message

    def startProducing(self):
        '''Signals that this Producer can start delivering data.
        The Producer interface allows a Producer to start when it is
        constructed, but that is not good for our use since we have to wait
        until we are in the presentation phase.
        '''
        self.__response.write('<updates>')
        # Register for updates.
        self.__statusView.addClient(self)

    # Producer interface:

    def resumeProducing(self):
        pass

    def pauseProducing(self):
        # We only send small amounts of data, so flow control is not worth the
        # complexity it introduces.
        pass

    def stopProducing(self):
        self.__statusView.removeClient(self)
        self.__response.unregisterProducer()
        # No-one should use the response object anymore; this way we will notice
        # if someone does.
        self.__response = None
