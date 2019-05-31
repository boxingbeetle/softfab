# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import Callable, ClassVar, Generic, cast

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.databaselib import DBRecord, Database
from softfab.formlib import actionButtons, makeForm
from softfab.pageargs import EnumArg, PageArgs, StrArg
from softfab.request import Request
from softfab.typing import Collection
from softfab.userlib import User, checkPrivilegeForOwned
from softfab.utils import abstract, pluralize
from softfab.webgui import unorderedList
from softfab.xmlgen import XML, XMLContent, xhtml


class RecordInUseError(Exception):

    def __init__(self,
                 refererName: str,
                 presenter: Callable[[str], XMLContent],
                 referers: Collection[str]):
        Exception.__init__(self, 'record in use')
        self.refererName = refererName
        self.presenter = presenter
        self.referers = referers

class DeleteArgs(PageArgs):
    id = StrArg()

Actions = Enum('Actions', 'DELETE CANCEL')

def fetchRecordForDeletion(recordId: str,
                           page: 'RecordDelete_GET[DBRecord]'
                           ) -> DBRecord:
    '''Tries to fetch the record with the given ID.
    Raises PresentableError if the record does not exist or can currently
    not be deleted.
    '''
    try:
        record = page.db[recordId]
    except KeyError:
        raise PresentableError(xhtml.p[
            'Cannot delete ', page.recordName, ' ', xhtml.b[ recordId ],
            ' because it does not exist (anymore).'
            ])

    try:
        page.checkState(record)
    except RecordInUseError as ex:
        raise PresentableError(xhtml.p[
            'Cannot delete ', page.recordName, ' ', xhtml.b[ recordId ],
            ' because it is used in the following ',
            pluralize(ex.refererName, ex.referers), ':'
            ] + unorderedList[(
                ex.presenter(referer) for referer in sorted(ex.referers)
                )].present()
            )

    return record

class RecordDelete_GET(FabPage['RecordDelete_GET.Processor',
                               'RecordDelete_GET.Arguments'],
                       Generic[DBRecord]):
    """Reusable implementation for handling a GET of a "delete record" dialog.
    Inherit from RecordDelete_GET and define the following fields:
        db = database to delete record from
        recordName = name under which user knows this record type
        denyText = text that appears in the 'access denied' message
    You can define these at class scope (since they are constants).
    """
    db = abstract # type: Database[DBRecord]
    recordName = abstract # type: ClassVar[str]
    denyText = abstract # type: ClassVar[str]

    description = abstract
    linkDescription = False
    icon = abstract
    iconModifier = IconModifier.DELETE

    class Arguments(DeleteArgs):
        pass

    class Processor(PageProcessor[DeleteArgs]):
        def process(self, req: Request[DeleteArgs], user: User) -> None:
            page = cast(RecordDelete_GET, self.page)
            fetchRecordForDeletion(req.args.id, page)

    def pageTitle(self, proc: Processor) -> str:
        return 'Delete ' + ' '.join(
            word.capitalize() for word in self.recordName.split()
            )

    def checkAccess(self, user: User) -> None:
        pass

    def getCancelURL(self, req: Request[DeleteArgs]) -> str:
        '''URL to redirect to when the user chooses "Cancel".
        By default this is the active referer with a fallback to the parent
        page, but subclasses can override this.
        '''
        return req.args.refererURL or self.getParentURL(req)

    def presentContent(self, proc: Processor) -> XMLContent:
        yield xhtml.p[
            'Delete ', self.recordName, ' ', xhtml.b[ proc.args.id ], '?'
            ]
        yield makeForm(args = proc.args)[
            xhtml.p[ actionButtons(Actions) ]
            ].present(proc=proc)

    def presentError(self, proc: Processor, message: XML) -> XMLContent:
        yield message
        yield self.backToReferer(proc.req)

    def checkState(self, record: DBRecord) -> None:
        '''Checks whether the given record can be deleted.
        It is possible deletion is not allowed if other records depend on it.
        If deletion is allowed, do nothing, otherwise raise PresentableError
        or RecordInUseError.
        The default implementation does nothing.
        '''

class RecordDelete_POSTMixin:
    """Mixin for implementing the POST handling of a "delete record" dialog.
    Subclasses are expected to inherit from this mixin and the GET page.
    """

    class ArgumentsMixin:
        action = EnumArg(Actions)

    class ProcessorMixin:
        def process(self, req: Request, user: User) -> None:
            page = cast(RecordDelete_GET, getattr(self, 'page'))
            action = req.args.action
            if action is not Actions.DELETE:
                assert action is Actions.CANCEL, action
                raise Redirect(page.getCancelURL(req))

            record = fetchRecordForDeletion(req.args.id, page)
            checkPrivilegeForOwned(
                user,
                page.db.privilegeObject + '/d',
                record,
                ( 'delete this ' + page.recordName,
                    'delete ' + page.denyText )
                )
            page.db.remove(record)

    def presentContent(self, proc: PageProcessor) -> XMLContent:
        assert isinstance(self, FabPage), self # indirect type hint
        yield (
            xhtml.p[
                self.recordName.capitalize(), ' ',
                xhtml.b[ proc.args.id ], ' has been deleted.'
                ],
            self.backToReferer(proc.req)
            )
