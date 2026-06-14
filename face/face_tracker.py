from scipy.spatial import distance as dist
from collections import OrderedDict
import numpy as np


class FaceTracker:
    """
    Lightweight centroid tracker for the face/demographics camera.

    Same matching logic as scene/centroidtracker.py, but update() returns
    {object_id: (centroid, rect)} so callers can re-crop the face region
    for a stably-tracked person across frames.
    """

    def __init__(self, maxDisappeared=15, maxDistance=120):
        self.nextObjectID   = 0
        self.objects        = OrderedDict()  # objectID -> centroid
        self.rects          = OrderedDict()  # objectID -> rect (x1,y1,x2,y2)
        self.disappeared    = OrderedDict()
        self.maxDisappeared = maxDisappeared
        self.maxDistance    = maxDistance

    def register(self, centroid, rect):
        self.objects[self.nextObjectID]     = centroid
        self.rects[self.nextObjectID]       = rect
        self.disappeared[self.nextObjectID] = 0
        self.nextObjectID += 1

    def deregister(self, objectID):
        del self.objects[objectID]
        del self.rects[objectID]
        del self.disappeared[objectID]

    def update(self, rects):
        """
        rects: list of (x1, y1, x2, y2)
        returns: {object_id: (centroid, rect)}
        """
        if len(rects) == 0:
            for objectID in list(self.disappeared.keys()):
                self.disappeared[objectID] += 1
                if self.disappeared[objectID] > self.maxDisappeared:
                    self.deregister(objectID)
            return self._result()

        inputCentroids = np.array(
            [((x1+x2)//2, (y1+y2)//2) for x1,y1,x2,y2 in rects],
            dtype="int"
        )

        if len(self.objects) == 0:
            for c, r in zip(inputCentroids, rects):
                self.register(c, r)
            return self._result()

        objectIDs       = list(self.objects.keys())
        objectCentroids = list(self.objects.values())
        D    = dist.cdist(np.array(objectCentroids), inputCentroids)
        rows = D.min(axis=1).argsort()
        cols = D.argmin(axis=1)[rows]

        usedRows = set()
        usedCols = set()

        for row, col in zip(rows, cols):
            if row in usedRows or col in usedCols:
                continue
            if D[row, col] > self.maxDistance:
                continue
            objectID = objectIDs[row]
            self.objects[objectID]     = inputCentroids[col]
            self.rects[objectID]       = rects[col]
            self.disappeared[objectID] = 0
            usedRows.add(row)
            usedCols.add(col)

        unusedRows = set(range(D.shape[0])) - usedRows
        unusedCols = set(range(D.shape[1])) - usedCols

        if D.shape[0] >= D.shape[1]:
            for row in unusedRows:
                objectID = objectIDs[row]
                self.disappeared[objectID] += 1
                if self.disappeared[objectID] > self.maxDisappeared:
                    self.deregister(objectID)
        else:
            for col in unusedCols:
                self.register(inputCentroids[col], rects[col])

        return self._result()

    def _result(self):
        return {
            objectID: (self.objects[objectID], self.rects[objectID])
            for objectID in self.objects
        }
