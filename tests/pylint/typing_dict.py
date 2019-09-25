# SPDX-License-Identifier: BSD-3-Clause

from astroid import MANAGER, ClassDef, Name, Subscript

def transform(cls):
    """Pretend that any class inheriting from 'Dict' also inherits from 'dict'.
    Works around PyLint not knowing about operations on the 'Dict' class.
    https://github.com/PyCQA/pylint/issues/3129
    """
    for index, base in enumerate(cls.bases):
        if isinstance(base, Subscript):
            if isinstance(base.value, Name):
                if base.value.name == 'Dict':
                    cls.bases.append(Name('dict', parent=cls))

def register(linter):
    pass

MANAGER.register_transform(ClassDef, transform)
