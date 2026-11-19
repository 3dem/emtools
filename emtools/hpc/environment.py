#!/usr/bin/env python3
# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [1]
# *
# * [1] SciLifeLab, Stockholm University
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'delarosatrevin@scilifelab.se'
# *
# **************************************************************************

""" Computing environment of the running process: the node (host, CPUs,
memory and GPUs) and the cluster job (LSF or Slurm) it runs in, if any.
"""

import os
import subprocess

from ..utils import System


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe(func, default=None):
    try:
        return func()
    except Exception:
        return default


class ClusterJob:
    """ Cluster job (LSF or Slurm) running the current process. """

    @staticmethod
    def current():
        """ Cluster job running this process, read from its environment
        variables, or None if it is running locally. """
        env = os.environ

        if job_id := env.get('LSB_JOBID'):
            hosts = env.get('LSB_HOSTS', '').split()  # one entry per slot
            return {'system': 'LSF', 'job_id': job_id,
                    'queue': env.get('LSB_QUEUE'),
                    'cpus': _int(env.get('LSB_DJOB_NUMPROC')) or len(hosts) or None,
                    'hosts': ' '.join(sorted(set(hosts))) or None}
        if job_id := env.get('SLURM_JOB_ID'):
            return {'system': 'Slurm', 'job_id': job_id,
                    'queue': env.get('SLURM_JOB_PARTITION'),
                    'cpus': _int(env.get('SLURM_CPUS_ON_NODE')),
                    'hosts': env.get('SLURM_JOB_NODELIST')}
        return None

    @staticmethod
    def memory(cluster, timeout=10):
        """ Max and average memory used (up to now) by a cluster job (as
        returned by current), as reported by LSF bjobs or Slurm sstat,
        or None. """
        if cluster['system'] == 'LSF':
            cmd = ['bjobs', '-noheader', '-o', "max_mem avg_mem delimiter='|'",
                   cluster['job_id']]
        else:
            cmd = ['sstat', '-n', '-P', '-j', f"{cluster['job_id']}.batch",
                   '--format=MaxRSS,AveRSS']
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return None
        lines = p.stdout.strip().splitlines() if p.returncode == 0 else []
        if not lines:
            return None
        values = [v.strip() for v in lines[0].split('|')] + ['', '']
        memory = {k: v for k, v in zip(['max', 'avg'], values) if v and v != '-'}
        return memory or None


class ComputingEnv:
    """ Computing environment of the current process. """

    @staticmethod
    def collect(gpu_ids=(), cpus=None):
        """ Computing environment of this process: the node (host, CPUs,
        memory and GPUs), the given CPUs and GPU ids used by the job, the
        type of those GPUs and, if running as a cluster job, its id, queue
        and CPUs. It never fails, missing values are None.

        Args:
            gpu_ids: GPU ids used by the job, relative to CUDA_VISIBLE_DEVICES
                if it is set.
            cpus: number of CPUs used by the job.
        """
        gpu_ids = list(gpu_ids or [])
        node_gpus = _safe(System.gpus, []) or []
        visible = os.environ.get('CUDA_VISIBLE_DEVICES', '').strip()
        visible_ids = [v.strip() for v in visible.split(',') if v.strip()]
        # The job GPU ids are relative to the visible devices (if set)
        indexes = [visible_ids[i] if i < len(visible_ids) else str(i)
                   for i in gpu_ids]
        gpu_names = {g.get('name') for g in node_gpus if g.get('index') in indexes}
        if gpu_ids and not gpu_names:
            # Not mapped (e.g. GPU UUIDs), it is clear if all are the same type
            if len(names := {g.get('name') for g in node_gpus}) == 1:
                gpu_names = names

        return {
            'host': _safe(System.hostname),
            'node': {
                'cpus': _safe(System.cpus),
                'memory': _safe(System.memory),  # GiB
                'gpus': [{'index': g.get('index'), 'name': g.get('name'),
                          'memory': g.get('memory.total')} for g in node_gpus]
            },
            'cpus': cpus,
            'gpus': len(gpu_ids),
            'gpu_ids': gpu_ids,
            'gpu_type': ', '.join(sorted(n for n in gpu_names if n)) or None,
            'cuda_visible_devices': visible or None,
            'cluster': ClusterJob.current()
        }

    @staticmethod
    def lines(info):
        """ Lines to log a computing environment dict (see collect). """
        node = info.get('node') or {}
        gpus = {}
        for g in node.get('gpus') or []:
            key = f"{g['name']} ({g['memory']})" if g.get('memory') else g['name']
            gpus[key] = gpus.get(key, 0) + 1
        node_gpus = ', '.join(f"{n} x {name}" for name, n in gpus.items()) or 'no GPUs'
        lines = ["Computing environment",
                 f"  Host: {info.get('host')}",
                 f"  Node: {node.get('cpus')} CPUs, {node.get('memory')} GiB memory, "
                 f"{node_gpus}"]
        if cluster := info.get('cluster'):
            lines.append(f"  Cluster: {cluster['system']} job {cluster['job_id']}, "
                         f"queue: {cluster.get('queue')}, CPUs: {cluster.get('cpus')}, "
                         f"hosts: {cluster.get('hosts')}")
        else:
            lines.append("  Cluster: none (running locally)")
        lines.append(f"  Job CPUs (params): {info.get('cpus')}")
        gpu_line = f"  Job GPUs: {info.get('gpus')}"
        if info.get('gpus'):
            gpu_line += (f", ids: {' '.join(str(i) for i in info['gpu_ids'])}"
                         f", type: {info.get('gpu_type')}")
        if visible := info.get('cuda_visible_devices'):
            gpu_line += f", CUDA_VISIBLE_DEVICES={visible}"
        lines.append(gpu_line)
        return lines
