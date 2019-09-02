# SPDX-License-Identifier: BSD-3-Clause

from logging import Logger
from types import ModuleType

from twisted.web.http import Request as TwistedRequest
from twisted.web.resource import Resource

from softfab.utils import iterModules


class WebhookResource(Resource):

    def __init__(self, webhook: ModuleType):
        super().__init__()
        self.webhook = webhook

    def render_POST(self, request: TwistedRequest) -> bytes:
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
        from softfab.databaselib import createUniqueId
        with open(createUniqueId() + '.dump', mode='wb') as out:
            for key, values in request.requestHeaders.getAllRawHeaders():
                for value in values:
                    out.write(b'%s: %s\n' % (key, value))
            out.write(b'---\n')
            while True:
                data = request.content.read()
                if not data:
                    break
                out.write(data)
        return b'Received\n'

class WebhookIndexResource(Resource):

    def render_GET(self, request: TwistedRequest) -> bytes:
        request.setHeader(b'Content-Type', b'text/plain; charset=UTF-8')
        return b'\n'.join(sorted(self.children)) + b'\n'

def createWebhooks(log: Logger) -> Resource:
    index = WebhookIndexResource()
    for name, module in iterModules(__name__, log):
        index.putChild(name.encode(), WebhookResource(module))
    return index
