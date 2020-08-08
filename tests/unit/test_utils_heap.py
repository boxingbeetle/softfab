# SPDX-License-Identifier: BSD-3-Clause

"""Test Heap functionality."""

from random import randint, shuffle

from pytest import fail, mark, raises

from softfab.utils import Heap


class SimParams:
    arraySize = 471
    arrayLoop = 27
    chunkSize = 217
    chunkLoop = 51
    fillFactor = 1.3
    delFactor = 0.4

simParams = SimParams()


class BaseTypeParams:
    keyFunc = None

    def wrapItem(self, item):
        return item

    def createHeap(self):
        return Heap(key=self.keyFunc)

class Uncomparable:
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

class UncomparableTypeParams(BaseTypeParams):

    @staticmethod
    def keyFunc(elem):
        return elem.x

    def wrapItem(self, item):
        return Uncomparable(item)

typeParamsOptions = (BaseTypeParams(), UncomparableTypeParams())


def checkEmpty(heap):
    assert heap.peek() is None
    assert heap.pop() is None
    with raises(StopIteration):
        next(heap.iterPop())

def getItems(heap):
    lst = []
    for item in heap.iterPop():
        heap._check()
        lst.append(item)
    return lst


@mark.parametrize('typeParams', typeParamsOptions)
def testHeapEmpty(typeParams):
    """Test with no elements (empty heap)."""
    heap = typeParams.createHeap()
    checkEmpty(heap)

@mark.parametrize('typeParams', typeParamsOptions)
def testHeapOneItem(typeParams):
    """Test with a single element (add/remove)."""
    heap = typeParams.createHeap()
    item = typeParams.wrapItem('item')
    heap.add(item)
    lst = getItems(heap)
    assert len(lst) == 1
    assert lst[0] == item
    checkEmpty(heap)

@mark.parametrize('typeParams', typeParamsOptions)
def testHeapShuffled(typeParams):
    """Test with a shuffled sequence of distinct integers."""
    heap = typeParams.createHeap()
    for _ in range(simParams.arrayLoop):
        initial = [typeParams.wrapItem(x) for x in range(simParams.arraySize)]
        shuffled = list(initial)
        shuffle(shuffled)
        for item in shuffled:
            heap.add(item)
            heap._check()
        assert getItems(heap) == initial
        checkEmpty(heap)

@mark.parametrize('typeParams', typeParamsOptions)
def testHeapRandom(typeParams):
    """Test with a sequence of random integers."""
    heap = typeParams.createHeap()
    for _ in range(simParams.arrayLoop):
        initial = [
            typeParams.wrapItem(randint(0, 1 << 30))
            for _ in range(simParams.arraySize)
            ]
        shuffle(initial)
        srt = sorted(initial, key=typeParams.keyFunc)
        for item in initial:
            heap.add(item)
            heap._check()
        assert getItems(heap) == srt
        checkEmpty(heap)

@mark.parametrize('typeParams', typeParamsOptions)
def testHeapChunky(typeParams):
    """Test with a sequence of random integers fed in chuncks."""
    heap = typeParams.createHeap()
    checkArray = []
    for _ in range(simParams.chunkLoop):
        toAdd = randint(1, int(simParams.chunkSize * simParams.fillFactor))
        toGet = randint(1, simParams.chunkSize)
        for a in range(toAdd):
            item = typeParams.wrapItem(randint(0, 1 << 30))
            heap.add(item)
            heap._check()
            checkArray.append(item)
        checkArray.sort(key=typeParams.keyFunc)
        for a in range(toGet):
            item = heap.pop()
            heap._check()
            if item is None:
                if len(checkArray) != 0:
                    fail(f"Heap is empty while check array "
                         f"contains {len(checkArray)} items")
            else:
                try:
                    assert checkArray.pop(0) == item
                except IndexError:
                    fail(f"Heap has returned '{item}' "
                         f"while check array is empty")
    for item in heap.iterPop():
        heap._check()
        try:
            assert checkArray.pop(0) == item
        except IndexError:
            fail(f"Heap has returned '{item}' while check array is empty")
    assert len(checkArray) == 0

@mark.parametrize('typeParams', typeParamsOptions)
def testHeapRemove(typeParams):
    """Test with removing elements from the middle."""
    heap = typeParams.createHeap()
    for _ in range(simParams.arrayLoop):
        initial = [typeParams.wrapItem(x) for x in range(simParams.arraySize)]
        shuffled = list(initial)
        shuffle(shuffled)
        for item in shuffled:
            heap.add(item)
            heap._check()
        for _ in range(int(simParams.arraySize * simParams.delFactor)):
            value = typeParams.wrapItem(randint(0, simParams.arraySize - 1))
            try:
                index = initial.index(value)
            except ValueError:
                pass
            else:
                del initial[index]
                try:
                    heap.remove(value)
                except ValueError:
                    fail(f"Failed to remove element: {value}")
                heap._check()
        assert getItems(heap) == initial
        checkEmpty(heap)
