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


from emtools.utils import Color
from emtools.jobs import Pipeline, Workflow


class TestWorkflow(unittest.TestCase):
    def test_basic(self):
        wf = Workflow()

        j1 = wf.registerJob('job01')
        d1 = j1.registerOutput('d1')
        j2 = wf.registerJob('job02', inputs=[d1])
        j3 = wf.registerJob('job03', inputs=[d1])
        d3a = j3.registerOutput('d3a')
        d3b = j3.registerOutput('d3b')
        j5 = wf.registerJob('job05')
        d5 = j5.registerOutput('d5')
        j6 = wf.registerJob('job06', inputs=[d3b, d5])

        wf.print()


