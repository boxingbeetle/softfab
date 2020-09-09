# SPDX-License-Identifier: BSD-3-Clause

from abc import abstractmethod
from enum import Enum
from typing import Callable, ClassVar, Collection, Generic, TypeVar, cast

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.databaselib import DBRecord, Database
from softfab.formlib import actionButtons, makeForm
from softfab.pageargs import EnumArg, PageArgs, StrArg
from softfab.request import Request
from softfab.users import User, checkPrivilegeForOwned
from softfab.utils import abstract, pluralize
from softfab.webgui import unorderedList
from softfab.xmlgen import XML, XMLContent, xhtml


class RecordInUseError(Exception):

    def __init__(self,
                 refererName: str,
                 presenter: Callable[[str], XMLContent],
                 referers: Collection[str]):
        super().__init__('record in use')
        self.refererName = refererName
        self.presenter = presenter
        self.referers = referers

class DeleteArgs(PageArgs):
    id = StrArg()

DeleteArgsT = TypeVar('DeleteArgsT', bound=DeleteArgs)

class RecordDeleteProcessor(PageProcessor[DeleteArgsT],
                            Generic[DeleteArgsT, DBRecord]):

    @property
    @abstractmethod
    def db(self) -> Database[DBRecord]:
        """Database to delete record from."""
        raise NotImplementedError

    recordName: ClassVar[str] = abstract
    """Name under which user knows this record type."""

    denyText: ClassVar[str] = abstract
    """Text that appears in the 'access denied' message."""

    async def process(self, req: Request[DeleteArgsT], user: User) -> None:
        fetchRecordForDeletion(self, req.args.id)

    def checkState(self, record: DBRecord) -> None:
        """Checks whether the given record can be deleted.
        It is possible deletion is not allowed if other records depend on it.
        If deletion is allowed, do nothing, otherwise raise PresentableError
        or RecordInUseError.
        The default implementation does nothing.
        """

Actions = Enum('Actions', 'DELETE CANCEL')

def fetchRecordForDeletion(proc: RecordDeleteProcessor[DeleteArgsT, DBRecord],
                           recordId: str
                           ) -> DBRecord:
    """Tries to fetch the record with the given ID.
    Raises PresentableError if the record does not exist or can currently
    not be deleted.
    """

    try:
        record = proc.db[recordId]
    except KeyError:
        raise PresentableError(xhtml.p[
            'Cannot delete ', proc.recordName, ' ', xhtml.b[ recordId ],
            ' because it does not exist (anymore).'
            ])

    try:
        proc.checkState(record)
    except RecordInUseError as ex:
        raise PresentableError(xhtml.p[
            'Cannot delete ', proc.recordName, ' ', xhtml.b[ recordId ],
            ' because it is used in the following ',
            pluralize(ex.refererName, ex.referers), ':'
            ] + unorderedList[(
                ex.presenter(referer) for referer in sorted(ex.referers)
                )].present()
            )

    return record

class RecordDelete_GET(FabPage['RecordDelete_GET.Processor[DBRecord]',
                               'RecordDelete_GET.Arguments']):
    """Reusable implementation for handling a GET of a "delete record" dialog.
    """

    description = abstract
    linkDescription = False
    icon = abstract
    iconModifier = IconModifier.DELETE

    class Arguments(DeleteArgs):
        pass

    class Processor(RecordDeleteProcessor[Arguments, DBRecord]):
        @property
        @abstractmethod
        def db(self) -> Database[DBRecord]:
            raise NotImplementedError

    def pageTitle(self, proc: Processor[DBRecord]) -> str:
        return 'Delete ' + ' '.join(
            word.capitalize() for word in proc.recordName.split()
            )

    def checkAccess(self, user: User) -> None:
        pass

    def getCancelURL(self, args: Arguments) -> str:
        '''URL to redirect to when the user chooses "Cancel".
        By default this is the active referer with a fallback to the parent
        page, but subclasses can override this.
        '''
        return args.refererURL or self.getParentURL(args)

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(RecordDelete_GET.Processor[DBRecord], kwargs['proc'])
        yield xhtml.p[
            'Delete ', proc.recordName, ' ', xhtml.b[ proc.args.id ], '?'
            ]
        yield makeForm(args = proc.args)[
            xhtml.p[ actionButtons(Actions) ]
            ].present(**kwargs)

    def presentError(self, message: XML, **kwargs: object) -> XMLContent:
        proc = cast(RecordDelete_GET.Processor[DBRecord], kwargs['proc'])
        yield message
        yield self.backToReferer(proc.args)

class RecordDelete_POSTMixin:
    """Mixin for implementing the POST handling of a "delete record" dialog.
    Subclasses are expected to inherit from this mixin and the GET page.
    """

    class ArgumentsMixin:
        action = EnumArg(Actions)

    class ProcessorMixin:
        async def process(self, req: Request, user: User) -> None:
            page = cast(RecordDelete_GET, getattr(self, 'page'))
            action = req.args.action
            if action is not Actions.DELETE:
                assert action is Actions.CANCEL, action
                raise Redirect(page.getCancelURL(req.args))

            assert isinstance(self, RecordDeleteProcessor), self
            record = fetchRecordForDeletion(self, req.args.id)
            checkPrivilegeForOwned(
                user,
                self.db.privilegeObject + '/d',
                record,
                ( 'delete this ' + self.recordName,
                  'delete ' + self.denyText )
                )
            self.db.remove(record)

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(RecordDeleteProcessor, kwargs['proc'])
        assert isinstance(self, RecordDelete_GET), self # indirect type hint
        yield (
            xhtml.p[
                proc.recordName.capitalize(), ' ',
                xhtml.b[ proc.args.id ], ' has been deleted.'
                ],
            self.backToParent(proc.args)
            )
