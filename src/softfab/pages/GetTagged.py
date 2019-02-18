# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import InvalidRequest, PageProcessor
from softfab.configlib import configDB
from softfab.pageargs import PageArgs, SetArg, StrArg
from softfab.schedulelib import scheduleDB
from softfab.taskdeflib import taskDefDB
from softfab.xmlgen import xml

subjectToDB = dict(
    config = configDB,
    schedule = scheduleDB,
    taskdef = taskDefDB,
    )

class GetTagged(ControlPage):

    class Arguments(PageArgs):
        subject = StrArg()
        key = SetArg()
        value = SetArg()

    def checkAccess(self, req):
        # Access check depends on subject, so check in Processor.
        pass

    class Processor(PageProcessor):

        def process(self, req):
            # Determine subject and access rights.
            try:
                db = subjectToDB[req.args.subject]
            except KeyError:
                raise InvalidRequest(
                    'Invalid subject type "%s"' % req.args.subject
                    )
            req.checkPrivilege(
                db.privilegeObject + '/l',
                'list %ss' % db.description
                )

            # Get tag cache from any record.
            # TODO: Refactor so tag cache can be fetched directly from "db".
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

    def writeReply(self, response, proc):
        matches = proc.matches
        subjectIdName = proc.args.subject + 'id'

        response.write(
            xml.matches[(
                xml.tag(**{
                    subjectIdName: recordId,
                    'key': key,
                    'value': value,
                    })
                for recordId, key, value in matches
                )].flattenIndented()
            )