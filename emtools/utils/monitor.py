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
Lightweight resource monitor of a running job: a process and all its
descendants, plus the GPUs it uses. It runs in its own low priority process
(nice 19, idle I/O class), so it does not share the GIL nor compete for CPU
with the job, and it stops by itself when the monitored process is gone:

    emt-monitor --pid PID --output usage.csv [--interval 2] [--gpus 0,1|all]
    emt-monitor --summary usage.csv

Every interval it appends one row to the CSV file (flushed at once, so it
can be read while the job runs and it is complete even if the job is
killed). The columns:

    time          seconds since the monitor started
    procs         processes in the job tree
    cpu           CPU of the job tree, in % of one core (400 = 4 cores busy)
    rss_gb        resident memory of the job tree (sum of RSS, GiB; shared
                  pages of MPI processes are counted once per process)
    read_mbs      I/O of the job tree in MB/s (read/write calls, so any file
    write_mbs     system, network ones included, and also page cache hits)
    node_cpu      CPU of the whole node, in % of all its cores
    node_mem_gb   memory used in the whole node (total - available, GiB)
    gpuN_util     utilization of GPU N (%, nvidia-smi index in the node)
    gpuN_mem_gb   memory used in GPU N (GiB, by any process)
    gpuN_power    power draw of GPU N (W)

Unavailable values are left empty (e.g. I/O on macOS). GPUs are read with
NVML (pynvml / nvidia-ml-py) if it can be imported, otherwise with a single
'nvidia-smi --loop-ms' process kept running for the whole job.

The GPUs are given as the job sees them: CUDA device ids, relative to
CUDA_VISIBLE_DEVICES and in CUDA order, which is not the nvidia-smi order
in nodes with different GPU models (CUDA puts the fastest first). The CUDA
driver tells their PCI bus ids, see resolve_gpus and System.cuda_bus_ids.
"""

import os
import sys
import csv
import time
import signal
import threading
import subprocess

import psutil

from .system import System


GiB = 1024 ** 3
MB = 1000 ** 2


def resolve_gpus(gpus):
    """ Node GPUs (ids for nvidia-smi -i or NVML) of the CUDA device ids
    used by a job (or 'all' of them), mapped with the PCI bus ids from the
    CUDA driver. Without it, CUDA order is taken as the nvidia-smi one
    and only CUDA_VISIBLE_DEVICES is applied. None means all node GPUs. """
    allGpus = str(gpus).strip().lower() == 'all'
    ids = [] if allGpus else [int(g) for g in gpus]
    try:
        busIds = System.cuda_bus_ids()
    except Exception:
        busIds = None
    if busIds is not None:
        return busIds if allGpus else [busIds[i] for i in ids if i < len(busIds)]
    visible = [v.strip() for v in os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
               if v.strip()]
    if allGpus:
        return visible or None
    return [visible[i] if i < len(visible) else str(i) for i in ids]


class _NvmlGpus:
    """ GPU readings through NVML, from the monitor process itself. """
    def __init__(self, ids):
        import pynvml
        pynvml.nvmlInit()
        self._nvml = pynvml
        self._handles = {}
        if ids is None:
            ids = [str(i) for i in range(pynvml.nvmlDeviceGetCount())]
        for gid in ids:
            gid = str(gid)
            if gid.isdigit():
                h = pynvml.nvmlDeviceGetHandleByIndex(int(gid))
            elif ':' in gid:
                h = pynvml.nvmlDeviceGetHandleByPciBusId(gid)
            else:
                h = pynvml.nvmlDeviceGetHandleByUUID(gid)
            self._handles[str(pynvml.nvmlDeviceGetIndex(h))] = h

    @property
    def indexes(self):
        return list(self._handles)

    def read(self):
        values = {}
        nvml = self._nvml
        for index, h in self._handles.items():
            def _get(func, conv):
                try:
                    return conv(func(h))
                except Exception:
                    return None
            values[index] = (
                _get(nvml.nvmlDeviceGetUtilizationRates, lambda u: u.gpu),
                _get(nvml.nvmlDeviceGetMemoryInfo, lambda m: m.used / GiB),
                _get(nvml.nvmlDeviceGetPowerUsage, lambda p: p / 1000))
        return values

    def close(self):
        try:
            self._nvml.nvmlShutdown()
        except Exception:
            pass


class _SmiGpus:
    """ GPU readings from one 'nvidia-smi' process running in loop mode,
    its lines are read in a thread and the last values kept. """
    QUERY = 'index,utilization.gpu,memory.used,power.draw'

    def __init__(self, ids, interval):
        cmd = ['nvidia-smi', '--format=csv,noheader,nounits']
        if ids:
            cmd += ['-i', ','.join(str(g) for g in ids)]
        # Resolve the ids (indexes, UUIDs or PCI bus ids) into indexes
        out = subprocess.run(cmd + ['--query-gpu=index'], capture_output=True,
                             text=True, check=True).stdout
        self.indexes = [line.strip() for line in out.splitlines() if line.strip()]
        self._last = {}
        self._proc = subprocess.Popen(
            cmd + [f'--query-gpu={self.QUERY}',
                   '-lms', str(max(100, int(interval * 1000)))],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            bufsize=1)
        threading.Thread(target=self._readLines, daemon=True).start()

    @staticmethod
    def _float(v):
        try:
            return float(v)
        except ValueError:  # e.g. [N/A]
            return None

    def _readLines(self):
        for line in self._proc.stdout:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) == 4:
                util, mem, power = (self._float(p) for p in parts[1:])
                self._last[parts[0]] = (util,
                                        None if mem is None else mem / 1024,
                                        power)

    def read(self):
        return dict(self._last)

    def close(self):
        self._proc.terminate()


class ResourceMonitor:
    """ Record the resources used by a process tree over time. """

    BASE_COLUMNS = ['time', 'procs', 'cpu', 'rss_gb', 'read_mbs', 'write_mbs',
                    'node_cpu', 'node_mem_gb']
    GPU_COLUMNS = ['util', 'mem_gb', 'power']

    def __init__(self, pid, output, interval=2, gpus=None):
        """ gpus: CUDA device ids used by the job, or 'all', see
        resolve_gpus. """
        self.pid = int(pid)
        self.output = output
        self.interval = float(interval)
        self._stop = threading.Event()
        self._prev = {}  # pid -> (create_time, cpu_seconds, read, write)
        self._first = True
        self._gpus = None
        if gpus:
            nodeGpus = None
            try:
                nodeGpus = resolve_gpus(gpus)
                try:
                    self._gpus = _NvmlGpus(nodeGpus)
                except Exception:
                    self._gpus = _SmiGpus(nodeGpus, self.interval)
                print(f"ResourceMonitor: job GPUs {gpus} are node GPUs "
                      f"{', '.join(self._gpus.indexes)} (nvidia-smi index)",
                      flush=True)
            except Exception as e:
                print(f"ResourceMonitor: job GPUs {gpus} ({nodeGpus}) can "
                      f"not be read: {e}", file=sys.stderr, flush=True)
        # The monitor and its children (nvidia-smi) are in the job tree
        me = psutil.Process()
        self._own = {me.pid} | {c.pid for c in me.children(recursive=True)}
        self.columns = list(self.BASE_COLUMNS)
        for i in (self._gpus.indexes if self._gpus else []):
            self.columns += [f'gpu{i}_{c}' for c in self.GPU_COLUMNS]

    def _sampleTree(self, dt):
        """ (procs, cpu %, rss GiB, read MB/s, write MB/s) of the job tree.
        CPU and I/O are the increments since the previous sample of each
        process (all of it for a process started since then). The last
        interval of a process that ended is lost, its children times are
        not added because they would count again what was already seen. """
        root = psutil.Process(self.pid)
        procs = [p for p in [root] + root.children(recursive=True)
                 if p.pid not in self._own]
        cpu = rss = read = write = 0
        ioOk = hasattr(psutil.Process, 'io_counters')  # Not in macOS
        current = {}
        alive = 0
        for p in procs:
            try:
                with p.oneshot():
                    if p.status() == psutil.STATUS_ZOMBIE:
                        continue  # Ended, not waited for yet
                    ct = p.create_time()
                    t = p.cpu_times()
                    secs = t.user + t.system
                    rss += p.memory_info().rss
                    r = w = None
                    if ioOk:
                        try:
                            io = p.io_counters()
                            r, w = io.read_chars, io.write_chars
                        except psutil.AccessDenied:
                            pass
            except psutil.NoSuchProcess:  # ZombieProcess too
                continue
            alive += 1
            prev = self._prev.get(p.pid)
            if prev is None or prev[0] != ct:
                prev = (ct, 0, 0, 0)
            if r is None:  # No increment if it can not be read
                r, w = prev[2], prev[3]
            current[p.pid] = (ct, secs, r, w)
            cpu += max(0, secs - prev[1])
            read += max(0, r - prev[2])
            write += max(0, w - prev[3])

        self._prev = current
        if self._first or not dt:  # No increments yet
            return alive, None, rss / GiB, None, None
        return (alive, 100 * cpu / dt, rss / GiB,
                read / MB / dt if ioOk else None,
                write / MB / dt if ioOk else None)

    def sample(self, elapsed, dt):
        procs, cpu, rss, read, write = self._sampleTree(dt)
        vm = psutil.virtual_memory()
        nodeCpu = psutil.cpu_percent(interval=None)
        row = [elapsed, procs, cpu, rss, read, write,
               None if self._first else nodeCpu,
               (vm.total - vm.available) / GiB]
        self._first = False
        if self._gpus:
            gpuValues = self._gpus.read()
            for i in self._gpus.indexes:
                row += list(gpuValues.get(i, (None, None, None)))
        return row

    @staticmethod
    def _format(v):
        if v is None:
            return ''
        if isinstance(v, float):
            return f'{v:.2f}'.rstrip('0').rstrip('.')
        return str(v)

    def run(self):
        """ Sample until stop() or until the monitored process is gone. """
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *args: self._stop.set())
        psutil.cpu_percent(interval=None)  # Start node CPU counting
        start = last = time.time()
        with open(self.output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(self.columns)
            f.flush()
            while not self._stop.is_set():
                now = time.time()
                try:
                    row = self.sample(now - start, now - last)
                except psutil.NoSuchProcess:
                    break  # The job is gone
                last = now
                writer.writerow([self._format(v) for v in row])
                f.flush()
                # Keep the pace even if a sample took a while
                self._stop.wait(max(0.0, self.interval - (time.time() - now)))
        if self._gpus:
            self._gpus.close()

    def stop(self):
        self._stop.set()

    # ---------------- Helpers for the process launching the monitor --------
    @staticmethod
    def launch(pid, output, interval=2, gpus=None):
        """ Start the monitor of the process pid in a new (low priority)
        process, writing to output. gpus: CUDA device ids of the job, or
        'all' (see resolve_gpus). Returns the subprocess.Popen. """
        cmd = [sys.executable, '-m', 'emtools.scripts.emt_monitor',
               '--pid', str(pid), '--output', output,
               '--interval', str(interval)]
        if gpus:
            cmd += ['--gpus', gpus if isinstance(gpus, str)
                    else ','.join(str(g) for g in gpus)]
        return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, close_fds=True)

    @staticmethod
    def terminate(proc, timeout=10):
        """ Stop a monitor started with launch(), it writes its last row. """
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout)
            except subprocess.TimeoutExpired:
                proc.kill()

    @staticmethod
    def summarize(csvFile):
        """ Summary of a monitor CSV file: duration, number of samples and,
        for each column, its average and maximum ('read_gb' and 'write_gb'
        are the totals of the job I/O). Empty dict if there are no rows. """
        with open(csvFile, newline='') as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return {}

        def _values(col):
            return [float(r[col]) for r in rows if r.get(col) not in (None, '')]

        times = _values('time')
        summary = {'duration': round(times[-1]) if times else 0,
                   'samples': len(rows)}
        for col in rows[0]:
            if col == 'time' or not (values := _values(col)):
                continue
            summary[col] = {'avg': round(sum(values) / len(values), 2),
                            'max': round(max(values), 2)}
        for col, key in [('read_mbs', 'read_gb'), ('write_mbs', 'write_gb')]:
            pairs = [(float(r['time']), float(r[col])) for r in rows if r[col]]
            total, prevT = 0, 0
            for t, v in pairs:
                total += v * (t - prevT) * MB
                prevT = t
            if pairs:
                summary[key] = round(total / 1e9, 2)
        return summary

    @staticmethod
    def csv_gpus(csvFile):
        """ nvidia-smi indexes of the GPUs in a CSV file (its columns). """
        with open(csvFile, newline='') as f:
            header = next(csv.reader(f), [])
        return [c[3:-5] for c in header if c.startswith('gpu') and c.endswith('_util')]

    @staticmethod
    def summary_lines(summary):
        """ Lines to log a summary from summarize(). """
        if not summary:
            return ["Resource usage: no samples"]

        def _stat(key, unit='', fmt='.1f'):
            s = summary.get(key)
            return f"avg {s['avg']:{fmt}}{unit}, max {s['max']:{fmt}}{unit}" if s else 'n/a'

        lines = [f"Resource usage ({summary['samples']} samples, "
                 f"{summary['duration']} s)",
                 f"  CPU (100% = 1 core): {_stat('cpu', '%')}",
                 f"  Memory (RSS): max {summary['rss_gb']['max']:.1f} GiB"
                 if 'rss_gb' in summary else "  Memory (RSS): n/a"]
        if 'read_gb' in summary:
            lines.append(f"  I/O: read {summary['read_gb']} GB, "
                         f"written {summary.get('write_gb')} GB")
        gpus = sorted({k.split('_')[0] for k in summary if k.startswith('gpu')})
        for g in gpus:
            mem = summary.get(f'{g}_mem_gb')
            lines.append(f"  {g.upper()}: util {_stat(f'{g}_util', '%')}, "
                         f"memory max {mem['max'] if mem else 'n/a'} GiB, "
                         f"power {_stat(f'{g}_power', ' W', '.0f')}")
        return lines
