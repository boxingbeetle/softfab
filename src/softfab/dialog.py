# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from typing import (
    Callable, ClassVar, Generic, List, Optional, Sequence, Type, TypeVar, cast
)

from softfab.FabPage import FabPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.formlib import backButton, makeForm, submitButton
from softfab.pageargs import ArgsCorrected, PageArgs, StrArg
from softfab.request import Request
from softfab.userlib import User
from softfab.utils import abstract
from softfab.webgui import PresenterFunction
from softfab.xmlgen import XML, XMLContent, xhtml

DialogProcT = TypeVar('DialogProcT', bound='DialogProcessorBase')
DialogArgsT = TypeVar('DialogArgsT', bound='DialogPage.Arguments')

def _backAndNextButton(backName: Optional[str],
                       nextLabel: Optional[str]
                       ) -> XML:
    back = backButton(name=backName)
    if nextLabel is None:
        return xhtml.p[ back ]
    else:
        # Make the 'next' button appear in the HTML first, so that it
        # becomes the default button of the form.
        return xhtml.p(
            style = 'display: flex; '
                'flex-direction: row-reverse; '
                'justify-content: flex-end'
            )[
            submitButton(value='next', tabindex=3)[ nextLabel ],
            xhtml.span[ '\u00A0' ],
            back
            ]

class VerificationError(Exception):
    '''Raised by `DialogStep.verify` if the data that can be entered in that
    dialog step is incorrect.
    '''

    def __init__(self, message: XMLContent): # pylint: disable=useless-super-delegation
        # https://github.com/PyCQA/pylint/issues/2270
        super().__init__(message)

class DialogStep(ABC, Generic[DialogProcT]):
    name: ClassVar[str] = abstract
    title: ClassVar[str] = abstract

    def __init__(self, page: 'DialogPage'):
        self._page = page
        self._formBodyPresenter = PresenterFunction(self.presentFormBody)

    def process(self, proc: DialogProcT) -> bool: # pylint: disable=unused-argument
        '''Process request. This method is allowed to use the same exceptions
        as Processor.process().
        Page arguments should be used from `proc.args`, not from the request
        object, since corrections may have been done during earlier processing.
        Returns True iff this step should be displayed.
        The default implementation does nothing and returns True.
        '''
        return True

    def presentContent(self, **kwargs: object) -> XMLContent:
        '''Presents this step.
        Is only called if process() returned True.
        The default implementation presents a form.
        '''
        proc = cast(DialogProcT, kwargs['proc'])
        buttons = _backAndNextButton(proc.backName, proc.nextLabel)
        return makeForm(
            formId = 'dialog', action = self._page.name, args = proc.args
            )[
            buttons,
            self._formBodyPresenter,
            buttons
            ].present(**kwargs)

    def presentFormBody(self, **kwargs: object) -> XMLContent: # pylint: disable=unused-argument
        return None

    def verify(self, proc: DialogProcT) -> 'Type[DialogStep]':
        '''Verifies the data the user provided for this step.
        If invalid input is encountered that the user must correct,
        `VerificationError` is raised.
        If invalid input is encountered that has been auto-corrected,
        `ArgsCorrected` is raised.
        Returns the next step in the dialog.
        '''
        raise NotImplementedError

T = TypeVar('T')

class DialogProcessorBase(PageProcessor[DialogArgsT]):
    """Abstract base class for Processors designed to be used with
    `DialogPage`.
    """

    # Tell mypy that our 'page' member is a DialogPage.
    # In theory we should pass the page type as a type argument to
    # PageProcessor, but I can't figure out a way to do that and
    # also keep the knowledge of the argument and processor types.
    page: 'DialogPage' # type: ignore[assignment]

    def __retryStep(self,
                    func: Callable[['DialogProcessorBase'], T]
                    ) -> T:
        # Call function with corrected arguments until it accepts them.
        for _ in range(100):
            try:
                return func(self)
            except ArgsCorrected as ex:
                # Usually ArgsCorrected is handled by a redirect, but POSTs
                # cannot be redirected. Even if it would be possible to
                # redirect them, it would not be useful since the POST body
                # is not accessible for the user, unlike the GET query in
                # the URL.
                self.args = ex.correctedArgs
                self.argsChanged()
        # The function keeps correcting its arguments; by now it is
        # safe to assume it has entered an infinite loop.
        boundObj = getattr(func, '__self__', None)
        if isinstance(boundObj, DialogStep):
            funcDesc = f'"{boundObj.__class__.name}" method'
        else:
            funcDesc = 'function'
        raise RuntimeError(f'dialog step {funcDesc} "{func.__name__}" '
                           f'keeps raising ArgsCorrected')

    def process(self, req: Request, user: User) -> None:
        raise NotImplementedError

    def walkSteps(self,
                  requestedPath: List[DialogStep],
                  limitStep: Optional[DialogStep] = None
                  ) -> None:
        """Walk as far as possible through the steps in `requestedPath`.
        The walk is stopped if a step doesn't pass verification, the walk
        takes us off the requested path, or `limitStep` is reached.
        """
        self.nextLabel = 'Next >' # pylint: disable=attribute-defined-outside-init
        stepObjects = self.page.stepObjects
        actualPath = []
        visibleSteps = []
        errorMessage = None
        step = stepObjects[self.page.steps[0].name]
        try:
            while True:
                # Replay the path the user has followed.
                if requestedPath:
                    nextStep = requestedPath.pop(0)
                    requested = nextStep is step
                    if not requested:
                        # We are deviating from the path the user followed.
                        # Stop trying to follow the rest of it.
                        requestedPath = []
                else:
                    requested = False

                actualPath.append(step.name)

                showStep = self.__retryStep(step.process)
                if showStep:
                    visibleSteps.append(step)
                    if not requested:
                        # We have reached the step that should be presented.
                        break

                # Validate input and determine next step.
                try:
                    nextClass = self.__retryStep(step.verify)
                except VerificationError as ex:
                    errorMessage, = ex.args
                    break
                else:
                    nextStep = stepObjects[nextClass.name]
                if nextStep is limitStep:
                    break
                else:
                    step = nextStep
        finally:
            # Note that not only the "break" statements but also exceptions
            # will go through here, so do not assume too much about the
            # state of the variables.
            if visibleSteps:
                step = visibleSteps[-1]
            while actualPath:
                if actualPath[-1] == step.name:
                    break
                actualPath.pop()
            else:
                actualPath = [ step.name ]
            # pylint: disable=attribute-defined-outside-init
            self.step = step
            self.errorMessage = errorMessage
            self.backName: Optional[str] = (
                'back' if len(visibleSteps) > 1 else None
                )
            self.args = self.args.override(
                path = ' '.join(actualPath), back = None, error = None
                )

    def argsChanged(self) -> None:
        '''Called when the "args" field has been changed.
        Interested subclasses can override this, for example to discard
        cached objects that were created based on information from "args".
        The default implementation does nothing.
        '''

class InitialDialogProcessor(DialogProcessorBase[DialogArgsT]):
    """Processor that loads the initial state for `DialogPage`.

    TODO: It would be cleaner to restart processing with the new
          arguments, via an internal redirect to the POST page.
    """

    def getInitial(self, args: PageArgs, user: User) -> DialogArgsT:
        '''Called when the dialog is entered, to determine the first step
        and the initial argument values.
        '''
        raise NotImplementedError

    def process(self, req: Request, user: User) -> None:
        initialArgs = self.getInitial(self.args, user)
        self.args = initialArgs
        stepObjects = self.page.stepObjects
        self.walkSteps([stepObjects[name] for name in initialArgs.path.split()])

class ContinuedDialogProcessor(DialogProcessorBase[DialogArgsT]):
    """Processor handles the state for subsequent steps of `DialogPage`.
    """

    def process(self, req: Request, user: User) -> None:
        # Determine navigation path.
        stepObjects = self.page.stepObjects
        requestedPath = []
        for name in self.args.path.split():
            try:
                requestedPath.append(stepObjects[name])
            except KeyError as ex:
                raise InvalidRequest(
                    f'non-existing dialog step "{name}" in navigation path'
                    ) from ex
        if not requestedPath:
            raise InvalidRequest('Dialog state was lost')

        if self.args.error is not None:
            # User pressed back button on error page.
            self.walkSteps(requestedPath[:-1])
        elif self.args.back is not None:
            # User pressed back button on normal page.
            # We must go back to the previous step that will be shown;
            # we can't just go back two steps, since we might end up on
            # a non-shown step and then automatically advance to the same
            # step the user pressed the back button on.
            self.walkSteps(requestedPath, requestedPath[-1])
        else:
            self.walkSteps(requestedPath)

class DialogPage(FabPage[DialogProcessorBase, 'DialogPage.Arguments'], ABC):
    description: ClassVar[str] = abstract
    icon: ClassVar[str] = abstract

    steps: ClassVar[Sequence[Type[DialogStep]]] = abstract

    class Arguments(PageArgs):
        path = StrArg('')
        back = StrArg(None) # back button on normal page
        error = StrArg(None) # back button on error page

    def __init__(self) -> None:
        FabPage.__init__(self)
        self.stepObjects = {
            stepClass.name: stepClass(self)
            for stepClass in self.steps
            }

    def checkAccess(self, user: User) -> None:
        # This method is already declared abstract in FabPage, we re-assert
        # that here to please PyLint.
        raise NotImplementedError

    def pageTitle(self, proc: DialogProcessorBase) -> str:
        # TODO: When presenting an error page, 'proc' is of a different type
        #       that does not have the 'step' attribute.
        #       We should probably split the title from the subtitle and
        #       pass 'proc' only to the subtitle method.
        step = getattr(proc, 'step', None)
        if step is None:
            return self.description
        else:
            return self.description + ' \u2013 ' + proc.step.title

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(DialogProcessorBase, kwargs['proc'])
        if proc.errorMessage is not None:
            yield xhtml.p(class_ = 'notice')[ proc.errorMessage ]
        yield proc.step.presentContent(**kwargs)
