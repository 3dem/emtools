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
    def system(cmd):
        print(cmd)
        os.system(cmd)


