from scipy.spatial import distance as dist
from collections import OrderedDict
import numpy as np


class CentroidTracker:
    def __init__(self, maxDisappeared=50, maxDistance=100):
        self.nextObjectID   = 0
        self.objects        = OrderedDict()
        self.disappeared    = OrderedDict()
        self.maxDisappeared = maxDisappeared
        self.maxDistance    = maxDistance

    def register(self, centroid):
        self.objects[self.nextObjectID]     = centroid
        self.disappeared[self.nextObjectID] = 0
        self.nextObjectID += 1

    def deregister(self, objectID):
        del self.objects[objectID]
        del self.disappeared[objectID]

    def update(self, rects):
        if len(rects) == 0:
            for objectID in list(self.disappeared.keys()):
                self.disappeared[objectID] += 1
                if self.disappeared[objectID] > self.maxDisappeared:
                    self.deregister(objectID)
            return self.objects

        inputCentroids = np.array(
            [((x1+x2)//2, (y1+y2)//2) for x1,y1,x2,y2 in rects],
            dtype="int"
        )

        if len(self.objects) == 0:
            for c in inputCentroids:
                self.register(c)
            return self.objects

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
                self.register(inputCentroids[col])

        return self.objects
