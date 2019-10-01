# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from enum import Enum
from typing import (
    TYPE_CHECKING, ClassVar, Generic, Mapping, Optional, Type, TypeVar, Union,
    cast
)

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import (
    InternalError, InvalidRequest, PageProcessor, PresentableError, Redirect
)
from softfab.databaselib import DBRecord, Database
from softfab.formlib import actionButtons, backButton, makeForm, textInput
from softfab.pageargs import EnumArg, PageArgs, StrArg
from softfab.request import Request
from softfab.userlib import User, checkPrivilege, checkPrivilegeForOwned
from softfab.utils import abstract
from softfab.webgui import preserveSpaces, rowManagerScript
from softfab.xmlgen import XML, XMLContent, xhtml

# TODO: Is having this as an enum really an advantage?
#       It makes it harder for subclasses to add actions;
#       is that something we want to encourage or discourage?
#EditPageActions = Enum('EditPageActions', 'EDIT SAVE SAVE_AS CANCEL')
#"""Values used on submit buttons."""

EditPagePrev = Enum('EditPagePrev', 'CONFIRM SAVE_AS EDIT')
"""Names for the previous dialog step."""

class InitialEditArgs(PageArgs):
    id = StrArg('')

class EditArgs(InitialEditArgs):
    newId = StrArg('')
    prev = EnumArg(EditPagePrev, None)
    #action = EnumArg(EditPageActions, None)
    action = StrArg(None)
    back = StrArg(None)

InitialEditArgsT = TypeVar('InitialEditArgsT', bound='InitialEditArgs')
EditArgsT = TypeVar('EditArgsT', bound='EditArgs')
EditProcT = TypeVar('EditProcT', bound='EditProcessorBase', contravariant=True)

class AbstractPhase(Generic[EditProcT, EditArgsT, DBRecord]):
    '''Note: This class is similar to DialogStep, but I don't know yet if/how
    that similarity can be exploited.
    '''

    def __init__(self, page: 'EditPage[EditArgsT, DBRecord]'):
        self.page = page

    def process(self, proc: EditProcT) -> None:
        '''Process request. This method is allowed to use the same exceptions
        as Processor.process().
        The default implementation does nothing.
        '''

    def presentContent(self, **kwargs: object) -> XMLContent:
        '''Presents this phase.
        '''
        raise NotImplementedError

class EditPhase(AbstractPhase['EditProcessorBase[EditArgsT, DBRecord]',
                              EditArgsT, DBRecord],
                Generic[EditArgsT, DBRecord]):
    '''First and main phase: actual editing of the record.
    '''

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(EditProcessorBase[EditArgsT, DBRecord], kwargs['proc'])
        page = self.page

        buttons = []
        if not page.isNew(proc.args):
            buttons.append('save')
        if page.autoName is None:
            buttons.append('save_as')
        buttons.append('cancel')

        yield makeForm(
            formId = page.formId,
            args = proc.args.override(
                prev = EditPagePrev.EDIT, newId = proc.args.id
                )
            )[
            page.getFormContent(proc),
            xhtml.p[ actionButtons(*buttons) ]
            ].present(**kwargs)

class SavePhase(AbstractPhase['EditProcessor[EditArgsT, DBRecord]',
                              EditArgsT, DBRecord],
                Generic[EditArgsT, DBRecord]):
    '''Commit edited element to the database.
    '''

    def process(self, proc: 'EditProcessor[EditArgsT, DBRecord]') -> None:
        page = self.page
        args = proc.args
        oldElement = proc.oldElement

        # TODO: All of these argument are taken from 'proc', do we really
        #       need to pass them?
        element = proc.createElement(args.newId, args, oldElement)

        if proc.replace:
            try:
                existingElement: Optional[DBRecord] = page.db[args.newId]
            except KeyError:
                # Record is no longer in DB; create instead of replace.
                existingElement = None
        else:
            existingElement = None

        if existingElement is None:
            checkPrivilege(
                proc.user,
                page.db.privilegeObject + '/c', 'create ' + page.privDenyText
                )
            self.addRecord(proc, element)
        else:
            checkPrivilegeForOwned(
                proc.user,
                page.db.privilegeObject + '/m',
                existingElement,
                ( 'modify this ' + page.elemName,
                  'modify ' + page.privDenyText )
                )
            self.updateRecord(proc, element)

    def addRecord(self,
            proc: 'EditProcessor[EditArgsT, DBRecord]', # pylint: disable=unused-argument
            element: DBRecord
            ) -> None:
        self.page.db.add(element)

    def updateRecord(self,
            proc: 'EditProcessor[EditArgsT, DBRecord]', # pylint: disable=unused-argument
            element: DBRecord
            ) -> None:
        self.page.db.update(element)

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(EditProcessor[EditArgsT, DBRecord], kwargs['proc'])
        page = self.page
        if page.autoName:
            elementId = None
        else:
            elementId = ' ' + xhtml.b[ proc.args.newId ]
        return (
            xhtml.p[
                'Changes to ', page.elemName, elementId, ' have been committed.'
                ],
            page.backToParent(proc.args)
            )

class SaveAsPhase(AbstractPhase['EditProcessor[EditArgsT, DBRecord]',
                                EditArgsT, DBRecord],
                  Generic[EditArgsT, DBRecord]):
    '''Ask for a name for the record.
    '''

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(EditProcessor[EditArgsT, DBRecord], kwargs['proc'])
        page = self.page
        args = proc.args
        yield xhtml.h2[ 'Save As' ]
        yield xhtml.p[ 'Please enter a name for ', page.elemName, ':' ]
        yield makeForm(args = args.override(prev = EditPagePrev.SAVE_AS))[
            xhtml.p[ textInput(name = 'newId', size = 40) ],
            xhtml.p[ actionButtons('save', 'cancel') ],
            ].present(**kwargs)

class ConfirmOverwritePhase(AbstractPhase['EditProcessor[EditArgsT, DBRecord]',
                                          EditArgsT, DBRecord],
                            Generic[EditArgsT, DBRecord]):
    '''Asks the user for confirmation before overwriting an existing record.
    '''

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(EditProcessor[EditArgsT, DBRecord], kwargs['proc'])
        page = self.page
        args = proc.args
        yield xhtml.p[
            'A ', page.elemName, ' named ', xhtml.b[ args.newId ],
            ' already exists.'
            ]
        yield xhtml.p[ 'Do you want to ', xhtml.b[ 'overwrite' ], ' it?' ]
        yield makeForm(args = args.override(prev = EditPagePrev.CONFIRM))[
            xhtml.p[ actionButtons('save', 'cancel') ]
            ].present(**kwargs)

class EditProcessorBase(PageProcessor[EditArgsT], Generic[EditArgsT, DBRecord]):

    if TYPE_CHECKING:
        @property
        def page(self # type: ignore[override]
                 ) -> 'EditPage[EditArgsT, DBRecord]':
            ...

    def process(self, req: Request[EditArgsT], user: User) -> None:
        # pylint: disable=attribute-defined-outside-init
        checkPrivilege(user, self.page.db.privilegeObject + '/a')

        # Process "id" argument.
        # This is not editable, so if we reject it, there is nothing
        # to go back to.
        self.showBackButton = False

        # Determine record ID.
        autoName = self.page.autoName
        if autoName:
            assert isinstance(autoName, str), autoName
            recordId = autoName
            if self.args.id:
                raise InvalidRequest('Value provided for fixed ID')
        else:
            recordId = self.args.id
            if autoName is False and not recordId:
                raise InvalidRequest('Missing ID')

        # Try to find existing record.
        oldElement = self.page.db.get(recordId) if recordId else None
        self.oldElement = oldElement

        # State-dependent processing.
        self.showBackButton = True
        self.processState(oldElement)
        # TODO: Redesign state checking and validation?
        # There seem to be two uses of validateState currently:
        # - converting from user friendly values like NONE_TEXT to
        #   implementation friendly values like None and ''
        # - silently removing errors which should actually be reported to
        #   the user: silent removal is OK if it doesn't change the meaning
        #   in any significant way, but in current cases it does
        # Idea: perform validateState before checkState.
        self._validateState()

        self.phase = self.determinePhase(req)
        self.phase.process(self)

    def processState(self, oldElement: Optional[DBRecord]) -> None:
        """Load or verify the element's state.
        """
        raise NotImplementedError

    def determinePhase(self: EditProcT,
                       req: Request[EditArgsT]
                       ) -> AbstractPhase[EditProcT, EditArgsT, DBRecord]:
        raise NotImplementedError

    def _validateState(self) -> None:
        '''Perform minor changes on arguments to make them valid,
        such as inserting default values for empty entries.
        '''

class InitialEditProcessor(EditProcessorBase[EditArgsT, DBRecord]):

    argsClass: ClassVar[Type[EditArgsT]] = abstract
    """The argument class used for editing: a subclass of `EditArgs`,
    that contains all the values needed to construct a record.
    """

    def processState(self, oldElement: Optional[DBRecord]) -> None:
        recordId = self.args.id # pylint: disable=access-member-before-definition
        editArgs = self.argsClass(action='edit', id=recordId,
                                  **self._initArgs(oldElement))
        # TODO: An internal redirect to the POST page would be cleaner
        #       than overwriting the args, but that doesn't fit into
        #       the way pages are currently processed.
        self.args = editArgs # pylint: disable=attribute-defined-outside-init

    def determinePhase(self,
                       req: Request[InitialEditArgsT]
                       ) -> EditPhase[EditArgsT, DBRecord]:
        return self.page.editPhase

    def _initArgs(self, element: Optional[DBRecord]) -> Mapping[str, object]:
        '''Get initial argument values for editing the given record.
        If the user is creating a new record, None is passed.
        Returns a dictionary containing argument names and values
        for those arguments that need to be overridden from their
        defaults.
        '''
        raise NotImplementedError

class EditProcessor(EditProcessorBase[EditArgsT, DBRecord]):

    if TYPE_CHECKING:
        replace = True

    def processState(self, oldElement: Optional[DBRecord]) -> None:
        if self.args.action not in ('edit', 'cancel'):
            try:
                self._checkState()
            except PresentableError:
                # pylint: disable=attribute-defined-outside-init
                self.args = self.args.override(action='edit')
                raise

    def determinePhase(self,
                       req: Request[EditArgsT]
                       ) -> AbstractPhase['EditProcessor[EditArgsT, DBRecord]',
                                          EditArgsT, DBRecord]:
        # pylint: disable=attribute-defined-outside-init
        page = self.page
        args = self.args
        action, prev = args.action, args.prev
        # In IE, if a form with two submit buttons is submitted by pressing
        # the Enter key, neither button is considered successful.
        # In this case, perform the default action for that page.
        if not action:
            if prev is EditPagePrev.SAVE_AS:
                action = 'save'
            elif prev is EditPagePrev.EDIT:
                action = 'edit'
            else:
                raise ValueError(prev)

        if action == 'cancel':
            if prev is EditPagePrev.EDIT:
                raise Redirect(page.getParentURL(req.args))
            elif prev is EditPagePrev.SAVE_AS:
                return page.editPhase
            elif prev is EditPagePrev.CONFIRM:
                return page.saveAsPhase
            else:
                raise ValueError(prev)
        elif action == 'save':
            if prev is EditPagePrev.SAVE_AS:
                if page.autoName is None:
                    # Save under new and unconfirmed name.
                    self.__checkId()
                    # Is there already a record with this name?
                    if page.db.get(args.newId) is None:
                        self.replace = False
                        return page.savePhase
                    else:
                        return page.confirmOverwritePhase
                else:
                    # There is probaly a custom '_updateRecord()'
                    self.replace = True
                    return page.savePhase
            elif args.newId == '':
                # If never saved before, use autoName or redirect to "Save
                # As".
                if page.autoName is None:
                    return page.saveAsPhase
                elif page.autoName:
                    self.args = args.override(newId = page.autoName)
                    self.replace = True
                    return page.savePhase
                elif page.autoName is False:
                    raise InvalidRequest('Missing ID')
                else:
                    raise InternalError('Bad value for "autoName"')
            else:
                self.replace = True
                # Save under the old or confirmed new name.
                return page.savePhase
        elif action == 'save_as':
            return page.saveAsPhase
        elif action == 'edit':
            return page.editPhase
        else:
            raise ValueError(action)

    def __checkId(self) -> None:
        args = self.args
        try:
            self.checkId(args.newId)
        except KeyError as ex:
            # pylint: disable=attribute-defined-outside-init
            self.args = args.override(
                prev = EditPagePrev.EDIT, action = 'save_as'
                )
            raise PresentableError(xhtml[
                xhtml.p[
                    'The ', self.page.elemName, ' name "',
                    preserveSpaces(args.newId),
                    '" is invalid: ', xhtml.b[ str(ex.args[0]) ], '.'
                    ],
                xhtml.p[ 'Please correct the name.' ]
                ])

    def checkId(self, recordId: str) -> None:
        '''Check whether the name is valid for saving a record under.
        Raises KeyError with a descriptive message if the name is invalid.
        The default implementation defers to `page.db`.
        '''
        self.page.db.checkId(recordId)

    def createElement(self,
                      recordId: str,
                      args: EditArgsT,
                      oldElement: Optional[DBRecord]
                      ) -> DBRecord:
        raise NotImplementedError

    def _checkState(self) -> None:
        '''Checks whether the arguments contain only valid values and
        whether they are consistent with the current contents of the
        database. For example, all references to other records should
        be checked.
        Raises PresentableError if there is a problem.
        '''

class EditPage(FabPage[EditProcessorBase[EditArgsT, DBRecord], EditArgsT], ABC):
    description: ClassVar[str] = abstract
    icon: ClassVar[str] = abstract
    iconModifier = IconModifier.NEW

    # TODO: It seems 'record' and 'element' are used for the same thing.
    #       Pick one term and stick with it.
    elemTitle: ClassVar[str] = abstract
    elemName: ClassVar[str] = abstract
    db: Database[DBRecord] = abstract
    privDenyText: ClassVar[str] = abstract
    useScript: ClassVar[bool] = abstract
    formId: ClassVar[str] = abstract
    # Possible values for "autoName":
    # TODO: Can we simplify this? Maybe bool whether user can name the record;
    #       if False a method to provide the ID.
    # None: user must name the record
    # False: record already has been named, this name cannot be changed
    # non-empty string: record has a fixed name, which is this string
    autoName: ClassVar[Union[None, bool, str]] = abstract

    def checkAccess(self, user: User) -> None:
        # Access will be checked later by Processor.
        pass

    def getFormContent(self,
                       proc: EditProcessorBase[EditArgsT, DBRecord]
                       ) -> XMLContent:
        """Returns the text and controls contained in the form.
        It will be presented later as part of the form presentation.
        """
        raise NotImplementedError

    def __init__(self) -> None:
        FabPage.__init__(self)
        self.editPhase = EditPhase[EditArgsT, DBRecord](self)
        self.savePhase = SavePhase[EditArgsT, DBRecord](self)
        self.saveAsPhase = SaveAsPhase[EditArgsT, DBRecord](self)
        self.confirmOverwritePhase = \
                ConfirmOverwritePhase[EditArgsT, DBRecord](self)

    def pageTitle(self, proc: EditProcessorBase[EditArgsT, DBRecord]) -> str:
        return self.activeDescription(proc.args)

    def isNew(self, args: Optional[EditArgsT]) -> bool:
        return args is None or (self.autoName is None and not args.id)

    def activeDescription(self, args: Optional[EditArgsT]) -> str:
        if self.isNew(args):
            return 'New ' + self.elemTitle
        else:
            return 'Edit ' + self.elemTitle

    def activeIconModifier(self, args: Optional[EditArgsT]) -> IconModifier:
        return IconModifier.NEW if self.isNew(args) else IconModifier.EDIT

    def presentHeadParts(self, **kwargs: object) -> XMLContent:
        yield super().presentHeadParts(**kwargs)
        if self.useScript:
            yield rowManagerScript.present(**kwargs)

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(EditProcessorBase[EditArgsT, DBRecord], kwargs['proc'])
        return proc.phase.presentContent(**kwargs)

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        proc = cast(EditProcessorBase[EditArgsT, DBRecord], kwargs['proc'])
        yield message
        if proc.showBackButton:
            yield makeForm(args = proc.args)[
                xhtml.p[ backButton(name = 'back') ]
                ].present(**kwargs)
