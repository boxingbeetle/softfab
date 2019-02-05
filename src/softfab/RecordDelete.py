# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from enum import Enum
from typing import ClassVar

from FabPage import FabPage, IconModifier
from Page import PageProcessor, PresentableError, Redirect
from databaselib import Database
from formlib import actionButtons, makeForm
from pageargs import EnumArg, PageArgs, StrArg
from utils import abstract, pluralize
from webgui import unorderedList
from xmlgen import xhtml

class RecordInUseError(Exception):

    def __init__(self, refererName, presenter, referers):
        Exception.__init__(self, 'record in use')
        self.refererName = refererName
        self.presenter = presenter
        self.referers = referers

class DeleteArgs(PageArgs):
    id = StrArg()

Actions = Enum('Actions', 'DELETE CANCEL')

def fetchRecordForDeletion(recordId, page):
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
                )]
            )

    return record

class RecordDelete_GET(FabPage, ABC):
    """Reusable implementation for handling a GET of a "delete record" dialog.
    Inherit from RecordDelete_GET and define the following fields:
        db = database to delete record from
        recordName = name under which user knows this record type
        denyText = text that appears in the 'access denied' message
    You can define these at class scope (since they are constants).
    """
    db = abstract # type: ClassVar[Database]
    recordName = abstract # type: ClassVar[str]
    denyText = abstract # type: ClassVar[str]

    description = abstract
    linkDescription = False
    icon = abstract
    iconModifier = IconModifier.DELETE

    class Arguments(DeleteArgs):
        pass

    class Processor(PageProcessor):
        def process(self, req):
            fetchRecordForDeletion(req.args.id, self.page)

    def fabTitle(self, proc):
        return 'Delete ' + ' '.join(
            word.capitalize() for word in self.recordName.split()
            )

    def checkAccess(self, req):
        pass

    def getCancelURL(self, req):
        '''URL to redirect to when the user chooses "Cancel".
        By default this is the active referer with a fallback to the parent
        page, but subclasses can override this.
        '''
        return req.args.refererURL or self.getParentURL(req)

    def presentContent(self, proc):
        yield xhtml.p[
            'Delete ', self.recordName, ' ', xhtml.b[ proc.args.id ], '?'
            ]
        yield makeForm(args = proc.args)[
            xhtml.p[ actionButtons(Actions) ]
            ].present(proc=proc)

    def presentError(self, proc, message):
        yield message
        yield self.backToReferer(proc.req)

    def checkState(self, record):
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

    class Arguments(DeleteArgs):
        action = EnumArg(Actions)

    class Processor(PageProcessor):
        def process(self, req):
            action = req.args.action
            if action is not Actions.DELETE:
                assert action is Actions.CANCEL, action
                raise Redirect(self.page.getCancelURL(req))

            record = fetchRecordForDeletion(req.args.id, self.page)
            req.checkPrivilegeForOwned(
                self.page.db.privilegeObject + '/d',
                record,
                ( 'delete this ' + self.page.recordName,
                    'delete ' + self.page.denyText )
                )
            self.page.db.remove(record)

    def presentContent(self, proc):
        yield (
            xhtml.p[
                self.recordName.capitalize(), ' ',
                xhtml.b[ proc.args.id ], ' has been deleted.'
                ],
            self.backToReferer(proc.req)
            )
