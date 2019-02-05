# SPDX-License-Identifier: BSD-3-Clause

from ControlPage import ControlPage
from Page import PageProcessor
from config import rootURL
from databases import iterDatabases
from projectlib import getBootTime, project
from timeview import formatTimeAttr
from userlib import privileges
from version import version
from xmlgen import xml

class GetFactoryInfo(ControlPage):

    def checkAccess(self, req):
        req.checkPrivilege('p/a')

        # Check that user has 'list' privileges for all databases.
        for priv in privileges.keys():
            if priv.endswith('/l'):
                req.checkPrivilege(priv)

    class Processor(PageProcessor):

        def process(self, req):
            pass

    def writeReply(self, response, proc):
        response.write(
            xml.factory(
                name = project['name'],
                url = rootURL,
                version = version,
                boottime = formatTimeAttr(getBootTime()),
                timezone = project['timezone'],
                )[
                ( xml.table(name = db.name, count = len(db))
                for db in iterDatabases() ),
                ]
            )
