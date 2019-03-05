# SPDX-License-Identifier: BSD-3-Clause

from astroid import MANAGER, AssignName, ClassDef

def transform(cls):
    if any(base.qname() == 'zope.interface.interface.InterfaceClass'
           for base in cls.ancestors()):
        for method in cls.mymethods():
            args = method.args
            if len(args.args) == 0 or args.args[0].name != 'self':
                # Insert a 'self' argument.
                selfArg = AssignName(name='self', parent=args)
                args.args.insert(0, selfArg)
                args.annotations.insert(0, None)

def register(linter):
    pass

MANAGER.register_transform(ClassDef, transform)
