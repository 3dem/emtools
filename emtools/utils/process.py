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
import psutil
import subprocess


class Process:
    def __init__(self, *args, **kwargs):
        """ Create a process using subprocess.run. """
        self.args = args
        self._p = subprocess.run(args, capture_output=True, text=True)
        self.stdout = self._p.stdout
        self.stderr = self._p.stderr
        #FIXME: Maybe some cases returncode could be non-zero
        if self._p.returncode != 0:
            raise Exception(self.stderr)

    def lines(self):
        for line in self.stdout.split('\n'):
            yield line

    def print(self, args=True, stdout=False):
        if args:
            print(">>> ", *self.args)
        if stdout:
            print(self.stdout)

    @staticmethod
    def system(cmd, only_print=False):
        print(cmd)
        if not only_print:
            os.system(cmd)

    @staticmethod
    def kill(pid, children=True):
        """ Kill the process with given pid and all children processes
        if children=True.

        :param pid: the process id to terminate
        """
        proc = psutil.Process(pid)
        if children:
            for c in proc.children(recursive=True):
                if c.pid is not None:
                    print("Terminating child pid: %d" % c.pid)
                    c.kill()
        print("Terminating process pid: %s" % pid)
        if pid is None:
            print("Got None PID!!!")
        else:
            proc.kill()


