# SPDX-License-Identifier: BSD-3-Clause

from urllib.parse import urljoin

from twisted.web.iweb import IRequest
from twisted.web.resource import Resource
from twisted.web.util import redirectTo


class PageRedirect(Resource):
    '''Redirect to a fixed page.
    '''
    isLeaf = True

    def __init__(self, page: str):
        Resource.__init__(self)
        self.page = page

    def render(self, request: IRequest) -> bytes:
        # The Location header must have an absolute URL as its value (see
        # RFC-2616 section 14.30).
        url = urljoin(request.prePathURL(), self.page.encode())
        return redirectTo(url, request)

    def getChild(self, path: str, request: IRequest) -> Resource:
        return self
