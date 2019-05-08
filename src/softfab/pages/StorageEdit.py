# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, Optional
from urllib.parse import urlparse

from softfab.EditPage import (
    AbstractPhase, EditArgs, EditPage, EditPagePrev, EditProcessor
)
from softfab.Page import PresentableError
from softfab.formlib import checkBox, makeForm, submitButton, textInput
from softfab.pageargs import BoolArg, StrArg
from softfab.request import Request
from softfab.storagelib import (
    Storage, getStorageIdByName, getStorageIdByURL, storageDB
)
from softfab.userlib import checkPrivilege
from softfab.webgui import PropertiesTable
from softfab.xmlgen import XMLContent, xhtml


class MergePhase(AbstractPhase):

    def process(self, proc):
        req = proc.req
        args = proc.args

        checkPrivilege(
            proc.user,
            storageDB.privilegeObject + '/m',
            'modify storages'
            )

        oldElement = proc.oldElement
        if oldElement is None:
            # It is not possible to create new storage records with this
            # page, so the absence of the old record means it was merged.
            proc.showBackButton = False
            raise PresentableError((
                xhtml.p[
                    'Your changes were ', xhtml.b['not saved'],
                    ' because the storage was merged into another'
                    ' while you were editing.'
                    ],
                self.page.backToParent(proc.req)
                ))

        oldId = args.id
        newId = args.newId
        if oldId == newId:
            element = proc.createElement(req, newId, args, oldElement)
            idByName = getStorageIdByName(element['name'])
            idByURL = getStorageIdByURL(element['url'])
            if idByName in (oldId, None) and idByURL in (oldId, None):
                storageDB.update(element)
            # Pass "element" to presentContent().
            proc.element = element
        else:
            try:
                newElement = storageDB[newId]
            except KeyError:
                # Reset the newId so we try to find a new merge target after
                # the back button is submitted.
                proc.args = args.override(newId = oldId)
                raise PresentableError(xhtml.p[
                    'The storage selected for merging no longer exists.'
                    ])
            newElement.takeOver(oldElement)

    def presentContent(self, proc: EditProcessor) -> XMLContent:
        if proc.args.newId != proc.args.id:
            return (
                xhtml.p[ 'The storages have been merged.' ],
                self.page.backToParent(proc.req)
                )

        # TODO: Design a way of passing data that mypy understands.
        element = proc.element # type: ignore
        idByName = getStorageIdByName(element['name'])
        idByURL = getStorageIdByURL(element['url'])
        if idByName is not None and idByName != element.getId():
            mergeId = idByName # type: Optional[str]
            if storageDB[idByName]['url'] == element['url']:
                theSame = 'name and URL'
            else:
                theSame = 'name'
            message = [
                'A storage with the same ', theSame, ' already exists.'
                ] # type: XMLContent
        elif idByURL is not None and idByURL != element.getId():
            mergeId = idByURL
            otherName = storageDB[idByURL].getName()
            message = [
                'Storage ', xhtml.b[ otherName ], ' already has the same URL.'
                ]
        else:
            mergeId = None

        if mergeId is None:
            return self.__presentCommitted(proc, element)
        else:
            return self.__presentMerge(proc, message, mergeId)

    def __presentMerge(self, proc, message, mergeId):
        yield xhtml.p[
            message, xhtml.br, 'It can be merged with the current storage.'
            ]
        yield makeForm(
            args = proc.args.override(
                prev = EditPagePrev.SAVE_AS,
                newId = mergeId
                )
            )[
            xhtml.p[
                submitButton(name = 'action', value = 'save')[ 'Merge' ],
                ' ',
                submitButton(name = 'action', value = 'cancel')
                ]
            ].present(proc=proc)

    def __presentCommitted(self, proc, element):
        page = self.page
        return (
            xhtml.p[
                'Changes to ', page.elemName, ' ', element['name'],
                ' have been committed.'
                ],
            page.backToParent(proc.req)
            )

class StorageEdit(EditPage):
    # FabPage constants:
    icon = 'IconReport'
    description = 'Edit Storage'
    linkDescription = False

    # EditPage constants:
    elemTitle = 'Storage'
    elemName = 'storage'
    db = storageDB
    privDenyText = 'storages'
    useScript = False
    formId = 'storage'
    autoName = False

    class Arguments(EditArgs):
        id = StrArg()
        name = StrArg('')
        url = StrArg('')
        export = BoolArg()

    class Processor(EditProcessor['StorageEdit.Arguments', Storage]):

        def createElement(self,
                          req: Request,
                          recordId: str,
                          args: 'StorageEdit.Arguments',
                          oldElement: Optional[Storage]
                          ) -> Storage:
            assert oldElement is not None
            return Storage({
                'id': recordId,
                'name': args.name,
                'url': args.url,
                'export': args.export
                }, oldElement)

        def _initArgs(self, element: Optional[Storage]) -> Mapping[str, object]:
            if element is None:
                return {}
            else:
                return dict(
                    name = element['name'],
                    url = element['url'],
                    export = element.hasExport()
                    )

        def _checkState(self) -> None:
            args = self.args
            if args.name == '':
                raise PresentableError(xhtml.p[
                    'The storage name must not be empty.'
                    ])
            url = urlparse(args.url)
            if url.scheme == '':
                raise PresentableError(xhtml.p[
                    'Scheme part (for example "http://") is missing from URL.'
                    ])
            if url.fragment != '':
                raise PresentableError(xhtml.p[
                    'Base URL cannot include a fragment ("#%s").' % url.fragment
                    ])

        def _validateState(self) -> None:
            args = self.args

            url = args.url
            if len(url) > 0 and url[-1] != '/':
                self.args = args.override(url = url + '/')

    def __init__(self):
        EditPage.__init__(self)
        self.savePhase = MergePhase(self)

    def getFormContent(self, proc):
        return StorageTable.instance

class StorageTable(PropertiesTable):

    def iterRows(self, **kwargs):
        yield 'Name', textInput(name='name', size=32)
        yield 'URL', textInput(name='url', size=80)
        yield 'Export', checkBox(name='export')[
            'CGI script for exporting reports is installed on web server'
            ]
