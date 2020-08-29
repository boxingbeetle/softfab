# SPDX-License-Identifier: BSD-3-Clause

"""
Test the atomicWrite context manager.

We do not test system shutdowns, since that would require a very complex
test setup.

We do not test abnormal program termination, but that could be implemented
later by spawning a process to perform the file modifications.
"""

from pytest import mark, raises

from softfab.utils import atomicWrite


class IntentionalError(Exception):
    """Thrown to test handling of arbitrary errors."""

def forceError(out):
    raise IntentionalError

def earlyClose(out):
    out.close()

def writeFile(openFunc, path, line, postWrite=None):
    """Opens a text file at the given path using the given function and
    writes the given line to it.
    'postWrite' is an optional function that will be called with the open
    file object after the line has been written.
    """
    with openFunc(path, 'w') as out:
        out.write(line)
        if postWrite is not None:
            postWrite(out)

def checkFile(path, line):
    """Reads the text file at the given path and checks whether it contains
    a single line containing the given text.
    """
    with open(path, 'r') as inp:
        lines = inp.readlines()
    assert len(lines) == 1
    assert lines[0] == line

def testNonAtomic(tmp_path):
    """Sanity check to demonstrate that the tests will catch problems when
    using non-atomic file operations.
    """
    path = str(tmp_path / 'testfile.txt')
    oldContent = 'test0100NonAtomic init\n'
    newContent = 'test0100NonAtomic overwrite\n'
    writeFile(open, path, oldContent)
    with raises(IntentionalError):
        writeFile(open, path, newContent, forceError)
    with open(path, 'r') as inp:
        lines = inp.readlines()
    assert not (len(lines) == 1 and lines[0] == oldContent)

def testAtomicNoError(tmp_path):
    """Checks that atomic write will update the file if no errors occur."""
    path = str(tmp_path / 'testfile.txt')
    oldContent = 'test0200AtomicNoError init\n'
    newContent = 'test0200AtomicNoError overwrite\n'
    writeFile(open, path, oldContent)
    writeFile(atomicWrite, path, newContent)
    checkFile(path, newContent)

def testAtomicError(tmp_path):
    """Checks that atomic write will not update the file if an error occurs."""
    path = str(tmp_path / 'testfile.txt')
    oldContent = 'test0210AtomicError init\n'
    newContent = 'test0210AtomicError overwrite\n'
    writeFile(open, path, oldContent)
    with raises(IntentionalError):
        writeFile(atomicWrite, path, newContent, forceError)
    checkFile(path, oldContent)

def testAtomicEarlyClose(tmp_path):
    """Checks that the user closing the file is handled as an error."""
    path = str(tmp_path / 'testfile.txt')
    oldContent = 'test0300UserClose init\n'
    newContent = 'test0300UserClose overwrite\n'
    writeFile(open, path, oldContent)
    with raises(ValueError):
        writeFile(atomicWrite, path, newContent, earlyClose)
    checkFile(path, oldContent)

@mark.parametrize('mode', ['q', 'r', 'a', 'w+b'])
def testAtomicBadMode(tmp_path, mode):
    """Checks handling of invalid open modes."""
    path = str(tmp_path / 'testfile.txt')
    with raises(ValueError):
        with atomicWrite(path, mode):
            pass

def testAtomicBadDir(tmp_path):
    """Checks open a file in a non-existing directory."""
    path = str(tmp_path / 'nosuchdir' / 'testfile.txt')
    with raises(FileNotFoundError):
        with atomicWrite(path, 'w'):
            pass
