# SPDX-License-Identifier: BSD-3-Clause

from typing import Sequence, Tuple

from softfab.FabPage import FabPage
from softfab.userlib import User
from softfab.xmlgen import XMLContent, xhtml


class Configure_GET(FabPage[FabPage.Processor[FabPage.Arguments],
                            FabPage.Arguments]):
    icon = 'IconConfig'
    description = 'Configure'
    children = [
        'ProjectEdit', 'Design', 'UserList', 'Notifications', 'About'
        ]

    def checkAccess(self, user: User) -> None:
        pass

    def presentContent(self, **kwargs: object) -> XMLContent:
        descriptions: Sequence[Tuple[str, str, XMLContent]] = (
            ( 'Project', 'ProjectEdit',
                'Change overall settings, such as the project name '
                'and the list of targets.'
                ),
            ( 'Design', 'Design',
                'Model the build and test process of your project: '
                'define products, frameworks, tasks and resources.'
                ),
            ( 'Users', 'UserList',
                'Add new users, change user passwords or '
                'change user roles.'
                ),
            ( 'Notifications', 'Notifications',
                'Configure ways to stay informed of the current status '
                'of your project.'
                ),
            ( 'About', 'About',
                'Look up version information of your SoftFab installation '
                'and web browser.'
                ),
            )
        return xhtml.dl(class_='toc')[(
            ( xhtml.dt[xhtml.a(href=url)[name]], xhtml.dd[descr] )
            for name, url, descr in descriptions
            )]
