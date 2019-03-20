# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import PageProcessor
from softfab.pageargs import PageArgs, StrArg
from softfab.statuslib import StatusModelRegistry
from softfab.userlib import User
from softfab.xmlgen import xml


def treeSupportsFormat(modelClass, fmt):
    '''Returns True iff the given model class or one of its descendants might
    support the given format, False iff the given format is certainly not
    supported.
    This method accepts None and "object" as model classes, to match the return
    values of StatusModel.getChildClass().
    The given format can be None to indicate that any format is allowed.
    '''
    if modelClass is None:
        # Node type invalid: parent was a leaf, this subtree does not exist.
        return False
    elif modelClass is object:
        # Node type unknown: it might support the format.
        return True
    else:
        # Node type known: query it and its children.
        return (
            fmt is None
            or modelClass.supportsFormat(fmt)
            or treeSupportsFormat(modelClass.getChildClass(), fmt)
            )

def modelToXML(model, fmt):
    '''Returns an XML tree iterator describing the given node and those
    children that can be presented in the given format. Subtrees that do not
    have any nodes that support the given format are omitted. Nodes that do not
    support the given format, but have children that do support the format, are
    returned with an attribute 'format="false"'.
    The given format can be None to indicate that any format is allowed.
    '''
    children = []
    childClass = model.getChildClass()
    if treeSupportsFormat(childClass, fmt):
        if childClass is not object and childClass.getChildClass() is None:
            # Special case: known child class which is a leaf.
            children.extend(xml.model(name = key) for key in model)
        else:
            # General case: always correct, but more instantiations.
            for key in model:
                for childXML in modelToXML(model.getChild(key), fmt):
                    children.append(childXML)
    supports = fmt is None or model.supportsFormat(fmt)
    name = model.getId() or '' # Root node will have empty name.
    if children:
        yield xml.model(
            name = name, format = None if supports else 'false'
            )[ children ]
    elif supports:
        yield xml.model(name = name)

class ListModels_GET(ControlPage['ListModels_GET.Arguments',
                                 'ListModels_GET.Processor']):

    class Arguments(PageArgs):
        model = StrArg(None)
        format = StrArg(None)

    class Processor(PageProcessor['ListModels_GET.Arguments']):
        pass

    def checkAccess(self, user: User) -> None:
        # Access will be checked for each model node.
        pass

    def writeReply(self, response, proc):
        try:
            root = StatusModelRegistry.instance.getExistingModel(
                proc.args.model or ''
                )
        except KeyError:
            modelXML = None
        else:
            modelXML = modelToXML(root, proc.args.format)
        response.write(xml.modellist[ modelXML ])
