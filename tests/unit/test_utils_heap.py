# SPDX-License-Identifier: BSD-3-Clause

import utils
import os, os.path, random, time, unittest

class TestHeap(unittest.TestCase):
    "Test Heap functionality."

    keyFunc = None

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)
        self.__arraySize = 471
        self.__arrayLoop = 27
        self.__chunkSize = 217
        self.__chunkLoop = 51
        self.__fillFactor = 1.3
        self.__delFactor = 0.4

    def __checkEmpty(self, heap):
        self.assertRaises(StopIteration, lambda: next(heap))

    def __getItems(self, heap):
        #return [item for item in heap]
        list = []
        for item in heap:
            heap._check(self)
            list.append(item)
        return list

    def _createHeap(self):
        return utils.Heap(key=self.keyFunc)

    def _wrapItem(self, item):
        return item

    def test01Empty(self):
        """Test with no elements (empty heap)"""
        heap = self._createHeap()
        self.__checkEmpty(heap)

    def test02OneItem(self):
        """Test with a single element (add/remove)"""
        heap = self._createHeap()
        item = self._wrapItem('item')
        heap.add(item)
        list = self.__getItems(heap)
        self.assertEqual(len(list), 1)
        self.assertEqual(list[0], item)
        self.__checkEmpty(heap)

    def test03Shuffled(self):
        """Test with a shuffled sequence of distinct integers"""
        heap = self._createHeap()
        for _ in range(self.__arrayLoop):
            initial = [ self._wrapItem(x) for x in range(self.__arraySize) ]
            shuffled = list(initial)
            random.shuffle(shuffled)
            for item in shuffled:
                heap.add(item)
                heap._check(self)
            self.assertEqual(self.__getItems(heap), initial)
            self.__checkEmpty(heap)

    def test04Random(self):
        """Test with a sequence of random integers"""
        heap = self._createHeap()
        for _ in range(self.__arrayLoop):
            initial = [
                self._wrapItem(random.randint(0, 1 << 30))
                for _ in range(self.__arraySize)
                ]
            random.shuffle(initial)
            sorted = list(initial)
            sorted.sort(key=self.keyFunc)
            for item in initial:
                heap.add(item)
                heap._check(self)
            self.assertEqual(self.__getItems(heap), sorted)
            self.__checkEmpty(heap)

    def test05Chunky(self):
        """Test with a sequence of random integers fed in chuncks"""
        heap = self._createHeap()
        checkArray = []
        for _ in range(self.__chunkLoop):
            toAdd = random.randint(1, int(self.__chunkSize * self.__fillFactor))
            toGet = random.randint(1, self.__chunkSize)
            for a in range(toAdd):
                item = self._wrapItem(random.randint(0, 1 << 30))
                heap.add(item)
                heap._check(self)
                checkArray.append(item)
            checkArray.sort(key=self.keyFunc)
            for a in range(toGet):
                try:
                    item = next(heap)
                    heap._check(self)
                except StopIteration:
                    if len(checkArray) != 0:
                        self.fail('Heap is empty while check array'
                        ' contains ' + str(len(checkArray)) + ' items')
                else:
                    try:
                        self.assertEqual(checkArray.pop(0), item)
                    except IndexError:
                        self.fail('Heap has returned \'' + str(item) +
                        '\' while check array is empty')
        for item in heap:
            heap._check(self)
            try:
                self.assertEqual(checkArray.pop(0), item)
            except IndexError:
                self.fail('Heap has returned \'' + str(item) +
                '\' while check array is empty')
        self.assertEqual(len(checkArray), 0)

    def test06Remove(self):
        """Test with removing elements from the middle"""
        heap = self._createHeap()
        for _ in range(self.__arrayLoop):
            initial = [ self._wrapItem(x) for x in range(self.__arraySize) ]
            shuffled = list(initial)
            random.shuffle(shuffled)
            for item in shuffled:
                heap.add(item)
                heap._check(self)
            for _ in range(int(self.__arraySize * self.__delFactor)):
                value = self._wrapItem(random.randint(0, self.__arraySize - 1))
                try:
                    index = initial.index(value)
                except ValueError:
                    pass
                else:
                    del initial[index]
                    try:
                        heap.remove(value)
                    except ValueError:
                        self.fail('Failed to remove element: ' + str(value))
                    heap._check(self)
            self.assertEqual(self.__getItems(heap), initial)
            self.__checkEmpty(heap)

class TestHeapExternalComparator(TestHeap):

    @staticmethod
    def keyFunc(elem):
        return elem.x

    class Uncomparable(object):
        def __init__(self, x):
            self.x = x
        def __lt__(self, other):
            assert False
        def __le__(self, other):
            assert False
        def __gt__(self, other):
            assert False
        def __ge__(self, other):
            assert False
        def __eq__(self, other):
            return hasattr(other, 'x') and self.x == other.x
        __hash__ = None

    def _wrapItem(self, item):
        return self.Uncomparable(item)

if __name__ == '__main__':
    unittest.main()
