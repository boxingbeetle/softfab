# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from enum import Enum
from typing import (
    TYPE_CHECKING, ClassVar, Generic, Mapping, Optional, TypeVar, Union, cast
)

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import (
    InternalError, InvalidRequest, PageProcessor, PresentableError, Redirect
)
from softfab.databaselib import Database, Record
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

class EditArgs(PageArgs):
    id = StrArg('')
    newId = StrArg('')
    prev = EnumArg(EditPagePrev, None)
    #action = EnumArg(EditPageActions, None)
    action = StrArg(None)
    back = StrArg(None)

EditArgsT = TypeVar('EditArgsT', bound='EditArgs')
EditProcT = TypeVar('EditProcT', bound='EditProcessorBase')

class AbstractPhase(Generic[EditProcT]):
    '''Note: This class is similar to DialogStep, but I don't know yet if/how
    that similarity can be exploited.
    '''

    def __init__(self, page: 'EditPage'):
        self.page = page

    def process(self, proc: EditProcT) -> None:
        '''Process request. This method is allowed to use the same exceptions
        as Processor.process().
        The default implementation does nothing.
        '''

    def presentContent(self, proc: EditProcT) -> XMLContent:
        '''Presents this phase.
        '''
        raise NotImplementedError

class EditPhase(AbstractPhase):
    '''First and main phase: actual editing of the record.
    '''

    def presentContent(self, proc: EditProcT) -> XMLContent:
        page = self.page

        buttons = ['save']
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
            ].present(proc=proc)

class SavePhase(AbstractPhase['EditProcessor[EditArgsT, Record]']):
    '''Commit edited element to the database.
    '''

    def process(self, proc: 'EditProcessor[EditArgsT, Record]') -> None:
        page = self.page
        args = proc.args
        oldElement = proc.oldElement

        # TODO: All of these argument are taken from 'proc', do we really
        #       need to pass them?
        element = proc.createElement(args.newId, args, oldElement)

        if proc.replace:
            try:
                existingElement = page.db[args.newId]
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
            proc: EditProcT, # pylint: disable=unused-argument
            element: Record
            ) -> None:
        self.page.db.add(element)

    def updateRecord(self,
            proc: EditProcT, # pylint: disable=unused-argument
            element: Record
            ) -> None:
        self.page.db.update(element)

    def presentContent(self,
                       proc: 'EditProcessor[EditArgsT, Record]'
                       ) -> XMLContent:
        page = self.page
        if page.autoName:
            elementId = None
        else:
            elementId = ' ' + xhtml.b[ proc.args.newId ]
        return (
            xhtml.p[
                'Changes to ', page.elemName, elementId, ' have been committed.'
                ],
            page.backToParent(proc.req)
            )

class SaveAsPhase(AbstractPhase):
    '''Ask for a name for the record.
    '''

    def presentContent(self, proc: EditProcT) -> XMLContent:
        page = self.page
        args = proc.args
        yield xhtml.h2[ 'Save As' ]
        yield xhtml.p[ 'Please enter a name for ', page.elemName, ':' ]
        yield makeForm(args = args.override(prev = EditPagePrev.SAVE_AS))[
            xhtml.p[ textInput(name = 'newId', size = 40) ],
            xhtml.p[ actionButtons('save', 'cancel') ],
            ].present(proc=proc)

class ConfirmOverwritePhase(AbstractPhase):
    '''Asks the user for confirmation before overwriting an existing record.
    '''

    def presentContent(self, proc: EditProcT) -> XMLContent:
        page = self.page
        args = proc.args
        yield xhtml.p[
            'A ', page.elemName, ' named ', xhtml.b[ args.newId ],
            ' already exists.'
            ]
        yield xhtml.p[ 'Do you want to ', xhtml.b[ 'overwrite' ], ' it?' ]
        yield makeForm(args = args.override(prev = EditPagePrev.CONFIRM))[
            xhtml.p[ actionButtons('save', 'cancel') ]
            ].present(proc=proc)

class EditProcessorBase(PageProcessor[EditArgsT], Generic[EditArgsT, Record]):

    if TYPE_CHECKING:
        page = cast('EditPage', None) # type: ignore

    def process(self, req: Request, user: User) -> None:
        # pylint: disable=attribute-defined-outside-init
        checkPrivilege(user, self.page.db.privilegeObject + '/a')

        # Process "id" argument.
        # This is not editable, so if we reject it, there is nothing
        # to go back to.
        self.showBackButton = False

        # Determine record ID.
        autoName = self.page.autoName
        if autoName:
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

    def processState(self, oldElement: Optional[Record]) -> None:
        """Load or verify the element's state.
        """
        raise NotImplementedError

    def determinePhase(self, req: Request) -> AbstractPhase:
        raise NotImplementedError

    def _validateState(self) -> None:
        '''Perform minor changes on arguments to make them valid,
        such as inserting default values for empty entries.
        '''

class EditProcessor(EditProcessorBase[EditArgsT, Record]):

    def processState(self, oldElement: Optional[Record]) -> None:
        # Initialize args on first arrival to the edit page.
        # TODO: It would be cleaner if we could separate the data
        #       being edited from the control flow fields that EditPage
        #       needs. For example, we could avoid calls to _initArgs
        #       when the user selects 'Cancel'. Currently ProjectEdit
        #       has to be able to deal with element == None in its
        #       _initArgs, even though project is a singleton.
        #       -> maybe this is fixed now?
        if self.args.action is None:
            self.args = self.args.override(
                action = 'edit',
                **self._initArgs(oldElement)
                )

        if self.args.action not in ('edit', 'cancel'):
            try:
                self._checkState()
            except PresentableError:
                self.args = self.args.override(action = 'edit')
                raise

    def determinePhase(self, req: Request) -> AbstractPhase:
        # pylint: disable=attribute-defined-outside-init
        page = self.page
        args = self.args
        action, prev = args.action, args.prev
        # In IE, if a form with two submit buttons is submitted by pressing
        # the Enter key, neither button is considered successful.
        # In this case, perform the default action for that page.
        if action == '':
            if prev is EditPagePrev.SAVE_AS:
                action = 'save'
            elif prev is EditPagePrev.EDIT:
                action = 'edit'
            else:
                raise ValueError(prev)

        if action == 'cancel':
            if prev is EditPagePrev.EDIT:
                raise Redirect(page.getParentURL(req))
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
                      oldElement: Optional[Record]
                      ) -> Record:
        raise NotImplementedError

    def _initArgs(self, element: Optional[Record]) -> Mapping[str, object]:
        '''Get initial argument values for editing the given record.
        If the user is creating a new record, None is passed.
        Returns a dictionary containing argument names and values
        for those arguments that need to be overridden from their
        defaults.
        '''
        raise NotImplementedError

    def _checkState(self) -> None:
        '''Checks whether the arguments contain only valid values and
        whether they are consistent with the current contents of the
        database. For example, all references to other records should
        be checked.
        Raises PresentableError if there is a problem.
        '''

class EditPage(FabPage[EditProcessor[EditArgsT, Record], EditArgsT], ABC):
    description = abstract # type: ClassVar[str]
    icon = abstract # type: ClassVar[str]
    iconModifier = IconModifier.EDIT

    # TODO: It seems 'record' and 'element' are used for the same thing.
    #       Pick one term and stick with it.
    elemTitle = abstract # type: ClassVar[str]
    elemName = abstract # type: ClassVar[str]
    db = abstract # type: ClassVar[Database]
    privDenyText = abstract # type: ClassVar[str]
    useScript = abstract # type: ClassVar[bool]
    formId = abstract # type: ClassVar[str]
    # Possible values for "autoName":
    # TODO: Can we simplify this? Maybe bool whether user can name the record;
    #       if False a method to provide the ID.
    # None: user must name the record
    # False: record already has been named, this name cannot be changed
    # non-empty string: record has a fixed name, which is this string
    autoName = abstract # type: ClassVar[Union[None, bool, str]]

    def checkAccess(self, user: User) -> None:
        # Access will be checked later by Processor.
        pass

    def getFormContent(self,
                       proc: EditProcessorBase[EditArgsT, Record]
                       ) -> XMLContent:
        """Returns the text and controls contained in the form.
        It will be presented later as part of the form presentation.
        """
        raise NotImplementedError

    def __init__(self) -> None:
        FabPage.__init__(self)
        self.editPhase = EditPhase(self)
        self.savePhase = SavePhase[EditArgsT, Record](self)
        self.saveAsPhase = SaveAsPhase(self)
        self.confirmOverwritePhase = ConfirmOverwritePhase(self)

    def pageTitle(self, proc: EditProcessor[EditArgsT, Record]) -> str:
        return 'Edit ' + self.elemTitle

    def presentHeadParts(self,
                         proc: EditProcessor[EditArgsT, Record]
                         ) -> XMLContent:
        yield super().presentHeadParts(proc)
        if self.useScript:
            yield rowManagerScript.present(proc=proc)

    def presentContent(self,
                       proc: EditProcessorBase[EditArgsT, Record]
                       ) -> XMLContent:
        return proc.phase.presentContent(proc)

    def presentError(self,
                     proc: EditProcessor[EditArgsT, Record],
                     message: XML
                     ) -> XMLContent:
        yield message
        if proc.showBackButton:
            yield makeForm(args = proc.args)[
                xhtml.p[ backButton(name = 'back') ]
                ].present(proc=proc)
