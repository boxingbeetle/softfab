# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import Iterator

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, Redirect
from softfab.configlib import Config, configDB
from softfab.configview import SelectConfigsMixin, SimpleConfigTable
from softfab.datawidgets import DataTable
from softfab.formlib import actionButtons, hiddenInput, makeForm
from softfab.pageargs import DictArg, EnumArg, RefererArg, SetArg, StrArg
from softfab.projectlib import project
from softfab.selectlib import getCommonTags
from softfab.selectview import (
    SelectArgs, TagValueEditTable, textToValues, valuesToText
)
from softfab.userlib import User, checkPrivilege, checkPrivilegeForOwned
from softfab.xmlgen import XMLContent, xhtml


class TagConfigTable(SimpleConfigTable):
    # Disable tabs and sorting because it would clear the forms.
    tabOffsetField = None
    sortField = None

    def getRecordsToQuery(self, proc):
        return proc.configs

parentPage = 'LoadExecute'

class ParentArgs(SelectArgs):
    parentQuery = RefererArg(parentPage, shared=SelectArgs)

Actions = Enum('Actions', 'APPLY CANCEL')

class ConfigTagsBase(FabPage['ConfigTagsBase.Processor', FabPage.Arguments]):
    icon = 'IconExec'
    iconModifier = IconModifier.EDIT
    description = 'Configuration Tags'
    linkDescription = False

    class Processor(SelectConfigsMixin, PageProcessor[ParentArgs]):

        def getBackURL(self):
            args = self.args
            query = args.parentQuery.override(SelectArgs.subset(args))
            return '%s?%s' % (parentPage, query.toURL())

        def process(self, req, user):
            # pylint: disable=attribute-defined-outside-init
            self.notices = []

            self.findConfigs()

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'c/a')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield TagConfigTable.instance

    def presentContent(self, proc: Processor) -> XMLContent:
        for notice in proc.notices:
            yield xhtml.p(class_ = 'notice')[ notice ]
        configs = proc.configs
        if configs:
            yield xhtml.h2[ 'Selected Configurations:' ]
            yield TagConfigTable.instance.present(proc=proc)

            yield xhtml.h2[ 'Common Selection Tags:' ]
            tagKeys = project.getTagKeys()
            commonTags = getCommonTags(tagKeys, configs)
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
                ].present(
                    proc=proc,
                    getValues=lambda key: valuesToText(commonTags[key].values())
                    )
        else:
            yield (
                xhtml.h2[ 'No configurations selected' ],
                xhtml.p[ xhtml.a(href = proc.getBackURL())[
                    'Back to Configurations'
                    ] ]
                )

class ConfigTags_GET(ConfigTagsBase):

    class Arguments(ParentArgs):
        pass

class ConfigTags_POST(ConfigTagsBase):

    class Arguments(ParentArgs):
        action = EnumArg(Actions)
        tagkeys = DictArg(StrArg())
        tagvalues = DictArg(StrArg())
        commontags = DictArg(SetArg())

    class Processor(ConfigTagsBase.Processor):

        def process(self, req, user):
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

            checkPrivilegeForOwned(
                user, 'c/m', configs,
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

    def presentContent(self, proc: ConfigTagsBase.Processor) -> XMLContent:
        if proc.notices:
            yield super().presentContent(proc)
        else:
            yield xhtml.p[ 'The tags have been updated successfully.' ]
            yield xhtml.p[ xhtml.a(href = proc.getBackURL())[
                    'Back to Configurations'
                    ] ]

class ConfigTagValueEditTable(TagValueEditTable):
    valTitle = 'Common Tag Values'
    tagCache = Config.cache
