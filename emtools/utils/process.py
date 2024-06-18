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
import time

import psutil
import subprocess
import logging


class Process:
    def __init__(self, *args, **kwargs):
        """ Create a process using subprocess."""
        self.args = args
        error = ''
        try:
            self._p = subprocess.run(args, capture_output=True, text=True)
            self.stdout = self._p.stdout
            self.stderr = self._p.stderr
            self.returncode = self._p.returncode
            if self.returncode != 0:
                error = self._p.stderr
        except Exception as e:
            self._p = None
            self.returncode = -1
            error = str(e)

        if error and kwargs.get('doRaise', True):
            raise Exception(error)

    def lines(self):
        """ Iterate over the lines of the process output.
        """
        for line in self.stdout.split('\n'):
            yield line

    def print(self, args=True, stdout=False):
        if args:
            print(">>> ", *self.args)
        if stdout:
            print(self.stdout)

    @staticmethod
    def system(cmd, only_print=False, color=None):
        """ Execute and print a command.

        Args:
            cmd: Command to be executed.
            only_print: If true, the command will only be printed and
                not executed
            color: Optional color for the command
        """
        printCmd = cmd if color is None else color(cmd)
        print(printCmd)
        if not only_print:
            return os.system(cmd)

    @staticmethod
    def ps(program, workingDir=None, children=False):
        """ Inspect processes matching a given program name.

        Args:
            program: string matching the program name
            workingDir: if not None, filter processes only with that folder as
                working directory (cwd)
        """
        processes = {}  # store processes grouped by working dir
        pids = set()

        def _addProc(f, proc):
            if f not in processes:
                processes[f] = []
            if proc.pid not in pids:
                processes[f].append(proc)
                pids.add(proc.pid)

        attrs = ['pid', 'ppid', 'name', 'cwd', 'username', 'memory_percent', 'cpu_percent']
        for proc in psutil.process_iter(attrs):
            if not program or program in proc.info['name']:
                folder = proc.info['cwd']
                if workingDir is None or folder == workingDir:
                    _addProc(folder, proc)
                    if children:
                        for child in proc.children(recursive=True):
                            child.info = child.as_dict(attrs)
                            _addProc(folder, child)

        return processes

    class Logger:
        """ Use a logger to log commands that are executed via os.system. """
        def __init__(self, logger=None, only_log=False,
                     format='%(asctime)s %(levelname)s %(message)s'):
            # If not logger, create one using stdout
            if logger is None:
                handler = logging.StreamHandler(stream=sys.stdout)
                formatter = logging.Formatter(format)
                handler.setFormatter(formatter)
                logger = logging.getLogger('stdout')
                logger.setLevel(logging.DEBUG)
                logger.addHandler(handler)

            # Shortcuts
            self.logger = logger
            self.info = logger.info
            self.error = logger.error
            self.warning = logger.warning

            # If True, only log bug not make the system call
            self.system_only_log = only_log

        def system(self, cmd, retry=None):
            """ Execute a command and log it.

            Args:
                 cmd: Command string to be executed with os.system
                 retry: If not None, it should be the time in seconds
                    after which the command will be re-executed on failure
                    until successful completion.

            Return:
                  last exit_status from os.system result
            """
            while True:
                self.logger.info(cmd)
                exit_status = 0
                if not self.system_only_log:
                    exit_status = os.system(cmd)
                if exit_status:
                    self.logger.error(f"COMMAND FAILED: {cmd} , "
                                      f"exit: {exit_status}")
                    if retry:
                        time.sleep(retry)
                    else:
                        break
                else:
                    break

            return exit_status

        def mkdir(self, path, retry=None):
            """ Make a folder path. """
            if not os.path.exists(path):
                self.system(f"mkdir -p '{path}'", retry=retry)

        def cp(self, src, dst, retry=None):
            """ Copy from src to dst. """
            self.system(f"cp '{src}' '{dst}'", retry=retry)

        def mv(self, src, dst, retry=None):
            """ Move from src to dst. """
            self.system(f"mv '{src}' '{dst}'", retry=retry)

        def rm(self, path):
            """ Remove a folder or file. """
            self.system(f"rm -rf '{path}'")

