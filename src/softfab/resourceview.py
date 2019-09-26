# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict
from typing import (
    Callable, Collection, DefaultDict, Iterator, List, Mapping, Optional, Set,
    Tuple, cast
)

from softfab.Page import PageProcessor, PresentableError
from softfab.connection import ConnectionStatus
from softfab.databaselib import Retriever, checkWrapperVarName
from softfab.datawidgets import DataColumn
from softfab.formlib import (
    dropDownList, emptyOption, hiddenInput, option, textInput
)
from softfab.frameworklib import TaskDefBase
from softfab.pageargs import ListArg, PageArgs
from softfab.pagelinks import createCapabilityLink, createTaskRunnerDetailsLink
from softfab.resourcelib import ResourceBase, TaskRunner
from softfab.resreq import (
    ResourceClaim, ResourceSpec, taskRunnerResourceRefName
)
from softfab.restypelib import resTypeDB, taskRunnerResourceTypeName
from softfab.restypeview import iterResourceTypes
from softfab.webgui import Panel, Table, cell, rowManagerInstanceScript
from softfab.xmlgen import XMLContent, txt, xhtml


class ResourceNameColumn(DataColumn[ResourceBase]):
    label = 'Name'
    keyName = 'id'
    cellStyle = 'nobreak'

    def presentCell(self, record: ResourceBase, **kwargs: object) -> XMLContent:
        if isinstance(record, TaskRunner):
            return createTaskRunnerDetailsLink(record.getId())
        else:
            return record.getId()

def getResourceStatus(resource: ResourceBase) -> str:
    """Returns a status summary string for `resource`."""
    connectionStatus = resource.getConnectionStatus()
    if connectionStatus in (ConnectionStatus.LOST, ConnectionStatus.WARNING):
        return connectionStatus.name.lower()
    elif resource.isReserved():
        executionRun = resource.getRun()
        if executionRun is not None:
            alert = executionRun.getAlert()
            if alert:
                return alert
        return 'reserved'
    elif resource.isSuspended():
        return 'suspended'
    elif connectionStatus is ConnectionStatus.CONNECTED:
        return 'free'
    else:
        return connectionStatus.name.lower()

class StatusColumn(DataColumn[ResourceBase]):
    sortKey = cast(Retriever, staticmethod(getResourceStatus))
    def presentCell(self, record: ResourceBase, **kwargs: object) -> XMLContent:
        status = getResourceStatus(record)
        return cell(class_=status)[ status ]

def presentCapabilities(capabilities: Collection[str],
                        resType: str,
                        capFilter: Optional[Callable[[str], bool]] = None
                        ) -> XMLContent:
    if not capabilities:
        return '-'
    if capFilter is None:
        capFilter = lambda cap: False
    return txt(', ').join(
        createCapabilityLink(resType, cap)(
            class_ = 'match' if capFilter(cap) else None
            )
        for cap in sorted(capabilities)
        )

class CapabilitiesPanel(Panel):
    label = 'Capabilities'
    content = xhtml.br.join((
        textInput(name='capabilities', size=80, style='width:100%'),
        'Multiple capabilities should be separated by spaces.',
        'Task definitions use capabilities to put additional '
        'requirements on the resources they need.'
        ))

class CommentPanel(Panel):
    label = 'Description'
    content = textInput(name = 'description', size = 80, style='width:100%')

initialResourceClaim = ResourceClaim.create((
    ResourceSpec.create(
        taskRunnerResourceRefName, taskRunnerResourceTypeName, ()
        ),
    ))

class ResourceRequirementsArgsMixin:
    '''Adds resource requirement editing arguments to a page.'''
    ref = ListArg()
    type = ListArg()
    caps = ListArg()

class _ResourceRequirementsArgs(ResourceRequirementsArgsMixin, PageArgs):
    """Helper class for type checking."""

def addResourceRequirementsToElement(element: TaskDefBase,
                                     args: ResourceRequirementsArgsMixin
                                     ) -> None:
    args = cast(_ResourceRequirementsArgs, args)
    for ref, resType, caps in zip(args.ref, args.type, args.caps):
        element.addResourceSpec(
            ResourceSpec.create(ref, resType, caps.split())
            )

def initResourceRequirementsArgs(element: Optional[TaskDefBase]
                                 ) -> Mapping[str, object]:
    if element is None:
        claim = initialResourceClaim
    else:
        claim = element.resourceClaim.merge(initialResourceClaim)
    return dict(
        ref=[spec.reference for spec in claim],
        type=[spec.typeName for spec in claim],
        caps=[' '.join(sorted(spec.capabilities)) for spec in claim]
        )

def checkResourceRequirementsState(args: ResourceRequirementsArgsMixin) -> None:
    args = cast(_ResourceRequirementsArgs, args)
    if args.type.count(taskRunnerResourceTypeName) != 1:
        # Even though the UI can only produce one Task Runner entry,
        # we should never trust the client to enforce that.
        raise PresentableError(xhtml.p[
            f'There must be exactly one Task Runner '
            f'(resource type "{taskRunnerResourceTypeName}").'
            ])

    if not len(args.ref) == len(args.type) == len(args.caps):
        raise PresentableError(xhtml.p[
            'Unequal number of ref/type/caps args'
            ])
    usedRefs: Set[str] = set()
    for ref, resType in zip(args.ref, args.type):
        if resType == '':
            continue

        # Check whether reference name is valid.
        if not ref:
            raise PresentableError(xhtml.p[
                'Empty resource reference name is not allowed.'
                ])
        if resType == taskRunnerResourceTypeName:
            if ref != taskRunnerResourceRefName:
                raise PresentableError(xhtml.p[
                    f'The Task Runner resource reference must be '
                    f'named "{taskRunnerResourceRefName}", '
                    f'got "{ref}" instead.'
                    ])
        else:
            try:
                checkWrapperVarName(ref)
            except KeyError as ex:
                raise PresentableError(xhtml.p[
                    f'Invalid resource reference name "{ref}": ',
                    xhtml.b[ str(ex.args[0]) ], '.'
                    ])

        # Check whether reference name is unique.
        if ref in usedRefs:
            raise PresentableError(xhtml.p[
                f'Duplicate resource reference name "{ref}".'
                ])
        usedRefs.add(ref)

        if resType not in resTypeDB:
            raise PresentableError(xhtml.p[
                f'Resource type "{resType}" does not exist (anymore).'
                ])

NONE_TEXT = '(none)'

def resTypeOptions() -> Iterator[XMLContent]:
    yield emptyOption[NONE_TEXT]
    for resType in iterResourceTypes():
        resTypeName = resType.getId()
        if resTypeName != taskRunnerResourceTypeName:
            yield option(value=resTypeName)[resType.presentationName]

def resourceRequirementsWidget(parentClaim: Optional[ResourceClaim] = None
                               ) -> XMLContent:
    yield xhtml.h3[ 'Resource Requirements' ]
    yield ResourceRequirementsTable(parentClaim)
    yield xhtml.ul[
        xhtml.li[
            f'To delete a resource requirement, set its type to "{NONE_TEXT}".'
            ],
        xhtml.li[
            'The "reference" field contains the name of the wrapper '
            'variable that will hold the locator of the reserved resource.'
            ],
        xhtml.li[
            'To share a job-exclusive resource between tasks, those tasks '
            'must use the same reference name for that resource.'
            ],
        xhtml.li[
            'The "capabilities" field contains a space separated list '
            'of the names of the required capabilities.'
            ],
        ]

class ResourceRequirementsTable(Table):
    columns = 'Type', 'Reference', 'Capabilities'
    bodyId = 'reslist'

    def __init__(self, parentClaim: Optional[ResourceClaim] = None):
        super().__init__()
        self.__parentClaim = parentClaim

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        proc = cast(PageProcessor, kwargs['proc'])
        resWidget = dropDownList(name='type')[resTypeOptions()]

        # pylint: disable=line-too-long
        reqMap: DefaultDict[str, DefaultDict[str, List[Tuple[bool, List[str]]]]] = defaultdict(
            lambda: defaultdict(list)
            )
              #       type -> ref -> (inherited, caps)*
        parentClaim = self.__parentClaim
        if parentClaim is not None:
            for spec in parentClaim:
                ref = spec.reference
                resTypeName = spec.typeName
                reqMap[resTypeName][ref].append(
                    (True, sorted(spec.capabilities))
                    )
        args = cast(_ResourceRequirementsArgs, proc.args)
        for ref, resTypeName, caps in zip(args.ref, args.type, args.caps):
            reqMap[resTypeName][ref].append(
                (False, sorted(caps.split()))
                )

        for resType in iterResourceTypes():
            resTypeName = resType.getId()
            refMap = reqMap[resTypeName]

            for ref in sorted(refMap.keys()):
                capMap = dict(refMap[ref])
                inherited = True in capMap
                if inherited or resTypeName == taskRunnerResourceTypeName:
                    # Type and reference are fixed.
                    typeControl: XMLContent = (
                        resType.presentationName,
                        hiddenInput(name='type', value=resTypeName)
                        )
                    refControl: XMLContent = (
                        xhtml.span(class_='var')[ref],
                        hiddenInput(name='ref', value=ref)
                        )
                else:
                    # User can edit type and reference.
                    typeControl = resWidget(selected=resTypeName)
                    refControl = _refInput(value=ref)

                if inherited:
                    capsControl = _CapabilitiesTable.instance.present(
                        resType=resTypeName, capMap=capMap, **kwargs
                        )
                else:
                    capsControl = _capsInput(value=' '.join(capMap[False]))

                yield typeControl, refControl, capsControl

        # Empty entry at the end.
        yield resWidget(selected=''), _refInput(value=''), _capsInput(value='')

    def present(self, **kwargs: object) -> XMLContent:
        yield super().present(**kwargs)
        yield rowManagerInstanceScript(bodyId=self.bodyId).present(**kwargs)

_refInput = textInput(name='ref', size=20, class_='var')
_capsInput = textInput(name='caps', size=60)

class _CapabilitiesTable(Table):
    columns = None, None
    style = 'hollow'

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        resType = cast(str, kwargs['resType'])
        capMap = cast(Mapping[bool, List[str]], kwargs['capMap'])
        yield 'inherited:\u00A0', presentCapabilities(
            capMap.get(True, []), resType
            )
        yield 'additional:\u00A0', _capsInput(
            value=' '.join(capMap.get(False, [])), size=51
            )

def validateResourceRequirementsState(proc: PageProcessor) -> None:
    args = cast(_ResourceRequirementsArgs, proc.args)

    filteredRef, filteredType, filteredCaps = [], [], []
    for ref, resType, caps in zip(args.ref, args.type, args.caps):
        if resType:
            filteredRef.append(ref)
            filteredType.append(resType)
            filteredCaps.append(caps)
    proc.args = args.override(
        ref=filteredRef, type=filteredType, caps=filteredCaps
        )

class InlineResourcesTable(Table):
    '''Resources table to be used as a cell inside a task properties table.
    '''
    hideWhenEmpty = True
    columns = None, None, None
    style = 'hollow'

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        claim = cast(ResourceClaim, kwargs['claim'])
        for spec in claim:
            ref = spec.reference
            resType = spec.typeName
            capabilities = spec.capabilities
            yield (
                ( createCapabilityLink(resType), '\u00A0' ),
                ( 'as ', xhtml.span(class_='var')[ref] ),
                ( '\u00A0with capabilities: ',
                    presentCapabilities(capabilities, resType)
                    )
                )
