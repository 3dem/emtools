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
import signal
import traceback
from uuid import uuid4

from emtools.utils import Process


class Pipeline:
    """
    Simple implementation of Pipeline class to manage tasks.
    It will allow to add generators and processors to create new tasks
    and process them. Internal a Queue classes will be used to connect
    inputs and outputs.
    """

    def __init__(self, debug=False):
        self.debug = debug
        self._nodes = OrderedDict()

    def _addNode(self, nodeClass, *args, **kwargs):
        name = kwargs.get('name', 'node-%02d' % len(self._nodes))
        if name in self._nodes:
            raise Exception("Duplicated node name '%s'" % name)

        kwargs['name'] = name
        if 'debug' not in kwargs:
            kwargs['debug'] = self.debug
        n = nodeClass(*args, **kwargs)
        self._nodes[name] = n
        return n

    def addGenerator(self, *args, **kwargs):
        return self._addNode(TaskGenerator, *args, **kwargs)

    def addProcessor(self, *args, **kwargs):
        return self._addNode(TaskProcessor, *args, **kwargs)

    def run(self):
        for n in self._nodes.values():
            n.start()

        for n in self._nodes.values():
            n.join()


class TaskQueue:
    """ Queue of tasks where producers can deposit tasks and
    consumers can get it.
    """
    def __init__(self):
        self._activeGenerators = 0
        self._condition = threading.Condition()
        self._tasks = []

    def getTask(self, proc):
        """ This function should be called from a consumer of this
        output instance.
        """
        self._condition.acquire()

        proc._print("Inside condition lock, queue._activeGenerators: ",
                    self._activeGenerators)
        doWait = True
        task = None

        while doWait:
            doWait = False
            if self._tasks:
                proc._print("There are tasks")
                task = self._tasks.pop(0)
            elif self._activeGenerators > 0:
                proc._print("No tasks, but not Done, waiting...")
                self._condition.wait()
                doWait = True
            else:
                proc._print("No tasks and done, should return None task.")

        self._condition.release()

        # Return the task, either None if nothing else should be
        # done, or a task to be processed
        return task

    def putTask(self, task):
        """ This function should be used by subclasses of Output
        that produces items that will be used by consumers.
        """
        self._condition.acquire()
        self._tasks.append(task)
        self._condition.notify()
        self._condition.release()

    def notifyGeneratorStarts(self):
        """ When this queue is associated to a generator, this method should be
        used to notify that the generator has started to run.
        """
        self._condition.acquire()
        self._activeGenerators += 1
        self._condition.release()

    def notifyGeneratorEnds(self):
        """ This function should be used by generators associated to this queue
        to notify that they are done and not more tasks will be produced.
        """
        self._condition.acquire()
        self._activeGenerators -= 1
        if self._activeGenerators == 0:
            self._condition.notifyAll()
        self._condition.release()

    def isDone(self):
        self._condition.acquire()
        is_done = self._activeGenerators == 0
        self._condition.release()
        return is_done


class TaskGenerator(threading.Thread):
    def __init__(self, generator, outputQueue=None,
                 name='', debug=False):
        """
        Params:
            generator: function generating new tasks
            outputQueue: queue to put new tasks.
                If None, a new queue will be created
        """
        threading.Thread.__init__(self)
        self.id = None
        self.name = name
        self.debug = debug
        self._generator = generator

        if outputQueue is None:
            self.outputQueue = TaskQueue()
        else:
            self.outputQueue = outputQueue

    def run(self):
        self.outputQueue.notifyGeneratorStarts()
        self.id = threading.get_ident()

        for task in self._generator():
            self.outputQueue.putTask(task)

        self.outputQueue.notifyGeneratorEnds()

    def _print(self, *args):
        """ Function to debug printing Generator's name. """
        if self.debug:
            print(">>> %s: " % self.name, *args)


class TaskProcessor(TaskGenerator):
    def __init__(self, inputQueue, processor, outputQueue=None,
                 name='', debug=False):
        TaskGenerator.__init__(self, self._process, outputQueue, name, debug)
        self._processor = processor
        self._inputQueue = inputQueue

    def _process(self):
        self._print("Getting new task...")
        task = self._inputQueue.getTask(self)
        while task is not None:
            self._print("Got task: '%s'" % task)

            yield self._processor(task)  # yield new processed task
            self._print("Getting new task...")
            task = self._inputQueue.getTask(self)

        self._print("Got task: None")


class ProcessingPipeline(Pipeline):
    """ Subclass of Pipeline that is commonly used to run programs.

    This class will define a workingDir (usually os.getcwd)
    and an output dir where all output should be generated.
    It will also add some helper functions to manipulate file
    paths relative to the working dir.
    """
    def __init__(self, **kwargs):
        workingDir = kwargs.pop('working_dir', os.getcwd())
        outputDir = kwargs.pop('output_dir', None)
        scratchDir = kwargs.pop('scratch', None)
        Pipeline.__init__(self, debug=kwargs.get('debug', False))
        self.workingDir = self.__validate(workingDir, 'working')
        self.outputDir = self.__validate(outputDir, 'output')
        self.scratchDir = self.__validate(scratchDir, 'scratch') if scratchDir else None
        self.tmpDir = self.join('tmp')

    def __validate(self, path, key):
        if not path:
            raise Exception(f'Invalid {key} directory: {path}')
        if not os.path.exists(path):
            raise Exception(f'Non-existing {key} directory: {path}')

        return path

    def __clean_tmp(self):
        Process.system(f"rm -rf {self.tmpDir}")

    def __create_tmp(self):
        self.__clean_tmp()

        if self.scratchDir:
            scratchTmp = os.path.join(self.scratchDir, str(uuid4()))
            Process.system(f"ln -s {scratchTmp} {self.tmpDir}")
        else:
            Process.system(f"mkdir {self.tmpDir}")

    def get_arg(self, argDict, key, envKey, default=None):
        """ Get an argument from the argDict or from the environment.

        Args:
            argDict: arguments dict from where to get the 'key' value
            key: string key of the argument name in argDict
            envKey: string key of the environment variable
            default: default value if not found in argDict or environ
        """
        return argDict.get(key, os.environ.get(envKey, default))

    def join(self, *p):
        return os.path.join(self.outputDir, *p)

    def relpath(self, p):
        return os.path.relpath(p, self.workingDir)

    def prerun(self):
        """ This method will be called before the run. """
        pass

    def postrun(self):
        """ This method will be called after the run. """
        pass

    def __file(self, suffix):
        with open(self.join(f'RELION_JOB_EXIT_{suffix}'), 'w'):
            pass

    def __abort(self, signum, frame):
        self.__file('ABORTED')
        sys.exit(0)

    def run(self):
        try:
            signal.signal(signal.SIGINT, self.__abort)
            signal.signal(signal.SIGTERM, self.__abort)
            self.__create_tmp()
            self.prerun()
            Pipeline.run(self)
            self.postrun()
            self.__clean_tmp()
            self.__file('SUCCESS')
        except Exception as e:
            self.__file('FAILURE')
            traceback.print_exc()


