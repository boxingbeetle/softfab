# SPDX-License-Identifier: BSD-3-Clause

from softfab.ControlPage import ControlPage
from softfab.Page import PageProcessor
from softfab.pageargs import PageArgs, StrArg
from softfab.statuslib import StatusModelRegistry, StatusViewClient


class ObserveStatus_GET(ControlPage['ObserveStatus_GET.Arguments', 'ObserveStatus_GET.Processor']):
    streaming = True

    class Arguments(PageArgs):
        model = StrArg()
        format = StrArg()

    class Processor(PageProcessor):
        pass

    def checkAccess(self, req):
        # For a streaming request, we have to deal with permissions changing
        # while the request is open. Also, the model might not exist now but
        # come into existance later. So there is no point in checking access
        # here.
        pass

    def writeReply(self, response, proc):
        # TODO: Is it possible / useful to do part of this in the Processor?
        #       Be careful for changes that might occur between processing
        #       and presentation.
        # Walk the model path.
        # TODO: To avoid leaking information on the existance of certain nodes
        #       in the model tree to unprivileged clients, we should check
        #       permissions at every level in the tree. For example, if a
        #       user does not have permission to list products, he must get
        #       "permission denied" on "/products" instead of "not found" on
        #       "/products/abc".
        #       Sending any kind of update, even "permission denied", when the
        #       requested model changes still leaks information. Therefore
        #       if is best to implement "permission denied" as a special kind
        #       of model (or view), which can be exchanged for a real model
        #       when the user's permissions change.
        model = StatusModelRegistry.instance.getModel(proc.args.model)
        # Get a view on the model.
        view = model.createView(proc.args.format)
        # Create a Processor.
        client = StatusViewClient(response, view)
        client.startProducing()
        return client
