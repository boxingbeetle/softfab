# SPDX-License-Identifier: BSD-3-Clause

from astroid import MANAGER, Decorators, ImportFrom, Name

def transform_decorators(decorators):
    """Replace @cachedProperty with @property.
    Since cachedProperty is essentially just a faster property,
    we can pretend it is the same thing so PyLint knows how to handle it.
    """
    for decorator in decorators.nodes:
        if isinstance(decorator, Name) and decorator.name == 'cachedProperty':
            decorator.name = 'property'

def transform_import_from(import_from):
    """Remove imports of cachedProperty.
    This avoids false positives about unused imports.
    """
    if import_from.modname == 'softfab.utils':
        for index, (org_name, as_name) in enumerate(import_from.names):
            if org_name == 'cachedProperty':
                del import_from.names[index]
                break

def register(linter):
    pass

MANAGER.register_transform(Decorators, transform_decorators)
MANAGER.register_transform(ImportFrom, transform_import_from)
