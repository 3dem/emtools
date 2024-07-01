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

import unittest
import numpy as np
import time

from emtools.jobs import Pipeline


class TestThreading(unittest.TestCase):
    def test_threads_processors(self):

        def generate():
            n = 17
            for i in range(1, n+1):
                mic = "mic_%03d.mrc" % i
                print("Created micrograph: %s" % mic)
                yield mic
                time.sleep(1)

        def filter(mic):
            print("Filtering micrograph: %s" % mic)
            time.sleep(3)
            return mic.replace(".mrc", "_filtered.mrc")

        def picking(mic):
            print("Picking micrograph: %s" % mic)
            time.sleep(2)
            m = 100
            xRand = np.random.randint(0, 1000, m)
            yRand = np.random.randint(0, 1000, m)
            coords = [(x, y) for x, y in zip(xRand, yRand)]
            time.sleep(1)
            return mic, coords

        pipeline = Pipeline(debug=False)

        g = pipeline.addGenerator(generate,
                            name='GENERATOR')

        f1 = pipeline.addProcessor(g.outputQueue, filter,
                             name='FILTER-1')
        pipeline.addProcessor(g.outputQueue, filter,
                              name='FILTER-2',
                              outputQueue=f1.outputQueue)
        pipeline.addProcessor(g.outputQueue, filter,
                              name='FILTER-3',
                              outputQueue=f1.outputQueue)
        pipeline.addProcessor(f1.outputQueue, picking,
                              name='PICKING')

        pipeline.run()

        print("PROCESSING DONE!!!")