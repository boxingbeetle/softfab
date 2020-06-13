# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
from typing import (
    AbstractSet, Any, ClassVar, Collection, Dict, FrozenSet, Iterator, List,
    Mapping, cast
)

from softfab.FabPage import FabPage, IconModifier
from softfab.Page import PageProcessor, Redirect
from softfab.configlib import Config, ConfigDB
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
from softfab.userlib import (
    User, UserDB, checkPrivilege, checkPrivilegeForOwned
)
from softfab.xmlgen import XMLContent, xhtml


class TagConfigTable(SimpleConfigTable):
    # Disable tabs and sorting because it would clear the forms.
    tabOffsetField = None
    sortField = None

    def getRecordsToQuery(self,
                          proc: PageProcessor[SelectArgs]
                          ) -> Collection[Config]:
        return cast(ConfigTagsBase.Processor[SelectArgs], proc).configs

parentPage = 'LoadExecute'

class ParentArgs(SelectArgs):
    parentQuery = RefererArg(parentPage, shared=SelectArgs)

Actions = Enum('Actions', 'APPLY CANCEL')

class ConfigTagsBase(FabPage['ConfigTagsBase.Processor[ArgsT]', ArgsT]):
    icon = 'IconExec'
    iconModifier = IconModifier.EDIT
    description = 'Configuration Tags'
    linkDescription = False

    class Processor(SelectConfigsMixin[ParentArgs], PageProcessor[ArgsT]):

        configDB: ClassVar[ConfigDB]

        notices: List[str]

        async def process(self, req: Request[ArgsT], user: User) -> None:
            self.notices = []

            self.findConfigs(self.configDB)

    def checkAccess(self, user: User) -> None:
        checkPrivilege(user, 'c/a')

    def iterDataTables(self,
                       proc: Processor[ArgsT]
                       ) -> Iterator[DataTable[Any]]:
        yield TagConfigTable.instance

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ConfigTagsBase.Processor[ArgsT], kwargs['proc'])
        for notice in proc.notices:
            yield xhtml.p(class_ = 'notice')[ notice ]
        configs = proc.configs
        if configs:
            yield xhtml.h3[ 'Selected Configurations:' ]
            yield TagConfigTable.instance.present(**kwargs)

            yield xhtml.h3[ 'Common Selection Tags:' ]
            tagKeys = project.getTagKeys()
            commonTags = getCommonTags(tagKeys,
                                       (config.tags for config in configs))
            yield makeForm(
                args=ParentArgs.subset(proc.args).override(
                    sel={config.getId() for config in configs}
                    )
                )[
                ConfigTagValueEditTable.instance,
                xhtml.p[ actionButtons(Actions) ],
                ( hiddenInput(name=f'commontags.{index:d}', value=tagName)
                  for index, tagKey in enumerate(tagKeys)
                  for tagName in commonTags[tagKey] )
                ].present(
                    getValues=lambda key: valuesToText(commonTags[key]),
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

    class Processor(ConfigTagsBase.Processor[Arguments]):

        userDB: ClassVar[UserDB]

        async def process(self,
                          req: Request['ConfigTags_POST.Arguments'],
                          user: User
                          ) -> None:
            args = req.args
            action = args.action
            if action is not Actions.APPLY:
                assert action is Actions.CANCEL, action
                raise Redirect(args.refererURL or parentPage)

            configDB = self.configDB
            self.notices = []
            self.findConfigs(configDB)
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
            additions: Dict[str, AbstractSet[str]] = {}
            removals: Dict[str, AbstractSet[str]] = {}
            for index, tagKey in tagkeys.items():
                storedValues = commontags.get(index, frozenset())
                values = textToValues(tagvalues[index])
                additions[tagKey] = values - storedValues
                removals[tagKey] = storedValues - values

            for config in configs:
                # TODO: Wrap update() call in context manager.
                for tagKey in tagkeys.values():
                    config.tags.updateTags(tagKey, additions[tagKey],
                                                   removals[tagKey])
                configDB.update(config)

    def presentContent(self, **kwargs: object) -> XMLContent:
        proc = cast(ConfigTags_POST.Processor, kwargs['proc'])
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
