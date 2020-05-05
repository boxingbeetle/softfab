# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import PageProcessor
from softfab.config import rootURL
from softfab.databases import iterDatabases
from softfab.projectlib import getBootTime, project
from softfab.request import Request
from softfab.response import Response
from softfab.timeview import formatTimeAttr
from softfab.userlib import User, checkPrivilege
from softfab.version import VERSION
from softfab.xmlgen import xml


class GetFactoryInfo_GET(ControlPage[ControlPage.Arguments,
                                     'GetFactoryInfo_GET.Processor']):

    def checkAccess(self, user: User) -> None:
        # Check that user has 'list' privileges for all databases.
        # For the singleton project DB, check the 'access' privilege instead.
        for db in iterDatabases():
            priv = f'{db.privilegeObject}/l'
            checkPrivilege(user, 'p/a' if priv == 'p/l' else priv)

    class Processor(PageProcessor[ControlPage.Arguments]):

        def process(self,
                    req: Request['GetFactoryInfo_GET.Arguments'],
                    user: User
                    ) -> None:
            pass

    async def writeReply(self, response: Response, proc: Processor) -> None:
        response.writeXML(
            xml.factory(
                name = project.name,
                url = rootURL,
                version = VERSION,
                boottime = formatTimeAttr(getBootTime()),
                timezone = project.timezone,
                )[
                ( xml.table(name = db.name, count = len(db))
                for db in iterDatabases() ),
                ]
            )
