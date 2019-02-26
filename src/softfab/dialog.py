# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from typing import ClassVar, Sequence, Type

from softfab.FabPage import FabPage
from softfab.Page import InvalidRequest, PageProcessor, PresentableError
from softfab.formlib import backButton, makeForm, submitButton
from softfab.pageargs import ArgsCorrected, PageArgs, StrArg
from softfab.utils import abstract
from softfab.webgui import PresenterFunction
from softfab.xmlgen import xhtml

def _backAndNextButton(backName, nextLabel):
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

class DialogStep(ABC):
    name = abstract # type: ClassVar[str]
    title = abstract # type: ClassVar[str]

    def __init__(self, page):
        self._page = page
        self._formBodyPresenter = PresenterFunction(self.presentFormBody)

    def backToParent(self, req):
        return self._page.backToParent(req)

    def process(self, proc): # pylint: disable=unused-argument
        '''Process request. This method is allowed to use the same exceptions
        as Processor.process().
        Page arguments should be used from `proc.args`, not from the request
        object, since corrections may have been done during earlier processing.
        Returns True iff this step should be displayed.
        The default implementation does nothing and returns True.
        '''
        return True

    def presentContent(self, proc):
        '''Presents this step.
        Is only called if process() returned True.
        The default implementation presents a form.
        '''
        buttons = _backAndNextButton(proc.backName, proc.nextLabel)
        return makeForm(
            formId = 'dialog', action = self._page.name, args = proc.args
            )[
            buttons,
            self._formBodyPresenter,
            buttons
            ].present(proc=proc)

    def presentFormBody(self, **kwargs): # pylint: disable=unused-argument
        return None

    def verify(self, proc):
        '''Verifies the data the user provided for this step.
        If invalid input is encountered that the user must correct,
        PresentableError is raised.
        If invalid input is encountered that has been auto-corrected,
        ArgsCorrected is raised.
        Returns the next step in the dialog.
        '''
        raise NotImplementedError

class DialogPage(FabPage, ABC):
    description = abstract # type: ClassVar[str]
    icon = abstract # type: ClassVar[str]

    steps = abstract # type: ClassVar[Sequence[Type[DialogStep]]]

    class Arguments(PageArgs):
        path = StrArg('')
        back = StrArg(None) # back button on normal page
        error = StrArg(None) # back button on error page

    class Processor(PageProcessor):

        def __retryStep(self, func):
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
            raise RuntimeError(
                'dialog step "%s" method "%s" keeps raising ArgsCorrected'
                % ( func.__self__.__class__.name, func.__name__ )
                )

        def process(self, req):
            args = self.args

            # Determine navigation path.
            stepObjects = self.page._stepObjects # pylint: disable=protected-access
            requestedPath = []
            for name in args.path.split():
                try:
                    requestedPath.append(stepObjects[name])
                except KeyError:
                    raise InvalidRequest(
                        'non-existing dialog step "%s" in navigation path'
                        % name
                        )
            if requestedPath:
                step = requestedPath[0]
            else:
                initialClass, initialArgs = self.getInitial(req)
                step = stepObjects[initialClass.name]
                self.args = args = initialArgs

            limitStep = None
            if args.error is not None:
                # User pressed back button on error page.
                requestedPath[-1 : ] = []
            elif args.back is not None:
                # User pressed back button on normal page.
                # We must go back to the previous step that will be shown;
                # we can't just go back two steps, since we might end up on
                # a non-shown step and then automatically advance to the same
                # step the user pressed the back button on.
                limitStep = requestedPath[-1]

            actualPath = []
            visibleSteps = []
            errorMessage = None
            self.nextLabel = 'Next >' # pylint: disable=attribute-defined-outside-init
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
                    except PresentableError as ex:
                        errorMessage = str(ex)
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
                self.backName = 'back' if len(visibleSteps) > 1 else None
                self.args = self.args.override(
                    path = ' '.join(actualPath), back = None, error = None
                    )

        def argsChanged(self):
            '''Called when the "args" field has been changed.
            Interested subclasses can override this, for example to discard
            cached objects that were created based on information from "args".
            The default implementation does nothing.
            '''

        def getInitial(self, req):
            '''Called when the dialog is entered, to determine the first step
            and the initial argument values.
            Returns a pair consisting of the DialogStep object for the initial
            step and a PageArgs instance.
            '''
            raise NotImplementedError

    def __init__(self):
        FabPage.__init__(self)
        self._stepObjects = dict(
            ( stepClass.name, stepClass(self) )
            for stepClass in self.steps
            )

    def checkAccess(self, req):
        # This method is already declared abstract in FabPage, we re-assert
        # that here to please PyLint.
        raise NotImplementedError

    def fabTitle(self, proc):
        return self.description + ' - ' + proc.step.title

    def presentContent(self, proc):
        if proc.errorMessage is not None:
            yield xhtml.p(class_ = 'notice')[ proc.errorMessage ]
        yield proc.step.presentContent(proc)
