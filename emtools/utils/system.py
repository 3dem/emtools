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

"""
index, name, driver_version, temperature.gpu, utilization.gpu [%], utilization.memory [%], memory.total [MiB], memory.used [MiB]
0, NVIDIA GeForce RTX 3090, 515.65.01, 42, 1 %, 13 %, 24576 MiB, 963 MiB
1, NVIDIA GeForce RTX 3090, 515.65.01, 37, 0 %, 0 %, 24576 MiB, 1 MiB
"""

import socket
import platform
import psutil

from .process import Process


class System:
    NVIDIA_SMI_QUERY = ['nvidia-smi', '--query-gpu=index,name,driver_version,'
                        'temperature.gpu,utilization.gpu,utilization.memory,'
                        'memory.total,memory.used', '--format=csv']

    @staticmethod
    def gpus():
        """ Return a dictionary with existing GPUs and their properties. """
        gpus = []
        query = Process(System.NVIDIA_SMI_QUERY[0],
                        *System.NVIDIA_SMI_QUERY[1:], doRaise=False)

        if query.returncode == 0:   # no error
            for i, line in enumerate(query.lines()):
                # Use first line as keywords since it is the header
                if line.strip():
                    if i == 0:
                        keys = line.split(',')
                    else:
                        values = line.split(',')
                        gpus.append({k.strip().split()[0]: v.strip()
                                     for k, v in zip(keys, values)})
        return gpus

    @staticmethod
    def cpus():
        """ Return number of CPUs in the system, None if can't figure it out."""
        system = platform.system()
        cpus = 0

        if system == 'Linux':
            for line in Process('lscpu').lines():
                if line.startswith('CPU(s):'):
                    cpus = int(line.split()[1].strip())

        elif system == 'Darwin':
            for line in Process('sysctl', '-a').lines():
                if line.startswith('hw.ncpu:'):
                    cpus = int(line.split()[1])

        return cpus

    @staticmethod
    def memory():
        """ Return the total virtual memory of the system. (in Gb) """
        return psutil.virtual_memory().total // (1024 * 1024 * 1024)  # GiB

    @staticmethod
    def specs():
        """ Make an informative summary of the system specs. """
        gpuDict = {}
        for gpu in System.gpus():
            name = gpu['name']
            if name not in gpuDict:
                gpuDict[name] = {
                    'count': 1,
                    'memory': gpu['memory.total']
                }
            else:
                gpuDict[name]['count'] += 1
        return {
            'CPUs': System.cpus(),
            'GPUs': gpuDict,
            'MEM': System.memory()
        }

    @staticmethod
    def hostname():
        """ Return the hostname. """
        return socket.gethostname()
