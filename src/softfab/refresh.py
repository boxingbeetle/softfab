# SPDX-License-Identifier: BSD-3-Clause

from typing import Iterator, cast

from softfab.Page import PageProcessor
from softfab.webgui import Script, Widget


class RefreshScript(Script):

    def __init__(self, *widgets: Widget):
        targetIds = []
        for widget in widgets:
            targetId = widget.widgetId
            assert targetId is not None
            targetIds.append(targetId)
        self.targetIds = targetIds
        Script.__init__(self)

    def iterLines(self, **kwargs: object) -> Iterator[str]:
        proc = cast(PageProcessor, kwargs['proc'])
        args = dict(
            delayms = 2000,
            urls = ', '.join(
                f'"{proc.subItemRelURL(targetId)}"'
                for targetId in self.targetIds
                ),
            )

        # 'forceFetch' works around a problem in Chrome where the first
        # XMLHttpRequest made after navigating back to the page ignores
        # the 'must-revalidate' cache instruction.

        yield r'''
var refreshRequest;
var timeout;
var suspendRefresh = false;

window.addEventListener("pageshow", function(event) {
    refreshRequest = new XMLHttpRequest();
    refreshItemCount = -1;
    forceFetch = true;
    refreshNext();
});

document.addEventListener("selectionchange", function(event) {
    if (window.getSelection().isCollapsed) {
        if (suspendRefresh) {
            suspendRefresh = false;
            refreshItemCount = -1;
            refreshNext();
        }
    } else {
        if (!suspendRefresh) {
            suspendRefresh = true;
            window.clearTimeout(timeout);
        }
    }
});

function refreshRequestReady() {
    if (!suspendRefresh && refreshRequest.readyState == 4) {
        try {
            if (refreshRequest.status == 200) {
                var newNode = refreshRequest.responseXML.documentElement;
                var nodeId = newNode.getAttribute("id");
                var oldNode = document.getElementById(nodeId);
                if (oldNode) {
                    newNode = document.adoptNode(newNode);
                    oldNode.parentNode.replaceChild(newNode, oldNode);
                }
            }
        } catch(e) {
        }
        refreshNext();
    }
}

var refreshURLs = [ %(urls)s ];
var refreshItemCount;
var forceFetch;
function refreshNext() {
    refreshItemCount++;
    if (refreshItemCount < refreshURLs.length) {
        refreshRequest.open("GET", refreshURLs[refreshItemCount]);
        refreshRequest.setRequestHeader("Accept", "application/xhtml+xml");
        if (forceFetch) {
            refreshRequest.setRequestHeader("Cache-Control", "no-cache");
        }
        refreshRequest.onreadystatechange = refreshRequestReady;
        refreshRequest.send(null);
    } else {
        refreshItemCount = -1;
        forceFetch = false;
        timeout = window.setTimeout(refreshNext, %(delayms)d);
    }
}
''' % args
