# SPDX-License-Identifier: BSD-3-Clause

from twisted.web import resource, util
from urllib.parse import urljoin

class PageRedirect(resource.Resource):
    '''Redirect to a fixed page.
    '''
    isLeaf = True

    def __init__(self, page):
        resource.Resource.__init__(self)
        self.page = page

    def render(self, request):
        # The Location header must have an absolute URL as its value (see
        # RFC-2616 section 14.30).
        url = urljoin(request.prePathURL(), self.page.encode())
        return util.redirectTo(url, request)

    def getChild(self, path, request):
        return self
