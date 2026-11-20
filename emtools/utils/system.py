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

import sys
import socket
import shutil
import subprocess
import platform
import psutil
import json

from .process import Process


class System:
    NVIDIA_SMI_QUERY = ['nvidia-smi', '--query-gpu=index,name,driver_version,'
                        'temperature.gpu,utilization.gpu,utilization.memory,'
                        'memory.total,memory.used,pci.bus_id', '--format=csv']

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
    def cuda_bus_ids(isolated=False):
        """ PCI bus ids of the CUDA devices as this process sees them, in
        CUDA order (after CUDA_VISIBLE_DEVICES and CUDA_DEVICE_ORDER), which
        is not the nvidia-smi one in nodes with different GPU models: CUDA
        puts the fastest first. From the CUDA driver, None if it can not be
        used. Only cuInit is called: no context is created, no GPU memory
        is used.

        Args:
            isolated: ask in a short-lived child process (same environment),
                so the CUDA driver is not loaded in this one, e.g. the main
                process of a job.
        """
        if isolated:
            code = ('import json; from emtools.utils.system import System; '
                    'print(json.dumps(System.cuda_bus_ids()))')
            try:
                p = subprocess.run([sys.executable, '-c', code], timeout=60,
                                   capture_output=True, text=True)
                return json.loads(p.stdout.strip().splitlines()[-1])
            except Exception:
                return None

        import ctypes
        lib = None
        for name in ('libcuda.so.1', 'libcuda.so', 'nvcuda.dll'):
            try:
                lib = ctypes.CDLL(name)
                break
            except OSError:
                pass
        if lib is None or lib.cuInit(0) != 0:
            return None
        n = ctypes.c_int()
        if lib.cuDeviceGetCount(ctypes.byref(n)) != 0:
            return None
        busIds = []
        for i in range(n.value):
            dev, buf = ctypes.c_int(), ctypes.create_string_buffer(64)
            if (lib.cuDeviceGet(ctypes.byref(dev), i) or
                    lib.cuDeviceGetPCIBusId(buf, len(buf), dev)):
                return None
            busIds.append(buf.value.decode())
        return busIds

    @staticmethod
    def bus_id_key(busId):
        """ Comparable PCI bus id: CUDA gives '0000:3B:00.0' and
        nvidia-smi '00000000:3B:00.0'. """
        domain, _, rest = str(busId).strip().lower().partition(':')
        try:
            return f"{int(domain, 16):x}:{rest}"
        except ValueError:
            return str(busId).strip().lower()

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

    @staticmethod
    def distro():
        """ Return a human-readable OS distribution name and version.
        On Linux, it reads /etc/os-release (PRETTY_NAME); on macOS it uses
        the product version; falls back to platform.platform() otherwise.
        """
        system = platform.system()

        if system == 'Linux':
            info = {}
            try:
                with open('/etc/os-release') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        key, _, value = line.partition('=')
                        info[key] = value.strip().strip('"')
            except (FileNotFoundError, OSError):
                pass

            name = info.get('PRETTY_NAME') or info.get('NAME')
            return name or f"Linux {platform.release()}"

        elif system == 'Darwin':
            version, _, _ = platform.mac_ver()
            return f"macOS {version}" if version else "macOS"

        return platform.platform()

    @staticmethod
    def kernel():
        """ Return the kernel release (e.g. what 'uname -r' would print). """
        return platform.release()

    @staticmethod
    def disk(path='/'):
        """ Return disk usage (in bytes) for the filesystem containing path.
        Keys: 'total', 'used', 'free'. Returns None if it can't be read. """
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            return None
        return {'total': usage.total, 'used': usage.used, 'free': usage.free}
