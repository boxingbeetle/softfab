# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, Redirect
from softfab.configlib import Config, configDB
from softfab.configview import SelectConfigsMixin, SimpleConfigTable
from softfab.formlib import actionButtons, hiddenInput, makeForm
from softfab.pageargs import DictArg, EnumArg, RefererArg, SetArg, StrArg
from softfab.projectlib import project
from softfab.selectlib import getCommonTags
from softfab.selectview import (
    SelectArgs, TagValueEditTable, textToValues, valuesToText
    )
from softfab.utils import encodeURL
from softfab.xmlgen import xhtml

from enum import Enum

class TagConfigTable(SimpleConfigTable):
    # Disable tabs and sorting because it would clear the forms.
    tabOffsetField = None
    sortField = None

    def getRecordsToQuery(self, proc):
        return proc.configs

parentPage = 'LoadExecute'

class ParentArgs(SelectArgs):
    parentQuery = RefererArg(parentPage, excludes = SelectArgs)

Actions = Enum('Actions', 'APPLY CANCEL')

class ConfigTags_GET(FabPage):
    icon = 'IconExec'
    iconModifier = IconModifier.EDIT
    description = 'Configuration Tags'
    linkDescription = False

    class Arguments(ParentArgs):
        pass

    class Processor(SelectConfigsMixin, PageProcessor):

        def getBackURL(self):
            parentQuery = self.args.parentQuery
            args = list(SelectArgs.subset(self.args).toQuery())
            if parentQuery is not None:
                args += parentQuery
            return '%s?%s' % ( parentPage, encodeURL(args) )

        def process(self, req):
            # pylint: disable=attribute-defined-outside-init
            self.notices = []

            self.findConfigs()

    def checkAccess(self, req):
        req.checkPrivilege('c/a')

    def iterDataTables(self, proc):
        yield TagConfigTable.instance

    def presentContent(self, proc):
        for notice in proc.notices:
            yield xhtml.p(class_ = 'notice')[ notice ]
        configs = proc.configs
        if configs:
            yield xhtml.h2[ 'Selected Configurations:' ]
            yield TagConfigTable.instance.present(proc=proc)

            yield xhtml.h2[ 'Common Selection Tags:' ]
            tagKeys = project.getTagKeys()
            commonTags = getCommonTags(tagKeys, configs)
            proc.getValues = lambda key: valuesToText(commonTags[key].values())
            yield makeForm(
                args=ParentArgs.subset(proc.args).override(
                    sel={config.getId() for config in configs}
                    )
                )[
                ConfigTagValueEditTable.instance,
                xhtml.p[ actionButtons(Actions) ],
                ( hiddenInput(name='commontags.%d' % index, value=tagName)
                  for index, tagKey in enumerate(tagKeys)
                  for tagName in commonTags[tagKey].keys() )
                ].present(proc=proc)
        else:
            yield (
                xhtml.h2[ 'No configurations selected' ],
                xhtml.p[ xhtml.a(href = proc.getBackURL())[
                    'Back to Configurations'
                    ] ]
                )

class ConfigTags_POST(ConfigTags_GET):

    class Arguments(ParentArgs):
        action = EnumArg(Actions)
        tagkeys = DictArg(StrArg())
        tagvalues = DictArg(StrArg())
        commontags = DictArg(SetArg())

    class Processor(ConfigTags_GET.Processor):

        def process(self, req):
            action = req.args.action
            if action is not Actions.APPLY:
                assert action is Actions.CANCEL, action
                raise Redirect(self.getBackURL())

            # pylint: disable=attribute-defined-outside-init
            self.notices = []
            self.findConfigs()
            if self.notices:
                return
            configs = self.configs

            req.checkPrivilegeForOwned(
                'c/m', configs,
                ( 'change tags on configurations owned by other users',
                    'change configuration tags' )
                )

            tagkeys = req.args.tagkeys
            tagvalues = req.args.tagvalues
            commontags = req.args.commontags

            # Determine changes between the submitted tags and the stored
            # tags.
            changes = {}
            for index, tagKey in tagkeys.items():
                storedValues = commontags.get(index, frozenset())
                values = dict(
                    Config.cache.toCanonical(tagKey, value)
                    for value in textToValues(tagvalues[index])
                    )
                changes[tagKey] = chValues = {}
                # Look for deleted tags.
                for cvalue in storedValues:
                    if cvalue not in values:
                        chValues[cvalue] = None
                # Look for added tags.
                for cvalue, dvalue in values.items():
                    if cvalue not in storedValues:
                        chValues[cvalue] = dvalue

            for config in configs:
                config.updateTags(changes)
                config._notify()

            # Case changes must be done on all instances of a tag;
            # even configurations that were not selected must be updated.
            # TODO: This is motivation to store the tag value only once
            #       in the DB instead of in every record tagged with it.
            for index, tagKey in tagkeys.items():
                for uvalue in textToValues(tagvalues[index]):
                    cvalue, dvalue = Config.cache.toCanonical(
                        tagKey, uvalue
                        )
                    if uvalue != dvalue:
                        for config in configDB:
                            if config.hasTagValue(tagKey, cvalue):
                                config.updateTags({
                                    tagKey: { cvalue: uvalue },
                                    })
                                config._notify()

    def presentContent(self, proc):
        if proc.notices:
            yield from super().presentContent(proc)
        else:
            yield xhtml.p[ 'The tags have been updated successfully.' ]
            yield xhtml.p[ xhtml.a(href = proc.getBackURL())[
                    'Back to Configurations'
                    ] ]

class ConfigTagValueEditTable(TagValueEditTable):
    valTitle = 'Common Tag Values'
    tagCache = Config.cache