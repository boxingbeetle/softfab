# SPDX-License-Identifier: BSD-3-Clause

from softfab.FabPage import FabPage
from softfab.config import enableSecurity
from softfab.xmlgen import xhtml
from softfab.webgui import docLink

class Configure(FabPage):
    icon = 'Configure'
    description = 'Configure'
    children = [
        'ProjectEdit', 'Design', 'UserList', 'About'
        ]

    def checkAccess(self, req):
        pass

    def presentContent(self, proc):
        descriptions = [
            ( 'Project',
                'Change overall settings, such as the project name '
                'and the list of targets.'
                ),
            ( 'Design',
                'Model the build and test process of your project: '
                'define products, frameworks, tasks and resources.'
                ),
            ] + ([
            ( 'Users',
                'Add new users, change user passwords or '
                'change user roles.'
                    ),
            ] if enableSecurity else []) + [
            ( 'About',
                'Look up version information of your SoftFab installation '
                'and web browser.'
                ),
            ( 'Documentation',
                'Learn more details about the possibilities of SoftFab '
                'on the general '
                + docLink('/')[ 'documentation pages' ] + '.'
                )
            ]
        return xhtml.dl[(
            ( xhtml.dt[name], xhtml.dd[descr] ) for name, descr in descriptions
            )]
