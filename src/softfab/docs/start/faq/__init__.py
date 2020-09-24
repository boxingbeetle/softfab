# SPDX-License-Identifier: BSD-3-Clause

from softfab.frameworklib import Framework
from softfab.graphview import ExecutionGraphBuilder
from softfab.productdeflib import ProductDef

button = 'FAQ'
children = ()
icon = 'IconDocs'

graphBuilders = (
    ExecutionGraphBuilder(
        'build',
        links=False,
        products=(
            ProductDef.create('BINARY'),
            ),
        frameworks=(
            Framework.create('build', (), ('BINARY',)),
            Framework.create('test', ('BINARY',), ())
            ),
        ),
    )
