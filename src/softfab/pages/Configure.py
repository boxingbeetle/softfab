# SPDX-License-Identifier: BSD-3-Clause

from typing import Sequence, Tuple

from softfab.FabPage import FabPage
from softfab.webgui import docLink
from softfab.xmlgen import XMLContent, xhtml


class Configure_GET(FabPage[FabPage.Processor, FabPage.Arguments]):
    icon = 'IconConfig'
    description = 'Configure'
    children = [
        'ProjectEdit', 'Design', 'UserList', 'Notifications', 'About'
        ]

    def checkAccess(self, req):
        pass

    def presentContent(self, proc: FabPage.Processor) -> XMLContent:
        descriptions = (
            ( 'Project',
                'Change overall settings, such as the project name '
                'and the list of targets.'
                ),
            ( 'Design',
                'Model the build and test process of your project: '
                'define products, frameworks, tasks and resources.'
                ),
            ( 'Users',
                'Add new users, change user passwords or '
                'change user roles.'
                ),
            ( 'Notifications',
                'Configure ways to stay informed of the current status '
                'of your project.'
                ),
            ( 'About',
                'Look up version information of your SoftFab installation '
                'and web browser.'
                ),
            ( 'Documentation',
                'Learn more details about the possibilities of SoftFab '
                'on the general '
                + docLink('/')[ 'documentation pages' ] + '.'
                ),
            ) # type: Sequence[Tuple[str, XMLContent]]
        return xhtml.dl[(
            ( xhtml.dt[name], xhtml.dd[descr] ) for name, descr in descriptions
            )]
