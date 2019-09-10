# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import (
    Collection, Dict, FrozenSet, Iterator, Mapping, Optional, cast
)

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, Redirect
from softfab.configlib import Config, configDB
from softfab.configview import SelectConfigsMixin, SimpleConfigTable
from softfab.datawidgets import DataTable
from softfab.formlib import actionButtons, hiddenInput, makeForm
from softfab.pageargs import (
    ArgsT, DictArg, EnumArg, RefererArg, SetArg, StrArg
)
from softfab.projectlib import project
from softfab.request import Request
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

    def getRecordsToQuery(self, proc: PageProcessor) -> Collection[Config]:
        return cast(ConfigTagsBase.Processor, proc).configs

parentPage = 'LoadExecute'

class ParentArgs(SelectArgs):
    parentQuery = RefererArg(parentPage, shared=SelectArgs)

Actions = Enum('Actions', 'APPLY CANCEL')

class ConfigTagsBase(FabPage['ConfigTagsBase.Processor', ArgsT]):
    icon = 'IconExec'
    iconModifier = IconModifier.EDIT
    description = 'Configuration Tags'
    linkDescription = False

    class Processor(SelectConfigsMixin[ParentArgs], PageProcessor[ArgsT]):

        def process(self, req: Request[ArgsT], user: User) -> None:
            # pylint: disable=attribute-defined-outside-init
            self.notices = []

            self.findConfigs()

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'c/a')

    def iterDataTables(self, proc: Processor) -> Iterator[DataTable]:
        yield TagConfigTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ConfigTagsBase.Processor, kwargs['proc'])
        for notice in proc.notices:
            yield xhtml.p(class_ = 'notice')[ notice ]
        configs = proc.configs
        if configs:
            yield xhtml.h3[ 'Selected Configurations:' ]
            yield TagConfigTable.instance.present(**kwargs)

            yield xhtml.h3[ 'Common Selection Tags:' ]
            tagKeys = project.getTagKeys()
            commonTags = getCommonTags(tagKeys, configs)
            yield makeForm(
                args=ParentArgs.subset(proc.args).override(
                    sel={config.getId() for config in configs}
                    )
                )[
                ConfigTagValueEditTable.instance,
                xhtml.p[ actionButtons(Actions) ],
                ( hiddenInput(name=f'commontags.{index:d}', value=tagName)
                  for index, tagKey in enumerate(tagKeys)
                  for tagName in commonTags[tagKey].keys() )
                ].present(
                    getValues=lambda key:
                        valuesToText(commonTags[key].values()),
                    **kwargs
                    )
        else:
            yield (
                xhtml.h3[ 'No configurations selected' ],
                xhtml.p[ xhtml.a(href=proc.args.refererURL or parentPage)[
                    'Back to Configurations'
                    ] ]
                )

class ConfigTags_GET(ConfigTagsBase[ParentArgs]):

    class Arguments(ParentArgs):
        pass

class ConfigTags_POST(ConfigTagsBase['ConfigTags_POST.Arguments']):

    class Arguments(ParentArgs):
        action = EnumArg(Actions)
        tagkeys = DictArg(StrArg())
        tagvalues = DictArg(StrArg())
        commontags = DictArg(SetArg())

    class Processor(ConfigTagsBase.Processor):

        def process(self,
                    req: Request['ConfigTags_POST.Arguments'],
                    user: User
                    ) -> None:
            args = req.args
            action = args.action
            if action is not Actions.APPLY:
                assert action is Actions.CANCEL, action
                raise Redirect(args.refererURL or parentPage)

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

            tagkeys = cast(Mapping[str, str], args.tagkeys)
            tagvalues = cast(Mapping[str, str], args.tagvalues)
            commontags = cast(Mapping[str, FrozenSet[str]], args.commontags)

            # Determine changes between the submitted tags and the stored
            # tags.
            changes: Dict[str, Dict[str, Optional[str]]] = {}
            for index, tagKey in tagkeys.items():
                assert isinstance(tagKey, str), tagKey
                storedValues = commontags.get(index, frozenset())
                values = dict(
                    Config.cache.toCanonical(tagKey, value)
                    for value in textToValues(tagvalues[index])
                    )
                chValues: Dict[str, Optional[str]] = {}
                # Look for deleted tags.
                for cvalue in storedValues:
                    if cvalue not in values:
                        chValues[cvalue] = None
                # Look for added tags.
                for cvalue, dvalue in values.items():
                    if cvalue not in storedValues:
                        chValues[cvalue] = dvalue
                changes[tagKey] = chValues

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

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ConfigTagsBase.Processor, kwargs['proc'])
        if proc.notices:
            yield super().presentContent(**kwargs)
        else:
            yield xhtml.p[ 'The tags have been updated successfully.' ]
            yield xhtml.p[
                xhtml.a(href=proc.args.refererURL or parentPage)[
                    'Back to Configurations'
                    ]
                ]

class ConfigTagValueEditTable(TagValueEditTable):
    valTitle = 'Common Tag Values'
    tagCache = Config.cache
