# **************************************************************************
# *
# * Authors:     J.M. de la Rosa Trevin (delarosatrevin@gmail.com)
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 3 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# **************************************************************************

from datetime import datetime, timedelta


class Bins:
    def __init__(self, delimiters):
        if not delimiters:
            raise Exception("At least one delimiter should be provided")

        self.bins = [0] * (len(delimiters) + 1)
        self.delimiters = delimiters
        self.total = 0

    def addValue(self, v):
        added = False
        for i, d in enumerate(self.delimiters):
            if v < d:
                self.bins[i] += 1
                added = True
                break
        if not added:
            self.bins[-1] += 1
        self.total += 1

    def print(self):
        print("Total: ", self.total)
        for label, b, p in self:
            print(f"{label:<10} {b:>7} {p:>6.2f}%")

    def toList(self):
        return list(iter(self))

    def __iter__(self):
        if not self.total:
            return

        for i, b in enumerate(self.bins):
            p = round((b * 100.0) / self.total, 2)
            if i == 0:
                label = "< %s" % self.delimiters[0]
            elif i == len(self.delimiters):
                label = "> %s" % self.delimiters[i-1]
            else:
                label = "> %s and < %s" % (self.delimiters[i-1],
                                           self.delimiters[i])

            yield label, b, p


class TsBins(Bins):
    def __init__(self, items, binSize=60):
        """
        Initialize the TimestampBins instance.
        Args:
            items: Items list sorted by timestamps. Each item should have
                a item['ts'] key with the timestamp value.
            binSize: size of the bins in minutes
        """
        # Compute bin delimiters based on binSize and first and last items
        first = items[0]
        last = items[-1]
        last_ts = datetime.fromtimestamp(last['ts'])
        bindelta = timedelta(minutes=binSize)
        delimiters = [datetime.fromtimestamp(first['ts']) + bindelta]

        while delimiters[-1] < last_ts:
            delimiters.append(delimiters[-1] + bindelta)

        Bins.__init__(self, delimiters)
        for item in items:
            self.addValue(datetime.fromtimestamp(item['ts']))

