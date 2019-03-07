# SPDX-License-Identifier: BSD-3-Clause

import sys
from abc import ABC
from enum import Enum
from typing import ClassVar, Mapping, Optional, Sequence, Union

from softfab.Page import FabResource, ProcT, Responder
from softfab.StyleResources import styleRoot
from softfab.UIPage import UIPage
from softfab.authentication import LoginAuthPage
from softfab.refresh import RefreshScript
from softfab.utils import abstract
from softfab.webgui import Widget, pageURL
from softfab.xmlgen import xhtml

class _WidgetResponder(Responder):

    def __init__(self, page, widget):
        Responder.__init__(self)
        self.__page = page
        self.__widget = widget

    def respond(self, response, proc):
        self.__page.writeHTTPHeaders(response)
        response.write(self.__widget.present(proc=proc))

IconModifier = Enum('IconModifier', 'NONE EDIT DELETE')

class FabPage(UIPage[ProcT], FabResource[ProcT], ABC):
    authenticator = LoginAuthPage

    __pageInfo = {} # type: ClassVar[Mapping[str, object]]

    icon = abstract # type: ClassVar[Optional[str]]
    iconModifier = IconModifier.NONE # type: ClassVar[IconModifier]
    description = abstract # type: ClassVar[str]
    # Description used to link from the parent to this page.
    # If set to None (default), the value of the "description" field is used.
    # If set to False, the parent will not link to this page.
    linkDescription = None # type: ClassVar[Union[str, bool, None]]
    children = [] # type: ClassVar[Sequence[str]]

    # TODO: Because this is a static method, it is not possible to disable
    #       pages (like AddUser) for certain roles.
    #       We could solve this by passing the request object: we separate
    #       the page and the request anyway.
    #       However, we would have to redesign the __pageInfo mechanism,
    #       since currently this does not contain instances of pages.
    @staticmethod
    def isActive():
        """Returns True iff this page should currently be shown.

        Inactive pages are not shown in the navigation bar and when accessed
        directly, the browser will be redirected to the parent page.
        By default, pages are active.
        """
        return True

    @classmethod
    def __processPage(cls, name, parents = ()):
        baseModule = cls.__module__.split('.')[ : -1]
        fullName = '.'.join(baseModule + [name])
        if fullName not in sys.modules:
            __import__(fullName)
        module = sys.modules[fullName]
        pageClass = getattr(module, name, None) \
            or getattr(module, name + '_GET')
        description = pageClass.description
        linkDescription = pageClass.linkDescription
        if linkDescription is None:
            linkDescription = pageClass.description
        # TODO: Maybe it's easier to just store the class reference?
        cls.__pageInfo[name] = {
            'parents': parents,
            'icon': None if pageClass.icon is None
                else styleRoot.addIcon(pageClass.icon),
            'iconModifier': pageClass.iconModifier,
            'description': description,
            'linkDescription': linkDescription,
            'isActive': pageClass.isActive,
            'parameters': frozenset(pageClass.Arguments.iterMandatoryArgs()),
            'pageClass': pageClass,
            }

        parentsInc = tuple(parents) + ( name, )
        for child in pageClass.children:
            cls.__processPage(child, parentsInc)

    @classmethod
    def getPageInfo(cls, page = None):
        if len(cls.__pageInfo) == 0:
            cls.__processPage('Home')
        return cls.__pageInfo[page or cls.getResourceName()]

    @classmethod
    def getPageURL(cls, req, page):
        '''Gets the URL of another page, relative to this page.
        This URL includes in its query part the arguments shared between
        this page and the other page.
        If the other page requires arguments not present in this page,
        None is returned.
        '''
        otherArgClass = cls.getPageInfo(page)['pageClass'].Arguments
        try:
            args = req.args
        except AttributeError:
            # No arguments available.
            try:
                emptyArgs = otherArgClass()
            except KeyError:
                # Other page has mandatory arguments.
                return None
            else:
                return pageURL(page, emptyArgs)

        # Only gather shared arguments that are mandatory in at least one
        # of the pages. In practice this preserves the arguments we want
        # to share across pages, such as selected names, while dropping
        # arguments such as sort order.
        ourArgClass = args.__class__
        sharedArgs = {}
        for name in otherArgClass.iterMandatoryArgs():
            if hasattr(args, name) and args.isArgument(name):
                if getattr(ourArgClass, name) == getattr(otherArgClass, name):
                    sharedArgs[name] = getattr(args, name)
                else:
                    # We share a name with a mandatory argument, but it's not
                    # the same argument.
                    return None
            else:
                # Mandatory argument missing.
                return None
        for name in args.iterMandatoryArgs():
            if hasattr(otherArgClass, name) and otherArgClass.isArgument(name):
                if getattr(ourArgClass, name) == getattr(otherArgClass, name):
                    sharedArgs[name] = getattr(args, name)

        return pageURL(page, otherArgClass(sharedArgs))

    @classmethod
    def iterRootPath(cls):
        currPageName = cls.getResourceName()
        yield from cls.getPageInfo(currPageName)['parents']
        yield currPageName

    @classmethod
    def iterActiveChildren(cls):
        myParameters = cls.getPageInfo()['parameters']
        for childName in cls.children:
            pageInfo = cls.getPageInfo(childName)
            if not pageInfo['parameters'] - myParameters:
                if pageInfo['isActive']():
                    yield childName

    def getResponder(self, path, proc):
        if path is None:
            return self
        for widget in self.iterWidgets(proc):
            if widget.widgetId == path:
                if isinstance(widget, type):
                    widget = widget.instance
                return _WidgetResponder(self, widget)
        raise KeyError('Page does not contain a widget named "%s"' % path)

    def pageTitle(self, proc: ProcT) -> str:
        return self.description

    def presentHeader(self, proc):
        yield super().presentHeader(proc)
        yield LinkBar.instance.present(proc=proc)

    def presentContent(self, proc):
        # This method is already declared abstract in UIPage, we re-assert
        # that here to please PyLint.
        raise NotImplementedError

    def presentBackgroundScripts(self, proc):
        autoUpdateWidgets = [
            widget
            for widget in self.iterWidgets(proc)
            if widget.autoUpdate
            ]
        if autoUpdateWidgets:
            yield RefreshScript(*autoUpdateWidgets).present(proc=proc)

    def getParentURL(self, req):
        for ancestor in reversed(self.getPageInfo()['parents']):
            url = self.getPageURL(req, ancestor)
            if url is not None:
                return url
        # In normal situations, the home page will be in the ancestry,
        # so it is unlikely we will ever get here.
        return 'Home'

    def backToParent(self, req):
        parentName = self.getPageInfo()['parents'][-1]
        parentURL = self.getPageURL(req, parentName)
        return xhtml.p[
            xhtml.a(href = parentURL)[
                'Back to ', self.getPageInfo(parentName)['description']
                ]
            ]

    def backToReferer(self, req):
        refererName = req.args.refererName
        if refererName is None:
            # No referer, fall back to page hierarchy.
            return self.backToParent(req)

        return xhtml.p[
            xhtml.a(href = req.args.refererURL)[
                'Back to ', self.getPageInfo(refererName)['description']
                ]
            ]

    def backToSelf(self):
        url = self.name
        return xhtml.p[ xhtml.a(href = url)[ 'Back to ', self.description ] ]

class LinkBar(Widget):
    '''A bar which contains links to other pages.
    '''

    # These icons are referenced from the style sheet.
    styleRoot.addIcon('IconNew')
    styleRoot.addIcon('IconEdit')
    styleRoot.addIcon('IconDelete')

    __levelSep = xhtml.div(class_ = 'level')[ '\u25B8' ]

    def __createLinkButton(self, proc, pageName, infoKey):
        page = proc.page
        pageInfo = page.getPageInfo(pageName)
        description = pageInfo[infoKey]
        if description is False:
            return None
        url = page.getPageURL(proc.req, pageName)
        if url is None:
            return None
        icon = pageInfo['icon'].present(proc=proc)

        iconModifier = pageInfo['iconModifier']
        iconStyle = ['navicon']
        if iconModifier is IconModifier.EDIT:
            iconStyle.append('editicon' if pageName == page.name else 'newicon')
        elif iconModifier is IconModifier.DELETE:
            iconStyle.append('delicon')
        else:
            assert iconModifier is IconModifier.NONE, iconModifier

        style = 'navthis' if pageName == page.name else None
        return xhtml.div(class_ = style)[
            xhtml.a(href = url)[
                xhtml.span(class_=' '.join(iconStyle))[ icon ],
                xhtml.span(class_='navlabel')[ description ]
                ]
            ]

    def __presentButtons(self, proc):
        childButtons = tuple(self.__presentChildButtons(proc))
        levelSep = self.__levelSep
        # Root path.
        yield levelSep.join(self.__presentRootButtons(proc, bool(childButtons)))
        # Children.
        if childButtons:
            yield levelSep
            yield from childButtons

    def __presentRootButtons(self, proc, styleThis):
        page = proc.page
        thisPage = page.name
        for pageName in page.iterRootPath():
            button = self.__createLinkButton(proc, pageName, 'description')
            if button is not None:
                if pageName != thisPage or styleThis:
                    yield button.addClass('rootpath')
                else:
                    yield button

    def __presentChildButtons(self, proc):
        for pageName in proc.page.iterActiveChildren():
            button = self.__createLinkButton(proc, pageName, 'linkDescription')
            if button is not None:
                yield button

    def present(self, *, proc, **kwargs):
        return xhtml.div(class_ = 'linkbar')[ self.__presentButtons(proc) ]
