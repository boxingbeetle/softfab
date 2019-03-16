# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC
from typing import ClassVar

from softfab.jobview import combinedStatus
from softfab.pagelinks import createTaskInfoLink, createTaskRunnerDetailsLink
from softfab.productdeflib import ProductType
from softfab.taskview import getTaskStatus
from softfab.utils import abstract
from softfab.webgui import Table, cell, row
from softfab.xmlgen import txt, xhtml


def formatLocator(product, locator, finishedTask):
    if locator is None:
        return 'unavailable' if finishedTask else 'not yet'
    elif product.getType() is ProductType.URL:
        return xhtml.a(href = locator)[ locator ]
    elif product.getType() is ProductType.TOKEN:
        return 'token was produced'
    else:
        return txt(locator)

def getProductStatus(job, name):
    '''Returns the status of the product with the given name.
    Raises KeyError if there is no product with the given name in the given job.
    '''
    product = job.getProduct(name)
    if not product.isCombined():
        if product.isBlocked():
            return 'cancelled'
        elif product.isAvailable():
            # In the case of multiple producers, we don't know which
            # producer created the default locator, so there is no
            # obviously right choice for the status.
            # So we choose something simple instead.
            return 'ok'
        # Not blocked and not available, so must be idle or busy.
        # The generic case can handle that just fine.
    return combinedStatus(
        getTaskStatus(task) for task in job.getProducers(name)
        )

# TODO: This is similar to configview.InputTable.
class ProductTable(Table, ABC):
    style = 'nostrong'
    hideWhenEmpty = True

    label = abstract # type: ClassVar[str]
    showProducers = abstract # type: ClassVar[bool]
    showConsumers = abstract # type: ClassVar[bool]
    showColors = abstract # type: ClassVar[bool]

    def getProducts(self, proc):
        raise NotImplementedError

    def iterColumns(self, proc, **kwargs):
        # TODO: hasLocal is computed twice: here and in iterRows().
        products = self.getProducts(proc)
        hasLocal = any(prod.isLocal() for prod in products)
        yield self.label
        if hasLocal:
            yield 'Local at'
        if self.showProducers:
            yield 'Producer'
        if self.showConsumers:
            yield 'Consumers'
        yield 'Locator'

    def filterProducers(self, proc, producers): # pylint: disable=unused-argument
        '''Iterates through those producer task names that should be shown in
        this table.
        The default implementation does not filter out any producers.
        '''
        return iter(producers)

    def iterRows(self, *, proc, **kwargs):
        job = proc.job
        jobId = job.getId()
        products = self.getProducts(proc)
        hasLocal = any(prod.isLocal() for prod in products)
        for product in products:
            productName = product.getName()
            potentialProducers = set(
                task.getName()
                for task in job.getProducers(productName)
                )
            actualProducers = set(
                taskName
                for taskName, locator_ in product.getProducers()
                )
            # For user inputs, actualProducers includes tasks that are not
            # in potentialProducers.
            producers = sorted(
                self.filterProducers(proc, potentialProducers | actualProducers)
                )
            if self.showColors:
                rowStyle = getProductStatus(job, productName)
            else:
                rowStyle = None

            consumers = sorted(job.getConsumers(productName))

            first = True
            for taskName in producers:
                task = job.getTask(taskName)
                if task is None:
                    # No actual producer; this must be an input product.
                    producerStatus = 'ok'
                    finishedTask = True
                else:
                    producerStatus = getTaskStatus(task)
                    finishedTask = task.isExecutionFinished()

                cells = []
                if first:
                    cells.append(cell(rowspan = len(producers))[
                        productName
                        ])
                if first and hasLocal:
                    cells.append(cell(rowspan = len(producers))[
                        createTaskRunnerDetailsLink(
                            ( product.getLocalAt() or '?' )
                            if product.isLocal() and
                                not product.isBlocked() else None
                            )
                        ])
                if self.showProducers:
                    cells.append(cell(
                        class_ = producerStatus if self.showColors else None
                        )[
                        '(job input)' if task is None else
                            createTaskInfoLink(jobId, taskName)
                        ])
                if first and self.showConsumers:
                    cells.append(cell(rowspan = len(producers))[
                        xhtml.br.join(
                            createTaskInfoLink(jobId, consumer.getName())
                            for consumer in consumers
                            )
                        ])
                locator = product.getLocator(taskName)
                if locator is None and not actualProducers:
                    # For old jobs, only one locator per product was stored.
                    locator = product.getLocator()
                if not self.showColors:
                    locatorStyle = None
                elif locator is None:
                    assert task is not None, \
                        'input without locator: %s' % taskName
                    if finishedTask:
                        locatorStyle = 'cancelled'
                    else:
                        locatorStyle = getTaskStatus(task)
                else:
                    locatorStyle = producerStatus
                cells.append(cell(class_ = locatorStyle)[
                    formatLocator(product, locator, finishedTask)
                    ])
                yield row(class_ = rowStyle)[cells]
                first = False
