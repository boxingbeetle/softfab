# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from enum import Enum
from typing import (
    Any, ClassVar, Dict, Iterable, Iterator, Mapping, Optional, Sequence,
    Union, cast
)
import sys

from softfab.Page import FabResource, PageProcessor, ProcT, Responder
from softfab.StyleResources import styleRoot
from softfab.UIPage import UIPage
from softfab.authentication import LoginAuthPage
from softfab.pageargs import ArgsT
from softfab.refresh import RefreshScript
from softfab.response import Response
from softfab.utils import abstract
from softfab.webgui import Widget, pageURL
from softfab.xmlgen import XMLContent, XMLNode, xhtml

IconModifier = Enum('IconModifier', 'NONE NEW EDIT DELETE')

class FabPage(UIPage[ProcT], FabResource[ArgsT, ProcT], ABC):
    authenticator = LoginAuthPage.instance

    __pageInfo = {} # type: ClassVar[Dict[str, Mapping[str, Any]]]

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
    def isActive() -> bool:
        """Returns True iff this page should currently be shown.

        Inactive pages are not shown in the navigation bar and when accessed
        directly, the browser will be redirected to the parent page.
        By default, pages are active.
        """
        return True

    @classmethod
    def __processPage(cls, name: str, parents: Sequence[str] = ()) -> None:
        baseModule = cls.__module__.split('.')[ : -1]
        fullName = '.'.join(baseModule + [name])
        if fullName not in sys.modules:
            __import__(fullName)
        module = sys.modules[fullName]
        pageClass = getattr(module, name + '_GET')
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
    def getPageInfo(cls, page: Optional[str] = None) -> Mapping[str, Any]:
        if len(cls.__pageInfo) == 0:
            cls.__processPage('Home')
        return cls.__pageInfo[page or cls.getResourceName()]

    @classmethod
    def getPageURL(cls, page: str, args: Optional[ArgsT]) -> Optional[str]:
        '''Gets the URL of another page, relative to this page.
        This URL includes in its query part the arguments shared between
        this page and the other page.
        If the other page requires arguments not present in this page,
        None is returned.
        '''
        otherArgClass = cls.getPageInfo(page)['pageClass'].Arguments
        if args is None:
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
    def iterRootPath(cls) -> Iterator[str]:
        currPageName = cls.getResourceName()
        yield from cls.getPageInfo(currPageName)['parents']
        yield currPageName

    @classmethod
    def iterActiveChildren(cls) -> Iterator[str]:
        myParameters = cls.getPageInfo()['parameters']
        for childName in cls.children:
            pageInfo = cls.getPageInfo(childName)
            if not pageInfo['parameters'] - myParameters:
                if pageInfo['isActive']():
                    yield childName

    def getResponder(self,
                     path: Optional[str],
                     proc: PageProcessor
                     ) -> Responder:
        if path is None:
            return super().getResponder(None, proc)
        for widget in self.iterWidgets(cast(ProcT, proc)):
            if widget.widgetId == path:
                return _WidgetResponder(self, widget, proc)
        raise KeyError('Page does not contain a widget named "%s"' % path)

    def pageTitle(self, proc: ProcT) -> str:
        return self.description

    def __createLinkButton(self,
            pageName: str, infoKey: str, args: Optional[ArgsT]
            ) -> Optional['LinkBarButton']:
        pageInfo = self.getPageInfo(pageName)

        description = pageInfo[infoKey]
        if description is False:
            return None

        url = self.getPageURL(pageName, args)
        if url is None:
            return None

        return LinkBarButton(
            label=description,
            url=url,
            icon=pageInfo['icon'],
            modifier=pageInfo['iconModifier'],
            active=pageName == self.name
            )

    def __createLinkButtons(self,
            pageNames: Iterable[str], infoKey: str, args: Optional[ArgsT]
            ) -> Iterator['LinkBarButton']:
        for name in pageNames:
            button = self.__createLinkButton(name, infoKey, args)
            if button is not None:
                yield button

    def presentHeader(self, proc: ProcT) -> XMLContent:
        yield super().presentHeader(proc)
        yield LinkBar.instance.present(
            rootButtons=tuple(self.__createLinkButtons(
                self.iterRootPath(), 'description', proc.args
                )),
            childButtons=tuple(self.__createLinkButtons(
                self.iterActiveChildren(), 'linkDescription', proc.args
                ))
            )

    def presentContent(self, proc: ProcT) -> XMLContent:
        # This method is already declared abstract in UIPage, we re-assert
        # that here to please PyLint.
        raise NotImplementedError

    def presentBackgroundScripts(self, proc: ProcT) -> XMLContent:
        autoUpdateWidgets = [
            widget
            for widget in self.iterWidgets(proc)
            if widget.autoUpdate
            ]
        if autoUpdateWidgets:
            yield RefreshScript(*autoUpdateWidgets).present(proc=proc)

    def getParentURL(self, args: Optional[ArgsT]) -> str:
        for ancestor in reversed(self.getPageInfo()['parents']):
            url = self.getPageURL(ancestor, args)
            if url is not None:
                return url
        # In normal situations, the home page will be in the ancestry,
        # so it is unlikely we will ever get here.
        return 'Home'

    def backToParent(self, args: Optional[ArgsT]) -> XMLNode:
        parentName = self.getPageInfo()['parents'][-1]
        parentURL = self.getPageURL(parentName, args)
        return xhtml.p[
            xhtml.a(href = parentURL)[
                'Back to ', self.getPageInfo(parentName)['description']
                ]
            ]

    def backToReferer(self, args: ArgsT) -> XMLNode:
        refererName = args.refererName
        if refererName is None:
            # No referer, fall back to page hierarchy.
            return self.backToParent(args)

        return xhtml.p[
            xhtml.a(href=args.refererURL)[
                'Back to ', self.getPageInfo(refererName)['description']
                ]
            ]

    def backToSelf(self) -> XMLNode:
        url = self.name
        return xhtml.p[ xhtml.a(href = url)[ 'Back to ', self.description ] ]

class _WidgetResponder(Responder):

    def __init__(self, page: FabPage, widget: Widget, proc: PageProcessor):
        Responder.__init__(self)
        self.__page = page
        self.__widget = widget
        self.__proc = proc

    def respond(self, response: Response) -> None:
        self.__page.writeHTTPHeaders(response)
        response.writeXML(self.__widget.present(proc=self.__proc))

class LinkBarButton:
    """The information to present one button in a `LinkBar`."""

    def __init__(self,
                 label: str,
                 url: str,
                 icon: XMLNode,
                 modifier: IconModifier,
                 active: bool
                 ):
        self.label = label
        self.url = url
        self.icon = icon
        self.modifier = modifier
        self.active = active

class LinkBar(Widget):
    '''A bar which contains links to other pages.
    '''

    # These icons are referenced from the style sheet.
    styleRoot.addIcon('IconNew')
    styleRoot.addIcon('IconEdit')
    styleRoot.addIcon('IconDelete')

    __levelSep = xhtml.div(class_ = 'level')[ '\u25B8' ]

    def __presentLinkButton(self, button: LinkBarButton) -> XMLNode:
        active = button.active

        iconModifier = button.modifier
        iconStyle = ['navicon']
        if iconModifier is IconModifier.NEW:
            iconStyle.append('newicon')
        elif iconModifier is IconModifier.EDIT:
            iconStyle.append('editicon' if active else 'newicon')
        elif iconModifier is IconModifier.DELETE:
            iconStyle.append('delicon')
        else:
            assert iconModifier is IconModifier.NONE, iconModifier

        return xhtml.div(class_='navthis' if active else None)[
            xhtml.a(href=button.url)[
                xhtml.span(class_=' '.join(iconStyle))[ button.icon ],
                xhtml.span(class_='navlabel')[ button.label ]
                ]
            ]

    def __presentButtons(self, **kwargs: object) -> XMLContent:
        rootButtons = cast(Sequence[LinkBarButton], kwargs['rootButtons'])
        childButtons = cast(Sequence[LinkBarButton], kwargs['childButtons'])
        levelSep = self.__levelSep

        # Root path.
        for button in rootButtons:
            presentation = self.__presentLinkButton(button)
            isParent = not button.active
            if isParent or childButtons:
                presentation = presentation.addClass('rootpath')
            yield presentation
            if isParent:
                yield levelSep

        # Children.
        if childButtons:
            yield levelSep
            for button in childButtons:
                yield self.__presentLinkButton(button)

    def present(self, **kwargs: object) -> XMLContent:
        return xhtml.div(class_='linkbar')[ self.__presentButtons(**kwargs) ]
