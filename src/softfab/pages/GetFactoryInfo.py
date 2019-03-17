# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import PageProcessor
from softfab.config import rootURL
from softfab.databases import iterDatabases
from softfab.projectlib import getBootTime, project
from softfab.timeview import formatTimeAttr
from softfab.userlib import checkPrivilege, privileges
from softfab.version import version
from softfab.xmlgen import xml


class GetFactoryInfo_GET(ControlPage[ControlPage.Arguments,
                                     'GetFactoryInfo_GET.Processor']):

    def checkAccess(self, user):
        checkPrivilege(user, 'p/a')

        # Check that user has 'list' privileges for all databases.
        for priv in privileges.keys():
            if priv.endswith('/l'):
                checkPrivilege(user, priv)

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
