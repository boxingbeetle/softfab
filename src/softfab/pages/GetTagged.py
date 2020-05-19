# SPDX-License-Identifier: BSD-3-Clause

from typing import Mapping, Optional, cast

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.configlib import configDB
from softfab.databaselib import Database
from softfab.pageargs import PageArgs, SetArg, StrArg
from softfab.request import Request
from softfab.response import Response
from softfab.schedulelib import scheduleDB
from softfab.selectlib import SelectableRecordABC, TagCache
from softfab.taskdeflib import taskDefDB
from softfab.userlib import User, checkPrivilege
from softfab.xmlgen import xml

subjectToDB: Mapping[str, Database[SelectableRecordABC]] = dict(
    config = cast(Database[SelectableRecordABC], configDB),
    schedule = cast(Database[SelectableRecordABC], scheduleDB),
    taskdef = cast(Database[SelectableRecordABC], taskDefDB),
    )

class GetTagged_GET(ControlPage['GetTagged_GET.Arguments',
                                'GetTagged_GET.Processor']):

    class Arguments(PageArgs):
        subject = StrArg()
        key = SetArg()
        value = SetArg()

    def checkAccess(self, user: User) -> None:
        # Access check depends on subject, so check in Processor.
        pass

    class Processor(PageProcessor['GetTagged_GET.Arguments']):

        async def process(self,
                          req: Request['GetTagged_GET.Arguments'],
                          user: User
                          ) -> None:
            # Determine subject and access rights.
            try:
                db = subjectToDB[req.args.subject]
            except KeyError:
                raise InvalidRequest(
                    f'Invalid subject type "{req.args.subject}"'
                    )
            checkPrivilege(
                user, db.privilegeObject + '/l',
                f'list {db.description}s'
                )

            # Get tag cache from any record.
            # TODO: Refactor so tag cache can be fetched directly from "db".
            tagCache: Optional[TagCache]
            for recordId in db.keys():
                tagCache = db[recordId].cache
                break
            else:
                tagCache = None

            # Determine keys and values.
            keys = req.args.key
            values = req.args.value
            if tagCache is not None:
                # Restrict keys to those that actually exist.
                if keys:
                    keys = keys & set(tagCache.getKeys())
                else:
                    keys = set(tagCache.getKeys())

            # Filter records.
            matches = []
            for record in db.values():
                for key in keys:
                    if record.hasTagKey(key):
                        recordId = record.getId()
                        if values:
                            for value in values:
                                cvalue, dvalue = \
                                    record.cache.toCanonical(key, value)
                                if record.hasTagValue(key, cvalue):
                                    matches.append(( recordId, key, dvalue ))
                        else:
                            for value in record.getTagValues(key):
                                matches.append(( recordId, key, value ))

            # pylint: disable=attribute-defined-outside-init
            self.matches = matches

    async def writeReply(self, response: Response, proc: Processor) -> None:
        matches = proc.matches
        subjectIdName = proc.args.subject + 'id'

        response.writeXML(
            xml.matches[(
                xml.tag(**{
                    subjectIdName: recordId,
                    'key': key,
                    'value': value,
                    })
                for recordId, key, value in matches
                )]
            )
