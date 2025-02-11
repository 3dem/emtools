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

import os
import sys
from collections import OrderedDict
import threading

from emtools.utils import Process


class Workflow:
    """
    Simple implementation of a Workflow class for management of Jobs and
    produced Data. The workflow is represented as a directed acyclic graph.
    """

    def __init__(self, jobCounter=0):
        self._jobs = {}
        self.data = {}
        self._jobCounter = jobCounter

    def jobs(self):
        """ Iterate over the jobs sorted by index. """
        return sorted(self._jobs.values(), key=lambda j: j.index)

    def root(self):
        """ Iterator over nodes that does not have any input. """
        for j in self.jobs():
            if not j.inputs:
                yield j

    def getJob(self, jobId):
        return self._jobs[jobId]

    def registerJob(self, jobId, inputs=[]):
        job = Workflow.Job(self, jobId, self._jobCounter + 1, inputs=inputs)
        self._jobCounter += 1
        self._jobs[jobId] = job
        return job

    def print(self):
        """ Print the workflow to the terminal. """
        dot = 'digraph G {\n   compound=true;\n'
        links = ''

        for j in self.jobs():
            dot += (f'   subgraph cluster_{j.index} {{\n'
                    f'        style=filled; color=lightgrey; \n'
                    f'        node [style=filled,color=white];\n'
                    f'        i{j.index} [color=lightgrey,fontcolor=lightgrey];\n'
                    f'        label="{j.id}";\n')
            for o in j.outputs:
                dot += f'        {o.id}\n'
                for c in o.childs:
                    links += f'{o.id} -> i{c.index} [lhead=cluster_{c.index}];\n'
            dot += '    }\n'

        dot += f'\n{links}\n}}\n'
        print(dot)

    class Job(dict):
        def __init__(self, wf, id, index, inputs=[], **kwargs):
            dict.__init__(self, **kwargs)
            self.wf = wf
            self.id = id
            self.index = index
            self.inputs = []
            self.outputs = []
            self.addInputs(inputs)

        def registerOutput(self, dataId, **kwargs):
            data = Workflow.Data(self, dataId, **kwargs)
            self.wf.data[dataId] = data
            self.outputs.append(data)
            return data

        def addInputs(self, inputs):
            if any(i in self.inputs for i in inputs):
                raise Exception(f'Input {i} was already added.')

            # TODO validate cyclic dependencies
            for i in inputs:
                self.inputs.append(i)
                i.childs.append(self)

    class Data(dict):
        def __init__(self, parent, dataId, **kwargs):
            dict.__init__(self, **kwargs)
            self.id = dataId
            self.parent = parent
            self.childs = []

