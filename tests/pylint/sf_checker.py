# SPDX-License-Identifier: BSD-3-Clause

from pylint.interfaces import IAstroidChecker
from pylint.checkers import BaseChecker

class SoftFabChecker(BaseChecker):
    '''SoftFab specific checks for PyLint.
    '''
    __implements__ = IAstroidChecker

    name = 'softfab'
    msgs = {
        'E9001': (
            'Inner function references itself',
            'inner-function-ref-cycle',
            'Issued when a function within a function contains a reference '
            'to itself; this creates a reference cycle which prevents the '
            'function from being garbage collected by the reference counting '
            'collector.'
            ),
        'W9001' : (
            'Class attribute %r is abstract in class %r but is not overridden',
            'abstract-class-attribute',
            'Issued when an abstract class attribute (see utils.abstract) is '
            'not overridden in concrete class.'
            ),
        }
    options = ()
    priority = -1

    def __init__(self, linter):
        BaseChecker.__init__(self, linter)
        self.active_functions = []

    def visit_functiondef(self, node):
        self.active_functions.append(node)

    def leave_functiondef(self, node):
        active = self.active_functions.pop()
        assert active is node

    def visit_name(self, node):
        scope, assignments = node.lookup(node.name)
        if scope in self.active_functions[ : -1]:
            for assignment in assignments:
                if assignment == self.active_functions[-1]:
                    self.add_message('E9001', node = assignment)

    def visit_classdef(self, node):
        abstractAttrs = {}
        for ancestor in node.ancestors():
            for name, values in ancestor.locals.items():
                for value in values:
                    if hasattr(value, 'assigned_stmts'):
                        for assigned in value.assigned_stmts():
                            if getattr(assigned, 'name', None) == 'abstract':
                                abstractAttrs[name] = ancestor.name
        for attrName, defClassName in sorted(abstractAttrs.items()):
            if attrName not in node.locals:
                for attr in node.local_attr(attrName):
                    for assigned in attr.assigned_stmts():
                        if getattr(assigned, 'name', None) == 'abstract':
                            self.add_message(
                                'W9001',
                                args = (attrName, defClassName),
                                node = node
                                )

def register(linter):
    linter.register_checker(SoftFabChecker(linter))
