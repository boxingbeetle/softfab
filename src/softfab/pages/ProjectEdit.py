# SPDX-License-Identifier: BSD-3-Clause

from urllib.parse import urlparse
import time

from softfab.EditPage import EditPage
from softfab.FabPage import IconModifier
from softfab.Page import PresentableError
from softfab.formlib import DropDownList, RadioTable, checkBox, textInput
from softfab.pageargs import ArgsCorrected, BoolArg, EnumArg, IntArg, StrArg
from softfab.projectlib import (
    EmbeddingPolicy, Project, _projectDB, defaultMaxJobs, getKnownTimezones,
    project
)
from softfab.setcalc import categorizedLists
from softfab.webgui import PropertiesTable, Widget, docLink
from softfab.xmlgen import xhtml


class ProjectEdit(EditPage):
    # FabPage constants:
    icon = 'Project1'
    iconModifier = IconModifier.NONE
    description = 'Project'

    # EditPage constants:
    elemTitle = 'Project Configuration'
    elemName = 'project configuration'
    db = _projectDB
    privDenyText = 'project configuration'
    useScript = False
    formId = 'project'
    autoName = 'singleton'

    class Arguments(EditPage.Arguments):
        name = StrArg('')
        targets = StrArg('')
        tagkeys = StrArg('')
        timezone = StrArg('')
        maxjobs = IntArg(defaultMaxJobs)
        taskprio = BoolArg()
        trselect = BoolArg()
        reqtag = BoolArg()
        embed = EnumArg(EmbeddingPolicy, None)
        embedcustom = StrArg('')

    class Processor(EditPage.Processor):

        def createElement(self, req, recordId, args, oldElement):
            assert args is not None
            assert oldElement is not None
            element = Project( {
                'name': args.name,
                'maxjobs': args.maxjobs,
                # TODO: Create a TimezoneArg?
                'timezone': decodeTimezone(args.timezone),
                'taskprio': args.taskprio,
                'trselect': args.trselect,
                'reqtag': args.reqtag,
                'embed': args.embed,
                'embedcustom': args.embedcustom,
                'version': oldElement['version'],
                } )
            element.setTargets(args.targets.split())
            element.setTagKeys(
                key
                for key in ( key.strip() for key in args.tagkeys.split(',') )
                if key
                )
            return element

        def _initArgs(self, element):
            if element is None:
                return {}
            else:
                return dict(
                    name = project.name,
                    targets = ' '.join(sorted(project.getTargets())),
                    tagkeys = ', '.join(project.getTagKeys()),
                    timezone = project.timezone,
                    maxjobs = project['maxjobs'],
                    taskprio = project['taskprio'],
                    trselect = project['trselect'],
                    reqtag = project['reqtag'],
                    embed = project['embed'],
                    embedcustom = project['embedcustom'],
                    )

        def _checkState(self):
            args = self.args

            # Check max job count.
            if args.maxjobs <= 0:
                raise PresentableError(xhtml.p[
                    'The value for multiple jobs limit (%d) is invalid; '
                    'it must be a positive integer.' % args.maxjobs
                    ])

            # Check timezone.
            # Since timezone is selected from a drop-down list, under normal
            # circumstances it will always be valid.
            timezone = decodeTimezone(args.timezone)
            knownZones = getKnownTimezones()
            if knownZones and timezone not in knownZones:
                raise PresentableError(xhtml.p[
                    'Unknown timezone "%s".' % timezone
                    ])

            # Check site filters.
            siteFilters = []
            for siteFilter in args.embedcustom.split():
                if ';' in siteFilter:
                    # Semicolon is used as a separator in the CSP header.
                    raise PresentableError(xhtml.p[
                        'Illegal character ";" in site filter "%s"'
                        % siteFilter
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
                        'Invalid site filter "%s": %s' % (siteFilter, ex)
                        ])
                for name in ('path', 'params', 'query', 'fragment',
                        'username', 'password'):
                    if getattr(url, name):
                        raise PresentableError(xhtml.p[
                            'Site filter "%s" contains %s, '
                            'which is not supported'
                            % (siteFilter, name)
                            ])
                scheme = url.scheme
                netloc = url.netloc
                if scheme and netloc:
                    siteFilters.append('%s://%s' % (scheme, netloc))
                elif scheme:
                    siteFilters.append('%s:' % scheme)
                elif netloc:
                    siteFilters.append(netloc)
                else:
                    # Note: I don't know what filter would parse like this,
                    #       but handle it just in case.
                    raise PresentableError(xhtml.p[
                        'Site filter "%s" contains no information' % siteFilter
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

    def getFormContent(self, proc):
        yield ProjectTable.instance
        yield xhtml.p[
            'For help about above project values, please read the '
            'document: ', docLink('/reference/user-manual/#configure')[
                'Configure project' ], '.'
            ]

def decodeTimezone(tzStr):
    if tzStr:
        return tzStr.replace(',', '/').replace(' ', '_')
    else:
        return None

def encodeTimezone(timezone):
    if timezone:
        return timezone.replace('/', ',').replace('_', ' ')
    else:
        return None

class TimeZoneSelector(DropDownList):
    name = 'timezone'
    def getActive(self, proc, **kwargs):
        return encodeTimezone(proc.args.timezone)
    def iterOptions(self, timezones, **kwargs):
        zonesByRegion = categorizedLists(
            encodeTimezone(fullZone).split(',', 1)
            for fullZone in timezones
            if '/' in fullZone
            )
        for region, zones in sorted(zonesByRegion.items()):
            yield region, sorted(zones)

class TimeZoneDisplay(Widget):
    def present(self, **kwargs):
        return time.tzname[bool(time.daylight)]

class ProjectTable(PropertiesTable):

    def iterRows(self, **kwargs):
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
        yield 'Task Runner selection', checkBox(name='trselect')[
            'User can specify a subset of Task Runners for a job/task'
            ]
        yield 'Requirement tracing', checkBox(name='reqtag')[
            'Link your task definitions with a requirements database'
            ' (experimental)'
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

    def iterOptions(self, **kwargs):
        yield EmbeddingPolicy.NONE, 'Never'
        yield EmbeddingPolicy.SELF, 'Same site only'
        yield EmbeddingPolicy.CUSTOM, 'Custom: ', (
            textInput(
                name='embedcustom', size=69,
                # The onchange event handler is there to make sure the right
                # radio button is activated when text is pasted into the edit
                # box from the context menu (right mouse button).
                onchange="form['%s'][2].checked=true" % self.name
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

    def formatOption(self, box, cells):
        yield xhtml.label[box, ' \u00A0', cells[0]] + cells[1:]
