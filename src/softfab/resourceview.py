# SPDX-License-Identifier: BSD-3-Clause

from collections import defaultdict

from softfab.Page import PresentableError
from softfab.connection import ConnectionStatus
from softfab.databaselib import checkWrapperVarName
from softfab.formlib import dropDownList, emptyOption, hiddenInput, textInput
from softfab.pageargs import ListArg
from softfab.pagelinks import createCapabilityLink
from softfab.resreq import ResourceSpec, taskRunnerResourceRefName
from softfab.restypelib import resTypeDB, taskRunnerResourceTypeName
from softfab.webgui import Panel, Table, rowManagerInstanceScript
from softfab.xmlgen import txt, xhtml


def getResourceStatus(resource):
    """Returns a status summary string for `resource`."""
    connectionStatus = resource.getConnectionStatus()
    if connectionStatus is not ConnectionStatus.CONNECTED:
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
    else:
        return 'free'

def presentCapabilities(capabilities, resType, capFilter = None):
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

initialTaskRunnerResourceSpec = ResourceSpec.create(
    taskRunnerResourceRefName, taskRunnerResourceTypeName, ()
    )

class ResourceRequirementsArgsMixin:
    '''Adds resource requirement editing arguments to a page.'''
    ref = ListArg()
    type = ListArg()
    caps = ListArg()

def addResourceRequirementsToElement(element, args):
    for ref, resType, caps in zip(args.ref, args.type, args.caps):
        element.addResourceSpec(
            ResourceSpec.create(ref, resType, caps.split())
            )

def initResourceRequirementsArgs(element):
    if element is None:
        specs = (initialTaskRunnerResourceSpec,)
    else:
        specs = tuple(element.resourceClaim)
    return dict(
        ref=[spec.reference for spec in specs],
        type=[spec.typeName for spec in specs],
        caps=[' '.join(sorted(spec.capabilities)) for spec in specs]
        )

def checkResourceRequirementsState(args):
    if args.type.count(taskRunnerResourceTypeName) != 1:
        # Even though the UI can only produce one Task Runner entry,
        # we should never trust the client to enforce that.
        raise PresentableError(xhtml.p[
            'There must be exactly one Task Runner '
            '(resource type "%s").' % taskRunnerResourceTypeName
            ])

    if not len(args.ref) == len(args.type) == len(args.caps):
        raise PresentableError(xhtml.p[
            'Unequal number of ref/type/caps args'
            ])
    usedRefs = set()
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
                    'The Task Runner resource reference must be '
                    'named "%s", got "%s" instead.'
                    % (taskRunnerResourceRefName, ref)
                    ])
        else:
            try:
                checkWrapperVarName(ref)
            except KeyError as ex:
                raise PresentableError(xhtml.p[
                    'Invalid resource reference name "%s": ' % ref,
                    xhtml.b[ str(ex.args[0]) ], '.'
                    ])

        # Check whether reference name is unique.
        if ref in usedRefs:
            raise PresentableError(xhtml.p[
                'Duplicate resource reference name "%s".' % ref
                ])
        usedRefs.add(ref)

        if resType not in resTypeDB:
            raise PresentableError(xhtml.p[
                'Resource type "%s" does not exist (anymore).' % resType
                ])

def resourceRequirementsWidget(parentClaim=None):
    yield xhtml.h2[ 'Resource Requirements' ]
    yield ResourceRequirementsTable(parentClaim)
    yield xhtml.ul[
        xhtml.li[
            'To delete a resource requirement, '
            'set its type to "%s".' % ResourceRequirementsTable.NONE_TEXT
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

    NONE_TEXT = '(none)'

    def __init__(self, parentClaim=None):
        super().__init__()
        self.__parentClaim = parentClaim

    def iterRows(self, *, proc, **kwargs):
        nonFixedResTypeNames = sorted(
            set(resTypeDB.keys()) - {taskRunnerResourceTypeName}
            )
        resWidget = dropDownList(name='type')[
            emptyOption[ self.NONE_TEXT ],
            nonFixedResTypeNames
            ]

        # reqMap: type -> ref -> (inherited, caps)*
        reqMap = defaultdict(lambda: defaultdict(list))
        parentClaim = self.__parentClaim
        if parentClaim is not None:
            for spec in parentClaim:
                ref = spec.reference
                resType = spec.typeName
                reqMap[resType][ref].append(
                    (True, sorted(spec.capabilities))
                    )
        args = proc.args
        for ref, resType, caps in zip(args.ref, args.type, args.caps):
            reqMap[resType][ref].append(
                (False, sorted(caps.split()))
                )

        for resType in [taskRunnerResourceTypeName] + nonFixedResTypeNames:
            refMap = reqMap[resType]

            for ref in sorted(refMap.keys()):
                capMap = dict(refMap[ref])
                inherited = True in capMap
                if inherited or resType == taskRunnerResourceTypeName:
                    # Type and reference are fixed.
                    typeControl = (
                        resTypeDB[resType]['presentation'],
                        hiddenInput(name='type', value=resType)
                        )
                    refControl = (
                        xhtml.span(class_='var')[ref],
                        hiddenInput(name='ref', value=ref)
                        )
                else:
                    # User can edit type and reference.
                    typeControl = resWidget(selected=resType)
                    refControl = _refInput(value=ref)

                if inherited:
                    capsControl = _CapabilitiesTable.instance.present(
                        proc=proc, resType=resType, capMap=capMap, **kwargs
                        )
                else:
                    capsControl = _capsInput(value=' '.join(capMap[False]))

                yield typeControl, refControl, capsControl

        # Empty entry at the end.
        yield resWidget(selected=''), _refInput(value=''), _capsInput(value='')

    def present(self, **kwargs):
        yield super().present(**kwargs)
        yield rowManagerInstanceScript(bodyId=self.bodyId).present(**kwargs)

_refInput = textInput(name='ref', size=20, class_='var')
_capsInput = textInput(name='caps', size=60)

class _CapabilitiesTable(Table):
    columns = None, None
    style = 'hollow'

    def iterRows(self, *, resType, capMap, **kwargs):
        yield 'inherited:\u00A0', presentCapabilities(
            capMap.get(True, []), resType
            )
        yield 'additional:\u00A0', _capsInput(
            value=' '.join(capMap.get(False, [])), size=51
            )

def validateResourceRequirementsState(proc):
    args = proc.args

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

    def iterRows(self, *, claim, **kwargs):
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
