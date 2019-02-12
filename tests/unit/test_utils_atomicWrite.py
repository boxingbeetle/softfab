# SPDX-License-Identifier: BSD-3-Clause

from softfab.utils import atomicWrite

import unittest

class IntentionalError(Exception):
    '''Thrown to test handling of arbitrary errors.'''
    pass

def forceError(out):
    raise IntentionalError

def earlyClose(out):
    out.close()

class TestAtomicWrite(unittest.TestCase):
    '''Test the atomicWrite context manager.
    We do not test system shutdowns, since that would require a very complex
    test setup.
    We do not test abnormal program termination, but that could be implemented
    later by spawning a process to perform the file modifications.
    '''

    def writeFile(self, openFunc, path, line, postWrite=None):
        '''Opens a text file at the given path using the given function and
        writes the given line to it.
        'postWrite' is an optional function that will be called with the open
        file object after the line has been written.
        '''
        with openFunc(path, 'w') as out:
            out.write(line)
            if postWrite is not None:
                postWrite(out)

    def checkFile(self, path, line):
        '''Reads the text file at the given path and checks whether it contains
        a single line containing the given text.
        '''
        with open(path, 'r') as inp:
            lines = inp.readlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], line)

    def test0100NonAtomic(self):
        '''Sanity check to demonstrate that the tests will catch problems when
        using non-atomic file operations.
        '''
        oldContent = 'test0100NonAtomic init\n'
        newContent = 'test0100NonAtomic overwrite\n'
        self.writeFile(open, 'testfile.txt', oldContent)
        self.assertRaises(IntentionalError, lambda:
            self.writeFile(open, 'testfile.txt', newContent, forceError)
            )
        with open('testfile.txt', 'r') as inp:
            lines = inp.readlines()
        self.assertFalse(len(lines) == 1 and lines[0] == oldContent)

    def test0200AtomicNoError(self):
        '''Checks that atomic write will update the file if no errors occur.
        '''
        oldContent = 'test0200AtomicNoError init\n'
        newContent = 'test0200AtomicNoError overwrite\n'
        self.writeFile(open, 'testfile.txt', oldContent)
        self.writeFile(atomicWrite, 'testfile.txt', newContent)
        self.checkFile('testfile.txt', newContent)

    def test0210AtomicError(self):
        '''Checks that atomic write will not update the file if an error occurs.
        '''
        oldContent = 'test0210AtomicError init\n'
        newContent = 'test0210AtomicError overwrite\n'
        self.writeFile(open, 'testfile.txt', oldContent)
        self.assertRaises(IntentionalError, lambda:
            self.writeFile(atomicWrite, 'testfile.txt', newContent, forceError)
            )
        self.checkFile('testfile.txt', oldContent)

    def test0300UserClose(self):
        '''Checks that the user closing the file is handled as an error.
        '''
        oldContent = 'test0300UserClose init\n'
        newContent = 'test0300UserClose overwrite\n'
        self.writeFile(open, 'testfile.txt', oldContent)
        self.assertRaises(ValueError, lambda:
            self.writeFile(atomicWrite, 'testfile.txt', newContent, earlyClose)
            )
        self.checkFile('testfile.txt', oldContent)

if __name__ == '__main__':
    unittest.main()
