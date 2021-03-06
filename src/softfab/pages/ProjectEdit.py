# SPDX-License-Identifier: BSD-3-Clause

from typing import (
    ClassVar, Iterable, Iterator, Mapping, Optional, Sequence, Tuple, cast,
    overload
)
from urllib.parse import urlparse
import time

from softfab.EditPage import (
    EditArgs, EditPage, EditProcessor, EditProcessorBase, InitialEditArgs,
    InitialEditProcessor
)
from softfab.FabPage import IconModifier
from softfab.Page import PresentableError
from softfab.formlib import (
    DropDownList, Option, RadioTable, checkBox, textInput
)
from softfab.pageargs import ArgsCorrected, BoolArg, EnumArg, IntArg, StrArg
from softfab.projectlib import (
    EmbeddingPolicy, Project, ProjectDB, defaultMaxJobs, getKnownTimezones
)
from softfab.setcalc import categorizedLists
from softfab.webgui import PropertiesTable, Widget, docLink
from softfab.xmlgen import XML, XMLContent, xhtml


class ProjectEditArgs(EditArgs):
    name = StrArg('')
    targets = StrArg('')
    tagkeys = StrArg('')
    timezone = StrArg(None)
    maxjobs = IntArg(defaultMaxJobs)
    taskprio = BoolArg()
    embed = EnumArg(EmbeddingPolicy, None)
    embedcustom = StrArg('')

class ProjectEditBase(EditPage[ProjectEditArgs, Project]):
    # FabPage constants:
    icon = 'Project1'
    iconModifier = IconModifier.NONE
    description = 'Project'

    # EditPage constants:
    elemTitle = 'Project Configuration'
    elemName = 'project configuration'
    dbName = 'projectDB'
    privDenyText = 'project configuration'
    useScript = False
    formId = 'project'
    autoName = 'singleton'

    def getFormContent(self,
                       proc: EditProcessorBase[ProjectEditArgs, Project]
                       ) -> XMLContent:
        yield ProjectTable.instance
        yield xhtml.p[
            'For help about above project values, please read the '
            'document: ', docLink('/start/user_manual/#configure')[
                'Configure project' ], '.'
            ]

class ProjectEdit_GET(ProjectEditBase):

    class Arguments(InitialEditArgs):
        pass

    class Processor(InitialEditProcessor[ProjectEditArgs, Project]):
        argsClass = ProjectEditArgs

        projectDB: ClassVar[ProjectDB]

        def _initArgs(self, element: Optional[Project]) -> Mapping[str, object]:
            if element is None:
                return {}
            else:
                return dict(
                    name = element.name,
                    targets = ' '.join(sorted(element.getTargets())),
                    tagkeys = ', '.join(element.getTagKeys()),
                    timezone = element.timezone,
                    maxjobs = element['maxjobs'],
                    taskprio = element['taskprio'],
                    embed = element['embed'],
                    embedcustom = element['embedcustom'],
                    )

class ProjectEdit_POST(ProjectEditBase):

    class Arguments(ProjectEditArgs):
        pass

    class Processor(EditProcessor[ProjectEditArgs, Project]):

        projectDB: ClassVar[ProjectDB]

        def createElement(self,
                          recordId: str,
                          args: ProjectEditArgs,
                          oldElement: Optional[Project]
                          ) -> Project:
            assert args is not None
            assert oldElement is not None
            element = Project( {
                'name': args.name,
                'maxjobs': args.maxjobs,
                # TODO: Create a TimezoneArg?
                'timezone': decodeTimezone(args.timezone),
                'taskprio': args.taskprio,
                'embed': args.embed,
                'embedcustom': args.embedcustom,
                'version': oldElement.dbVersion,
                'anonguest': oldElement.anonguest,
                } )
            element.setTargets(args.targets.split())
            element.setTagKeys(
                key
                for key in ( key.strip() for key in args.tagkeys.split(',') )
                if key
                )
            return element

        def _checkState(self) -> None:
            args = self.args

            # Check max job count.
            if args.maxjobs <= 0:
                raise PresentableError(xhtml.p[
                    f'The value for multiple jobs limit ({args.maxjobs:d}) '
                    f'is invalid; it must be a positive integer.'
                    ])

            # Check timezone.
            # Since timezone is selected from a drop-down list, under normal
            # circumstances it will always be valid.
            timezone = decodeTimezone(args.timezone)
            knownZones = getKnownTimezones()
            if knownZones and timezone not in knownZones:
                raise PresentableError(xhtml.p[
                    f'Unknown timezone "{timezone}".'
                    ])

            # Check site filters.
            siteFilters = []
            for siteFilter in args.embedcustom.split():
                if ';' in siteFilter:
                    # Semicolon is used as a separator in the CSP header.
                    raise PresentableError(xhtml.p[
                        f'Illegal character ";" in site filter "{siteFilter}"'
                        ])
                try:
                    url = urlparse(siteFilter)
                    if not url.scheme:
                        # Force scheme-less location to be parsed as a netloc;
                        # otherwise urlparse() treats it as a relative path.
                        url = urlparse('//' + siteFilter)
                    # Force sanity check of port number.
                    _ = url.port
                except ValueError as ex:
                    raise PresentableError(xhtml.p[
                        f'Invalid site filter "{siteFilter}": {ex}'
                        ])
                for name in ('path', 'params', 'query', 'fragment',
                             'username', 'password'):
                    if getattr(url, name):
                        raise PresentableError(xhtml.p[
                            f'Site filter "{siteFilter}" contains {name}, '
                            f'which is not supported'
                            ])
                scheme = url.scheme
                netloc = url.netloc
                if scheme and netloc:
                    siteFilters.append(f'{scheme}://{netloc}')
                elif scheme:
                    siteFilters.append(f'{scheme}:')
                elif netloc:
                    siteFilters.append(netloc)
                else:
                    # Note: I don't know what filter would parse like this,
                    #       but handle it just in case.
                    raise PresentableError(xhtml.p[
                        f'Site filter "{siteFilter}" contains no information'
                        ])
            if not siteFilters and args.embed is EmbeddingPolicy.CUSTOM:
                raise PresentableError(xhtml.p[
                    'Custom embedding policy cannot be empty'
                    ])
            siteFilterStr = ' '.join(siteFilters)
            if siteFilterStr != args.embedcustom:
                raise ArgsCorrected(args, embedcustom=siteFilterStr)

            #if ';' in embedCustom:
                #raise PresentableError(xhtml.p[
                    #'Illegal character in site filter: ";"'
                    #])

def decodeTimezone(tzStr: Optional[str]) -> Optional[str]:
    if tzStr is None:
        return None
    else:
        return tzStr.replace(',', '/').replace(' ', '_')

@overload
def encodeTimezone(timezone: None) -> None: ...

@overload
def encodeTimezone(timezone: str) -> str: ...

def encodeTimezone(timezone: Optional[str]) -> Optional[str]:
    if timezone is None:
        return None
    else:
        return timezone.replace('/', ',').replace('_', ' ')

class TimeZoneSelector(DropDownList):
    name = 'timezone'

    def getActive(self, **kwargs: object) -> Optional[str]:
        proc = cast(ProjectEditBase.Processor[ProjectEditArgs], kwargs['proc'])
        return encodeTimezone(proc.args.timezone)

    def iterOptions(self, **kwargs: object) -> Iterator[Option]:

        def splitZones() -> Iterator[Tuple[str, str]]:
            for fullZone in cast(Iterable[str], kwargs['timezones']):
                if '/' in fullZone:
                    region, name = encodeTimezone(fullZone).split(',', 1)
                    yield region, name

        zonesByRegion: Mapping[str, Iterable[str]] \
                     = categorizedLists(splitZones())
        for region, zones in sorted(zonesByRegion.items()):
            yield region, sorted(zones)

class TimeZoneDisplay(Widget):
    def present(self, **kwargs: object) -> str:
        return time.tzname[bool(time.daylight)]

class ProjectTable(PropertiesTable):

    def iterRows(self, **kwargs: object) -> Iterator[XMLContent]:
        yield 'Project name', textInput(name='name', size=20)
        yield 'Targets', xhtml.br.join((
            textInput(name='targets', size=80),
            'Multiple targets must be space-separated'
            ))
        timezones = getKnownTimezones()
        yield 'Project time zone', (
            TimeZoneSelector.instance.present(timezones=timezones, **kwargs)
            if timezones else
            TimeZoneDisplay.instance
            )
        yield 'Multiple jobs limit', textInput(
            name='maxjobs', size=10, maxlength=6
            )
        yield 'Task priorities', checkBox(name='taskprio')[
            'User can specify priorities for tasks within a single job'
            ]
        yield 'Configuration tags', xhtml.br.join((
            textInput(name='tagkeys', size=80),
            'Multiple tags must be comma-separated'
            ))
        yield 'Embedding policy', xhtml.br.join((
            'Allow embedding of this SoftFab Control Center in web sites?',
            EmbeddingWidget.instance
            ))

class EmbeddingWidget(RadioTable):
    style = 'hollow'
    name = 'embed'
    columns = None,

    def iterOptions(self, **kwargs: object) -> Iterator[Sequence[XMLContent]]:
        yield EmbeddingPolicy.NONE, 'Never'
        yield EmbeddingPolicy.SELF, 'Same site only'
        yield EmbeddingPolicy.CUSTOM, 'Custom: ', (
            textInput(
                name='embedcustom', size=69,
                # The onchange event handler is there to make sure the right
                # radio button is activated when text is pasted into the edit
                # box from the context menu (right mouse button).
                onchange=f"form['{self.name}'][2].checked=true"
                ),
            xhtml.br,
            'You can enter one or more site filters, '
            'such as ', xhtml.code['https://*.example.com'],
            xhtml.br,
            'This is used as a ', xhtml.code['frame-ancestors'], ' rule '
            'in the ', xhtml.code['Content-Security-Policy'], ' header; ',
            xhtml.a(
                href='https://developer.mozilla.org/en-US/docs'
                '/Web/HTTP/Headers/Content-Security-Policy/frame-ancestors'
                )['full documentation at MDN'],
            )

    def formatOption(self, box: XML, cells: Sequence[XMLContent]) -> XMLContent:
        yield xhtml.label[box, ' ', cells[0]] + cells[1:]
