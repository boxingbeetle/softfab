# SPDX-License-Identifier: BSD-3-Clause

from softfab.Page import FabResource
from softfab.UIPage import UIPage
from softfab.authentication import NoAuthPage
from softfab.xmlgen import xhtml

import gc

class Garbage(UIPage, FabResource):
    # This page is only shown in debug mode.
    authenticationWrapper = NoAuthPage

    def __init__(self):
        super().__init__()
        # Save all objects found during mark-and-sweep collection.
        # Using this feature, this page can print objects that are causing
        # memory leaks.
        # Note that this page is only available if config.debugSupport is True.
        gc.set_debug(gc.DEBUG_SAVEALL)

    def checkAccess(self, req):
        pass

    def fabTitle(self, proc):
        return 'Garbage Overview'

    def presentContent(self, proc):
        nrCollected = gc.collect()
        yield xhtml.p[ '%d items collected' % nrCollected ]

        for i in range(nrCollected):
            # Note: Do not store gc.garbage[i] in a local variable, because
            #       that would add a referrer.
            referrers = gc.get_referrers(gc.garbage[i])
            # The gc.garbage list is always one of the referrers, but we do
            # not want to see it.
            referrers.remove(gc.garbage)
            yield (
                xhtml.h2[ 'Item %d' % i ],
                xhtml.table[ xhtml.tbody[
                    xhtml.tr[ xhtml.td[ repr(gc.garbage[i]) ]]
                    ]],
                xhtml.p[ 'Referred by:' ],
                xhtml.table[
                    xhtml.tbody[(
                        # Note: Generator expressions do not put their iteration
                        #       variable in the outside scope, unlike list
                        #       comprehensions.
                        xhtml.tr[ xhtml.td[ repr(referrer) ]]
                        for referrer in referrers
                        )]
                    ]
                )
            del referrers
