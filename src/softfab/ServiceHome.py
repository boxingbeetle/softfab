# SPDX-License-Identifier: BSD-3-Clause

from FabPage import FabPage
from xmlgen import xhtml

class ServiceHome(FabPage):
    icon = 'LogoHome'
    description = 'Home'
    children = [ 'ProjectEdit', 'ResourceIndex', 'UserList' ]

    def __init__(self):
        FabPage.__init__(self)

    def checkAccess(self, req):
        pass

    def presentContent(self, proc):
        return (
            xhtml.h2[ 'Service Home' ],
            xhtml.p[ 'No content so far' ]
            )
