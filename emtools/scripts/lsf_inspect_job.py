#!/usr/bin/env python3
"""
Inspect an LSF job: its request, state and, if pending, why it has not started and whether it ever can.

The job request (slots, span, memory, GPUs, select[] expression, -m hosts)
is compared against the static capacity of every host in the job's queue:

  NEVER     No host (or not enough hosts) could satisfy the request even if
            the whole queue were idle. The job must be modified or killed.
  BLOCKED   The request fits, but the job cannot start until someone acts:
            the queue is closed, the hosts that fit are down/closed by an
            admin, or the job is held (PSUSP).
  WAITING   The request fits on hosts that are currently busy, or the job is
            held back by a limit/dependency. It should start once resources
            are freed.
  READY     Enough resources appear free right now. If the job stays pending,
            the cause is a scheduling policy (fairshare, guarantees,
            reservations for other jobs) rather than capacity.

A job that is not pending (e.g. running) is reported with its execution
host(s), run time and memory usage (NOT_PENDING).

Usage:
    lsf_inspect_job.py JOBID [--json] [-v] [--timeout SECONDS]

Exit codes: 0 = waiting/ready/not pending, 1 = error, 2 = NEVER, 3 = BLOCKED
With --json the exit code is 0 unless there is an error, and errors are also
printed as JSON ({"error": ...}), e.g. for the EMhub 'inspect' queue command.
"""

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# bjobs -l wraps long lines with a 21-space indentation
WRAP_RE = re.compile(r'\n {21}')

UNITS_MB = {'': 1.0, 'K': 1.0 / 1024, 'M': 1.0, 'G': 1024.0, 'T': 1024.0 ** 2}

HOST_UP = {'ok'}
HOST_BUSY = {'closed_full', 'closed_excl', 'closed_busy', 'closed_cu_excl', 'closed_wind'}

EXIT_OK, EXIT_ERROR, EXIT_NEVER, EXIT_BLOCKED = 0, 1, 2, 3

# Version of the --json output format
SCHEMA = 1

# Timeout (seconds) of each LSF command, set from --timeout
TIMEOUT = 20


def run(args, timeout=None):
    timeout = timeout or TIMEOUT
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=timeout)
    except FileNotFoundError:
        raise SystemExit(f"ERROR: command not found: {args[0]} (is LSF in PATH?)")
    except subprocess.TimeoutExpired:
        raise SystemExit(f"ERROR: timeout running: {' '.join(args)}")
    return p.stdout, p.stderr, p.returncode


def to_mb(text) -> Optional[float]:
    m = re.match(r'^\s*([\d.]+)\s*([KMGT]?)B?\s*$', str(text), re.I)
    if not m:
        return None
    return float(m.group(1)) * UNITS_MB[m.group(2).upper()]


def fmt_mb(mb: Optional[float]) -> str:
    if mb is None:
        return '-'
    if mb >= 1024 ** 2:
        return f'{mb / 1024 ** 2:.1f}T'
    if mb >= 1024:
        return f'{mb / 1024:.0f}G'
    return f'{mb:.0f}M'


def fmt_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    d, h = divmod(h, 24)
    m = rem // 60
    return f'{d}d {h}h {m}m' if d else f'{h}h {m}m'


# --------------------------------------------------------------------------
# select[] expression evaluation
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"""\s*(?:
    (?P<num>\d+(?:\.\d+)?)(?P<unit>[KMGTkmgt]?)(?![\w])
  | (?P<str>'[^']*'|"[^"]*")
  | (?P<op>&&|\|\||==|!=|>=|<=|=|>|<|!|\(|\)|,)
  | (?P<id>[A-Za-z_][\w.\-]*)
)""", re.X)

STRING_ATTRS = {'hname', 'host', 'hostname', 'type', 'model'}
NUMERIC_ATTRS = {'ncpus', 'maxmem', 'maxswp', 'cpuf', 'ngpus', 'ngpus_physical', 'maxslots'}


class SelectExpr:
    """Minimal evaluator for LSF select[] strings against static host data.
    Dynamic load indices (r1m, mem, tmp, ...) cannot be judged statically and
    evaluate to True; they are reported in `unknown`."""

    def __init__(self, text: str):
        self.text = text.strip()
        self.tokens = self._tokenize(self.text)
        self.pos = 0
        self.ast = self._parse_or() if self.tokens else ('true',)
        self.unknown: Set[str] = set()

    @staticmethod
    def _tokenize(text):
        tokens, pos = [], 0
        while pos < len(text):
            m = _TOKEN_RE.match(text, pos)
            if not m or m.end() == pos:
                if text[pos:].strip():
                    raise ValueError(f"cannot parse select expression near: {text[pos:]!r}")
                break
            pos = m.end()
            if m.group('num') is not None:
                tokens.append(('num', float(m.group('num')) * UNITS_MB.get(m.group('unit').upper(), 1.0)
                               if m.group('unit') else float(m.group('num'))))
            elif m.group('str') is not None:
                tokens.append(('str', m.group('str')[1:-1]))
            elif m.group('op') is not None:
                tokens.append(('op', m.group('op')))
            elif m.group('id') is not None:
                tokens.append(('id', m.group('id')))
        return tokens

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _next(self):
        tok = self._peek()
        self.pos += 1
        return tok

    def _parse_or(self):
        node = self._parse_and()
        while self._peek() == ('op', '||'):
            self._next()
            node = ('or', node, self._parse_and())
        return node

    def _parse_and(self):
        node = self._parse_unary()
        while self._peek() == ('op', '&&'):
            self._next()
            node = ('and', node, self._parse_unary())
        return node

    def _parse_unary(self):
        if self._peek() == ('op', '!'):
            self._next()
            return ('not', self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self):
        kind, val = self._peek()
        if (kind, val) == ('op', '('):
            self._next()
            node = self._parse_or()
            if self._next() != ('op', ')'):
                raise ValueError(f"unbalanced parentheses in select: {self.text!r}")
            return node
        lhs = self._parse_operand()
        kind, val = self._peek()
        if kind == 'op' and val in ('==', '!=', '>=', '<=', '=', '>', '<'):
            self._next()
            return ('cmp', '==' if val == '=' else val, lhs, self._parse_operand())
        return ('bool', lhs)

    def _parse_operand(self):
        kind, val = self._next()
        if kind == 'id' and self._peek() == ('op', '('):
            self._next()
            args = []
            while self._peek() not in (('op', ')'), (None, None)):
                tok = self._next()
                if tok != ('op', ','):
                    args.append(tok)
            self._next()
            return ('func', val, args)
        if kind in ('num', 'str', 'id'):
            return (kind, val)
        raise ValueError(f"unexpected token {val!r} in select: {self.text!r}")

    def evaluate(self, host: 'Host', known_resources: Set[str]) -> bool:
        return bool(self._eval(self.ast, host, known_resources))

    def _numeric(self, name, host):
        return {
            'ncpus': host.ncpus, 'maxmem': host.maxmem_mb, 'cpuf': host.cpuf,
            'ngpus': len(host.gpus), 'ngpus_physical': len(host.gpus),
            'maxslots': host.max_slots,
        }.get(name)

    def _eval(self, node, host, known):
        op = node[0]
        if op == 'true':
            return True
        if op == 'or':
            return self._eval(node[1], host, known) or self._eval(node[2], host, known)
        if op == 'and':
            return self._eval(node[1], host, known) and self._eval(node[2], host, known)
        if op == 'not':
            return not self._eval(node[1], host, known)
        if op == 'bool':
            return self._eval_bool(node[1], host, known)
        if op == 'cmp':
            return self._eval_cmp(node[1], node[2], node[3], host)
        return True

    def _eval_bool(self, operand, host, known):
        kind, val = operand[0], operand[1]
        if kind == 'func':
            if val == 'defined' and operand[2]:
                return operand[2][0][1] in host.resources
            self.unknown.add(f'{val}()')
            return True
        if kind == 'num':
            return val != 0
        if kind == 'id':
            if val in NUMERIC_ATTRS:
                num = self._numeric(val, host)
                return bool(num) if num is not None else True
            if val in known:
                return val in host.resources
            self.unknown.add(val)
            return True
        return True

    def _eval_cmp(self, cmp, lhs, rhs, host):
        lname = lhs[1] if lhs[0] == 'id' else None
        if lname in STRING_ATTRS:
            right = str(rhs[1])
            if lname == 'type' and right in ('local', 'any'):
                return cmp == '=='
            left = {'hname': host.name, 'host': host.name, 'hostname': host.name,
                    'type': host.type, 'model': host.model}[lname]
            if cmp == '==':
                return left == right
            if cmp == '!=':
                return left != right
            return True
        if lname in NUMERIC_ATTRS and rhs[0] == 'num':
            left = self._numeric(lname, host)
            if left is None:
                return True
            right = rhs[1]
            return {'==': left == right, '!=': left != right, '>=': left >= right,
                    '<=': left <= right, '>': left > right, '<': left < right}[cmp]
        if lname:
            self.unknown.add(lname)
        return True


# --------------------------------------------------------------------------
# Job and host data
# --------------------------------------------------------------------------

@dataclass
class GpuRequest:
    num: float = 1
    per: str = 'host'           # 'host' or 'task'
    mig: Optional[str] = None   # e.g. '2' or '2/1' when MIG slices requested
    gmodel: Optional[str] = None
    gmem: Optional[str] = None
    exclusive: bool = True
    raw: str = ''


@dataclass
class Host:
    name: str
    status: str = 'unknown'
    max_slots: Optional[int] = None
    njobs: int = 0
    ncpus: Optional[int] = None
    maxmem_mb: Optional[float] = None
    cpuf: Optional[float] = None
    type: str = ''
    model: str = ''
    resources: Set[str] = field(default_factory=set)
    gpus: List[dict] = field(default_factory=list)   # {'model','mig','njobs'}
    load: Dict[str, Tuple[str, str]] = field(default_factory=dict)  # index -> (total, reserved)


def bracket_sections(resreq: str) -> Dict[str, str]:
    """Split 'select[..] rusage[..] span[..]' into {name: content}."""
    sections, i = {}, 0
    while i < len(resreq):
        m = re.compile(r'(\w+)\[').search(resreq, i)
        if not m:
            break
        depth, j = 1, m.end()
        while j < len(resreq) and depth:
            depth += {'[': 1, ']': -1}.get(resreq[j], 0)
            j += 1
        sections.setdefault(m.group(1), resreq[m.end():j - 1])
        i = j
    return sections


def parse_gpu_request(text: str) -> Optional[GpuRequest]:
    if not text or text.strip() in ('-', ''):
        return None
    req = GpuRequest(raw=text)
    for item in text.split(':'):
        if '=' not in item:
            continue
        key, val = item.split('=', 1)
        key = key.strip().lower()
        if key == 'num':
            num, _, per = val.partition('/')
            req.num = float(num)
            req.per = per or 'host'
        elif key == 'mig':
            req.mig = val
        elif key == 'gmodel':
            req.gmodel = val
        elif key == 'gmem':
            req.gmem = val
        elif key == 'j_exclusive':
            req.exclusive = val.lower() == 'yes'
        elif key == 'mode' and val.startswith('exclusive'):
            req.exclusive = True
    return req


def load_job(jobid: str) -> dict:
    fields = ('jobid stat queue user job_name nreq_slot combined_resreq memlimit sla '
              'pend_reason dependency pend_time submit_time start_time exec_host '
              'run_time max_mem avg_mem')
    out, err, _ = run(['bjobs', '-o', fields, '-json', jobid])
    try:
        recs = json.loads(out).get('RECORDS', [])
    except ValueError:
        raise SystemExit(f"ERROR: could not parse bjobs output: {(err or out).strip()}")
    if not recs:
        raise SystemExit(f"ERROR: {err.strip() or 'job not found'}")
    if 'ERROR' in recs[0]:
        raise SystemExit(f"ERROR: {recs[0]['ERROR']}")
    return recs[0]


def load_job_details(jobid: str) -> dict:
    out, _, _ = run(['bjobs', '-l', jobid])
    text = WRAP_RE.sub('', out)
    details = {'specified_hosts': [], 'gpu': None}
    m = re.search(r'Specified Hosts ((?:<[^>]*>,?\s*)+);', text)
    if m:
        details['specified_hosts'] = re.findall(r'<([^>]*)>', m.group(1))
    m = (re.search(r'GPU REQUIREMENT DETAILS:\s*Combined:\s*(\S+)', text)
         or re.search(r'Requested GPU <([^>]*)>', text))
    if m:
        details['gpu'] = m.group(1)
    return details


def load_pending_reasons(jobid: str) -> List[dict]:
    """Parse `bjobs -p3` into [{'section','reason','hosts'}]."""
    out, _, _ = run(['bjobs', '-p3', jobid])
    reasons, section = [], 'job'
    for line in out.splitlines()[1:]:
        if not line.strip() or re.match(r'^\d', line):
            continue
        hdr = re.match(r'^\s*(Candidate|Non-candidate) host pending reasons', line)
        if hdr:
            section = hdr.group(1).lower()
            continue
        m = re.match(r'^\s*(.*?)(?::\s*(\d+)\s+hosts?)?;?\s*$', line)
        if m and m.group(1):
            reasons.append({'section': section, 'reason': m.group(1).rstrip(';'),
                            'hosts': int(m.group(2)) if m.group(2) else None})
    return reasons


def load_queue(qname: str) -> dict:
    out, _, _ = run(['bqueues', '-o', 'queue_name status', '-json', qname])
    status = 'unknown'
    try:
        recs = json.loads(out).get('RECORDS', [])
        if recs and 'STATUS' in recs[0]:
            status = recs[0]['STATUS']
    except ValueError:
        pass
    out, _, _ = run(['bqueues', '-l', qname])
    hosts = re.search(r'^HOSTS:\s*(.*)$', out, re.M)
    users = re.search(r'^USERS:\s*(.*)$', out, re.M)
    return {'status': status,
            'hosts': hosts.group(1).split() if hosts else ['all'],
            'users': users.group(1).split() if users else ['all']}


_group_cache: Dict[Tuple[str, str], Optional[List[str]]] = {}


def expand_group(cmd: str, name: str) -> Optional[List[str]]:
    """Expand a host group (bmgroup) or user group (bugroup) recursively."""
    key = (cmd, name)
    if key not in _group_cache:
        out, _, rc = run([cmd, '-r', '-w', name])
        lines = out.strip().splitlines()
        members = None
        if rc == 0 and len(lines) >= 2:
            toks = lines[1].split()
            if toks and toks[0] == name:
                members = toks[1:]
        _group_cache[key] = members
    return _group_cache[key]


def expand_host_list(tokens: List[str], all_hosts: List[str]) -> Set[str]:
    included, excluded = set(), set()
    for tok in tokens:
        tok = re.sub(r'\+\d+$', '', tok)
        target = excluded if tok.startswith('~') else included
        tok = tok.lstrip('~')
        if tok in ('all', 'others', 'allremote'):
            target.update(all_hosts)
        elif tok == 'none':
            continue
        else:
            members = expand_group('bmgroup', tok.rstrip('/'))
            if members is None:
                target.add(tok.rstrip('/'))
            elif 'all' in members:
                target.update(all_hosts)
            else:
                target.update(members)
    return included - excluded


def user_allowed(user: str, tokens: List[str]) -> Optional[bool]:
    """True/False if membership could be determined, None otherwise."""
    if not tokens or tokens[0] == 'all':
        return True
    undetermined = False
    for tok in tokens:
        name = tok.rstrip('/')
        if name.startswith('~'):
            continue
        if name == user:
            return True
        if tok.endswith('/'):
            members = expand_group('bugroup', name)
            if members is None:
                undetermined = True
            elif user in members or 'all' in members:
                return True
    return None if undetermined else False


def load_hosts() -> Dict[str, Host]:
    hosts: Dict[str, Host] = {}
    out, _, _ = run(['lshosts', '-w'])
    row = re.compile(r'^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*(?:\((.*)\))?\s*$')
    for line in out.splitlines()[1:]:
        m = row.match(line)
        if not m:
            continue
        h = Host(name=m.group(1), type=m.group(2), model=m.group(3))
        h.cpuf = float(m.group(4)) if re.match(r'^[\d.]+$', m.group(4)) else None
        h.ncpus = int(m.group(5)) if m.group(5).isdigit() else None
        h.maxmem_mb = to_mb(m.group(6))
        h.resources = set((m.group(9) or '').split())
        hosts[h.name] = h

    out, _, _ = run(['bhosts', '-w'])
    for line in out.splitlines()[1:]:
        toks = line.split()
        if len(toks) < 5:
            continue
        h = hosts.setdefault(toks[0], Host(name=toks[0]))
        h.status = toks[1]
        h.max_slots = int(toks[3]) if toks[3].isdigit() else h.ncpus
        h.njobs = int(toks[4]) if toks[4].isdigit() else 0
    return hosts


def load_host_details(hosts: Dict[str, Host], names: List[str]):
    """Fill GPU inventory and current scheduling load for the given hosts."""
    if not names:
        return
    out, _, _ = run(['lshosts', '-gpu', '-w'] + names)
    current = None
    for line in out.splitlines()[1:]:
        toks = line.split()
        if not toks:
            continue
        if not line[0].isspace() and toks[0] in hosts:
            current, toks = hosts[toks[0]], toks[1:]
        if current is not None and len(toks) >= 7 and toks[0].isdigit():
            current.gpus.append({'model': toks[1], 'mig': toks[-1].upper() == 'Y', 'njobs': 0})

    out, _, _ = run(['bhosts', '-gpu', '-w'] + names)
    current, idx = None, 0
    for line in out.splitlines()[1:]:
        toks = line.split()
        if not toks:
            continue
        if not line[0].isspace() and toks[0] in hosts:
            current, idx, toks = hosts[toks[0]], 0, toks[1:]
        if current is not None and len(toks) >= 8 and toks[0].isdigit():
            if idx < len(current.gpus) and toks[-4].isdigit():
                current.gpus[idx]['njobs'] = int(toks[-4])
            idx += 1

    out, _, _ = run(['bhosts', '-l'] + names)
    current, header = None, []
    for line in out.splitlines():
        m = re.match(r'^HOST\s+(\S+)', line)
        if m:
            current, header = hosts.get(m.group(1)), []
            continue
        toks = line.split()
        if current is None or not toks:
            continue
        if toks[0] in ('Total', 'Reserved') and header:
            for i, name in enumerate(header):
                if i + 1 < len(toks):
                    total, reserved = current.load.get(name, ('-', '-'))
                    if toks[0] == 'Total':
                        total = toks[i + 1]
                    else:
                        reserved = toks[i + 1]
                    current.load[name] = (total, reserved)
        elif toks[0] not in ('loadSched', 'loadStop') and line.startswith(' ' * 8):
            header = toks


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

REASON_CATEGORIES = [
    ('held', ('suspended by', 'held', 'psusp')),
    ('dependency', ('dependency',)),
    ('limit', ('limit', 'fairshare', 'running element', 'priority', 'service class',
               'guarantee', 'sla ', 'quota', 'share')),
    ('infra', ('closed by lsf administrator', 'load information unavailable',
               'unable to reach', 'unavail', 'lim is down', 'locked', 'closed_lock')),
    ('config', ("resource requirements not satisfied", 'not specified in job submission',
                'no access', 'not a member', 'not usable', 'not a candidate')),
    ('resources', ('not enough', 'reservation', 'reserving resource', 'gpu resources',
                   'load threshold', 'job slot', 'busy', 'exclusive', 'memory')),
]


CHECKS = [
    ('job_state', 'Job is pending'),
    ('held', 'Job is not held'),
    ('dependency', 'Dependency can be satisfied'),
    ('queue_open', 'Queue is open and active'),
    ('user_access', 'User may submit to the queue'),
    ('host_list', 'Queue (and -m) hosts exist'),
    ('request_fit', 'Request fits on idle hosts'),
    ('hosts_up', 'Fitting hosts are in service'),
    ('free_now', 'Resources are free right now'),
    ('limits', 'No limit or policy holding the job'),
]


def classify_reason(text: str) -> str:
    low = text.lower()
    for category, needles in REASON_CATEGORIES:
        if any(n in low for n in needles):
            return category
    return 'other'


class Analysis:
    def __init__(self, job: dict, details: dict, reasons: List[dict], queue: dict,
                 hosts: Dict[str, Host]):
        self.job, self.details, self.reasons, self.queue, self.hosts = job, details, reasons, queue, hosts
        self.notes: List[str] = []
        self.checks: Dict[str, dict] = {}
        self.host_rows: List[dict] = []
        self._parse_request()

    def _parse_request(self):
        job = self.job
        self.nslots = int(job['NREQ_SLOT']) if str(job.get('NREQ_SLOT', '')).isdigit() else 1
        self.resreq = job.get('COMBINED_RESREQ') or ''
        sec = bracket_sections(self.resreq)
        self.select_text = sec.get('select', '')
        self.select = SelectExpr(self.select_text)

        self.mem_per_slot = 0.0
        self.rusage_gpus = None
        for item in re.split(r'[:,]', sec.get('rusage', '')):
            key, _, val = item.partition('=')
            if key.strip() == 'mem':
                self.mem_per_slot = to_mb(val) or 0.0
            elif key.strip() in ('ngpus_physical', 'ngpus', 'ngpus_excl_p', 'ngpus_shared'):
                self.rusage_gpus = val

        span = sec.get('span', '')
        ptile = re.search(r'ptile=(\d+)', span)
        if ptile:
            self.per_host = min(int(ptile.group(1)), self.nslots)
            self.hosts_needed = math.ceil(self.nslots / int(ptile.group(1)))
        elif re.search(r'hosts=1\b', span):
            self.per_host, self.hosts_needed = self.nslots, 1
        else:
            self.per_host, self.hosts_needed = None, None   # free distribution

        self.gpu = parse_gpu_request(self.details.get('gpu') or '')
        if self.gpu is None and self.rusage_gpus:
            num, _, per = self.rusage_gpus.partition('/')
            self.gpu = GpuRequest(num=float(num), per=per or 'host', raw=f'rusage {self.rusage_gpus}')

    # -- per host -----------------------------------------------------------

    def eligible_gpus(self, host: Host) -> List[dict]:
        if not self.gpu:
            return []
        want_mig = bool(self.gpu.mig) and self.gpu.mig.lower() != 'no'
        gpus = [g for g in host.gpus if g['mig'] == want_mig]
        if self.gpu.gmodel:
            model = self.gpu.gmodel.split('#')[0].lower()
            gpus = [g for g in gpus if model in g['model'].lower()]
        return gpus

    def gpus_on_host(self, slots_on_host: int) -> float:
        if not self.gpu:
            return 0
        return self.gpu.num * slots_on_host if self.gpu.per == 'task' else self.gpu.num

    def gpu_shortfall_text(self, host: Host, need: float, have: int) -> str:
        if not host.gpus:
            return 'host has no GPUs'
        n_mig = sum(g['mig'] for g in host.gpus)
        want_mig = bool(self.gpu.mig) and self.gpu.mig.lower() != 'no'
        if not want_mig and n_mig:
            return f'needs {need:g} non-MIG GPUs, host has {have} ({n_mig} of {len(host.gpus)} are in MIG mode)'
        if want_mig:
            return f'needs {need:g} MIG GPUs, host has {have} MIG-enabled'
        if self.gpu.gmodel:
            return f'needs {need:g} GPUs of model {self.gpu.gmodel}, host has {have}'
        return f'needs {need:g} GPUs, host has {have}'

    def static_capacity(self, host: Host) -> Tuple[int, List[Tuple[str, str]]]:
        """Return (max slots this host could ever give the job, failures)."""
        fails: List[Tuple[str, str]] = []
        if self.select_text and not self.select.evaluate(host, self.known_resources):
            fails.append(('select', f'does not match select[{self.select_text}]'))
        max_slots = host.max_slots if host.max_slots is not None else (host.ncpus or 0)
        eligible = len(self.eligible_gpus(host))

        if self.per_host is not None:
            need = self.per_host
            if need > max_slots:
                fails.append(('slots', f'needs {need} slots on one host, host has {max_slots}'))
            mem_need = self.mem_per_slot * need
            if self.mem_per_slot and host.maxmem_mb is not None and mem_need > host.maxmem_mb:
                fails.append(('memory', f'needs {fmt_mb(mem_need)} on one host, host has {fmt_mb(host.maxmem_mb)}'))
            gpu_need = self.gpus_on_host(need)
            if gpu_need > eligible:
                fails.append(('gpu', self.gpu_shortfall_text(host, gpu_need, eligible)))
            return (0 if fails else need), fails

        cap = max_slots
        if self.mem_per_slot and host.maxmem_mb is not None:
            cap = min(cap, int(host.maxmem_mb // self.mem_per_slot))
            if cap < 1:
                fails.append(('memory', f'needs {fmt_mb(self.mem_per_slot)} per slot, host has {fmt_mb(host.maxmem_mb)}'))
        if self.gpu:
            if self.gpu.per == 'task':
                cap = min(cap, int(eligible // self.gpu.num))
            elif eligible < self.gpu.num:
                cap = 0
            if cap < 1:
                fails.append(('gpu', self.gpu_shortfall_text(host, self.gpus_on_host(1), eligible)))
        if max_slots < 1:
            fails.append(('slots', 'host has no job slots'))
        return (0 if fails else cap), fails

    def current_free(self, host: Host) -> Tuple[int, Optional[float], int]:
        """Approximate free slots, memory (MB) and eligible GPUs right now."""
        slots_total = host.load.get('slots', ('-', '-'))[0]
        if slots_total.isdigit():
            free_slots = int(slots_total)
        else:
            free_slots = max((host.max_slots or 0) - host.njobs, 0)
        mem_total, mem_reserved = host.load.get('mem', ('-', '-'))
        free_mem = to_mb(mem_total)
        reserved = to_mb(mem_reserved)
        if free_mem is not None and reserved is not None and host.maxmem_mb is not None:
            free_mem = min(free_mem, host.maxmem_mb - reserved)
        eligible = self.eligible_gpus(host)
        free_gpus = sum(1 for g in eligible if g['njobs'] == 0) if self.gpu and self.gpu.exclusive else len(eligible)
        return free_slots, free_mem, free_gpus

    def busy_dimensions(self, host: Host, slots_on_host: int) -> List[str]:
        free_slots, free_mem, free_gpus = self.current_free(host)
        busy = []
        if free_slots < slots_on_host:
            busy.append(f'slots {free_slots}/{slots_on_host} free')
        if self.mem_per_slot and free_mem is not None and free_mem < self.mem_per_slot * slots_on_host:
            busy.append(f'memory {fmt_mb(max(free_mem, 0))}/{fmt_mb(self.mem_per_slot * slots_on_host)} free')
        gpu_need = self.gpus_on_host(slots_on_host)
        if gpu_need and free_gpus < gpu_need:
            busy.append(f'GPUs {free_gpus}/{gpu_need:g} free')
        return busy

    # -- whole job ----------------------------------------------------------

    def run(self) -> dict:
        job = self.job

        def _value(key):
            value = job.get(key)
            return None if value in (None, '', '-') else value

        result = {
            'schema': SCHEMA,
            'job': {
                'id': job.get('JOBID'), 'user': job.get('USER'), 'queue': job.get('QUEUE'),
                'name': _value('JOB_NAME'),
                'status': job.get('STAT'), 'service_class': job.get('SERVICE_CLASS') or None,
                'pending_seconds': int(job['PEND_TIME']) if str(job.get('PEND_TIME', '')).isdigit() else None,
                'submit_time': _value('SUBMIT_TIME'), 'start_time': _value('START_TIME'),
                'exec_host': _value('EXEC_HOST'), 'run_time': _value('RUN_TIME'),
                'max_mem': _value('MAX_MEM'), 'avg_mem': _value('AVG_MEM'),
            },
            'request': self.request_summary(),
            'reasons': [dict(r, category=classify_reason(r['reason'])) for r in self.reasons],
        }
        stat = job.get('STAT')
        if stat not in ('PEND', 'PSUSP'):
            self.check('job_state', 'info', f'status {stat}, nothing to diagnose')
            result['verdict'] = self.verdict('NOT_PENDING', f'Job is not pending (status {stat}).')
            result['checks'] = self.ordered_checks()
            return result
        self.check('job_state', 'pass', f'status {stat}')

        all_names = sorted(self.hosts)
        queue_hosts = expand_host_list(self.queue['hosts'], all_names)
        specified = self.details.get('specified_hosts') or []
        if specified:
            queue_hosts &= expand_host_list(specified, all_names)
        names = sorted(h for h in queue_hosts if h in self.hosts)
        self.known_resources = set().union(*(self.hosts[h].resources for h in all_names)) if all_names else set()
        load_host_details(self.hosts, names)
        result['queue'] = {'status': self.queue['status'], 'hosts': len(names),
                           'host_list': self.queue['hosts'], 'specified_hosts': specified}

        fit_hosts, dim_fails = [], {}
        for name in names:
            host = self.hosts[name]
            cap, fails = self.static_capacity(host)
            row = {'host': name, 'status': host.status, 'capacity': cap,
                   'max_slots': host.max_slots, 'maxmem_mb': host.maxmem_mb,
                   'gpus': len(host.gpus), 'eligible_gpus': len(self.eligible_gpus(host)),
                   'fails': [f'{d}: {t}' for d, t in fails]}
            for dim, text in fails:
                dim_fails.setdefault(dim, []).append((name, text))
            if not fails:
                free_slots, free_mem, free_gpus = self.current_free(host)
                row.update(free_slots=free_slots, free_mem_mb=free_mem, free_gpus=free_gpus)
                slots_here = self.per_host if self.per_host is not None else 1
                row['busy'] = self.busy_dimensions(host, slots_here)
                status = host.status.lower()
                row['state'] = ('down' if status not in HOST_UP | HOST_BUSY
                                else 'busy' if row['busy'] or status in HOST_BUSY else 'free')
                fit_hosts.append(row)
            else:
                row['state'] = 'never'
            self.host_rows.append(row)
        result['hosts'] = self.host_rows

        if self.select.unknown:
            self.notes.append('select[] terms not evaluated (dynamic or unknown): '
                              + ', '.join(sorted(self.select.unknown)))
        if self.gpu and self.gpu.gmem:
            self.notes.append(f'GPU memory request gmem={self.gpu.gmem} was not checked.')

        result['verdict'] = self.decide(stat, names, fit_hosts, dim_fails)
        result['checks'] = self.ordered_checks()
        result['notes'] = self.notes
        return result

    def request_summary(self) -> dict:
        req = {'slots': self.nslots, 'mem_per_slot_mb': self.mem_per_slot or None,
               'select': self.select_text or None, 'resreq': self.resreq,
               'specified_hosts': self.details.get('specified_hosts') or None}
        if self.per_host is not None:
            req['layout'] = f'{self.hosts_needed} host(s) x {self.per_host} slots'
        else:
            req['layout'] = 'slots may be spread over any number of hosts'
        if self.gpu:
            req['gpu'] = {'num': self.gpu.num, 'per': self.gpu.per, 'mig': self.gpu.mig,
                          'gmodel': self.gpu.gmodel, 'exclusive': self.gpu.exclusive, 'raw': self.gpu.raw}
        return req

    @staticmethod
    def verdict(code: str, summary: str, details: Optional[List[str]] = None,
                suggestions: Optional[List[str]] = None) -> dict:
        return {'code': code, 'summary': summary, 'details': details or [],
                'suggestions': suggestions or []}

    def job_reasons(self, *categories) -> List[str]:
        return [r['reason'] for r in self.reasons
                if r['section'] == 'job' and classify_reason(r['reason']) in categories]

    def check(self, key: str, status: str, detail: str):
        self.checks[key] = {'check': key, 'label': dict(CHECKS)[key], 'status': status, 'detail': detail}

    def ordered_checks(self) -> List[dict]:
        return [self.checks.get(key, {'check': key, 'label': label, 'status': 'skip',
                                      'detail': 'not evaluated, verdict already decided'})
                for key, label in CHECKS]

    def decide(self, stat, names, fit_hosts, dim_fails) -> dict:
        job_user = self.job.get('USER', '')
        if stat == 'PSUSP':
            self.check('held', 'fail', 'job is suspended while pending (PSUSP)')
            return self.verdict('BLOCKED', 'Job is held (PSUSP); it will not start until it is resumed.',
                                suggestions=[f"Run 'bresume {self.job.get('JOBID')}' to release it."])
        self.check('held', 'pass', 'job is not held')

        dep_never = [r['reason'] for r in self.reasons if 'never satisfied' in r['reason'].lower()]
        dependency = self.job.get('DEPENDENCY') or ''
        if dep_never:
            self.check('dependency', 'fail', f'{dependency}: ' + '; '.join(dep_never))
            return self.verdict('NEVER', 'The job dependency can never be satisfied.', dep_never,
                                ['Kill the job or change its dependency with bmod -w.'])
        if self.job_reasons('dependency'):
            self.check('dependency', 'warn', f'waiting on: {dependency}')
        else:
            self.check('dependency', 'pass', f'satisfied: {dependency}' if dependency else 'none')

        if not self.queue['status'].lower().startswith('open:active'):
            self.check('queue_open', 'fail', f"{self.job.get('QUEUE')} is {self.queue['status']}")
            return self.verdict('BLOCKED', f"Queue {self.job.get('QUEUE')} is {self.queue['status']}.",
                                suggestions=['Wait for the queue to be reopened or move the job with bswitch.'])
        self.check('queue_open', 'pass', f"{self.job.get('QUEUE')} is {self.queue['status']}")

        allowed = user_allowed(job_user, self.queue['users'])
        users_text = ' '.join(self.queue['users'])
        if allowed is False:
            self.check('user_access', 'fail', f'{job_user} is not in USERS: {users_text}')
            return self.verdict('NEVER', f"User {job_user} is not allowed in queue {self.job.get('QUEUE')}.",
                                suggestions=['Move the job to a queue the user can access (bswitch).'])
        self.check('user_access', 'pass' if allowed else 'warn',
                   f'{job_user} is in USERS: {users_text}' if allowed
                   else f'could not resolve membership in USERS: {users_text}')

        specified = self.details.get('specified_hosts') or []
        source = ' '.join(self.queue['hosts']) + (f" restricted by -m {' '.join(specified)}" if specified else '')
        if not names:
            self.check('host_list', 'fail', f'no hosts left from {source}')
            return self.verdict('NEVER', 'No hosts are left after combining the queue hosts with the hosts '
                                         'requested with -m.',
                                suggestions=['Remove or fix the -m host list (bmod -mn).'])
        self.check('host_list', 'pass', f'{len(names)} host(s) from {source}')

        if self.per_host is not None:
            feasible = len(fit_hosts) >= self.hosts_needed
            needed_text = f'{self.hosts_needed} host(s) with {self.per_host} slots each'
            have_text = f'{len(fit_hosts)} of {len(names)} hosts can fit'
        else:
            capacity = sum(r['capacity'] for r in fit_hosts)
            feasible = capacity >= self.nslots
            needed_text = f'{self.nslots} slots in total'
            have_text = f'{len(fit_hosts)} of {len(names)} hosts fit, {capacity} slots in total'
        causes = ', '.join(f'{dim} on {len(items)} host(s)' for dim, items in dim_fails.items())
        self.check('request_fit', 'pass' if feasible else 'fail',
                   f'needs {needed_text}; {have_text}' + (f'; excluded by {causes}' if causes else ''))

        if not feasible:
            details = [f'Needs {needed_text}; only {len(fit_hosts)} of {len(names)} queue hosts could ever fit it.']
            for dim, items in sorted(dim_fails.items(), key=lambda kv: -len(kv[1])):
                details.append(f'{dim}: {len(items)} host(s) excluded, e.g. {items[0][0]}: {items[0][1]}')
            return self.verdict('NEVER', 'This request cannot be satisfied by the hosts in the queue, '
                                         'even when they are completely idle.',
                                details, self.never_suggestions(names, dim_fails))

        usable = [r for r in fit_hosts if r['state'] != 'down']
        enough_usable = (len(usable) >= self.hosts_needed if self.per_host is not None
                         else sum(r['capacity'] for r in usable) >= self.nslots)
        down = [f"{r['host']} ({r['status']})" for r in fit_hosts if r['state'] == 'down']
        self.check('hosts_up', 'pass' if enough_usable else 'fail',
                   f'{len(usable)} fitting host(s) in service'
                   + (f"; unavailable: {', '.join(down)}" if down else ''))
        if not enough_usable:
            return self.verdict('BLOCKED', 'The request fits, but the hosts that could run it are down or '
                                           'closed by an administrator.',
                                [f'Hosts that fit but are unavailable: {", ".join(down)}'],
                                ['Ask the cluster admins about the hosts above, or resize the job to fit '
                                 'other hosts.'])

        free = [r for r in usable if r['state'] == 'free']
        free_enough = (len(free) >= self.hosts_needed if self.per_host is not None
                       else sum(min(r['free_slots'], r['capacity']) for r in free) >= self.nslots)
        details = [f'{len(fit_hosts)} of {len(names)} queue hosts can fit this request '
                   f'({len(free)} look free right now).']
        for dim, items in sorted(dim_fails.items(), key=lambda kv: -len(kv[1])):
            hosts_text = ', '.join(name for name, _ in items[:8]) + (' ...' if len(items) > 8 else '')
            details.append(f'{len(items)} host(s) can never run it ({dim}): {hosts_text} '
                           f'- e.g. {items[0][1]}')

        free_detail = (f"{len(free)} fitting host(s) free now"
                       + (f": {', '.join(r['host'] for r in free[:10])}" if free else ''))
        self.check('free_now', 'pass' if free_enough else 'fail', free_detail)

        dependency = self.job_reasons('dependency')
        limits = self.job_reasons('limit')
        self.check('limits', 'warn' if limits else 'pass',
                   '; '.join(limits) if limits else 'no limit or policy reason reported by LSF')
        if dependency:
            return self.verdict('WAITING', 'Waiting for a job dependency to be satisfied.', details + dependency)
        if limits:
            return self.verdict('WAITING', 'The request fits, but the job is held back by a limit or '
                                           'scheduling policy. It will start once that clears.',
                                details + limits)
        if free_enough:
            pend = self.job.get('PEND_TIME')
            long_wait = str(pend).isdigit() and int(pend) > 600
            summary = ('Enough resources look free right now; the job should start soon.'
                       if not long_wait else
                       'Enough resources look free right now, yet the job has been pending for '
                       f'{fmt_duration(int(pend))}. A scheduling policy (fairshare, guarantees, '
                       'reservations for other jobs) is likely holding it.')
            return self.verdict('READY', summary,
                                details + [f"Free now: {', '.join(r['host'] for r in free[:10])}"],
                                ['If it does not start, send the job ID and this report to the cluster admins.']
                                if long_wait else [])

        busy = {}
        for r in usable:
            for b in r.get('busy', []):
                busy.setdefault(b.split()[0], []).append(r['host'])
        details.append('Currently short of: ' +
                       (', '.join(f'{k} on {len(v)} host(s)' for k, v in busy.items()) or 'host availability'))
        return self.verdict('WAITING', 'The request fits; the job will start when resources are freed on '
                                       'the hosts listed below.', details)

    def never_suggestions(self, names, dim_fails) -> List[str]:
        selectable = [self.hosts[n] for n in names
                      if not self.select_text or self.select.evaluate(self.hosts[n], self.known_resources)]
        sugg = []
        if 'select' in dim_fails and not selectable:
            sugg.append(f'No queue host matches select[{self.select_text}]; relax the -R select expression.')
            return sugg
        pool = selectable or [self.hosts[n] for n in names]
        if 'slots' in dim_fails:
            best = max((h.max_slots or 0) for h in pool)
            sugg.append(f'Request at most {best} slots per host (span[ptile=...] / -n), '
                        'or allow the job to span several hosts.')
        if 'memory' in dim_fails and self.mem_per_slot:
            best = max((h.maxmem_mb or 0) for h in pool)
            per_host = self.per_host or 1
            sugg.append(f'Largest host memory is {fmt_mb(best)}; reduce mem per slot to about '
                        f'{int(best // per_host)} MB or use fewer slots per host.')
        if 'gpu' in dim_fails and self.gpu:
            best = max(len(self.eligible_gpus(h)) for h in pool)
            mig_hosts = [h.name for h in pool if any(g['mig'] for g in h.gpus)]
            if best:
                sugg.append(f'At most {best} suitable GPUs exist on one host; request no more than that.')
            if mig_hosts and not (self.gpu.mig and self.gpu.mig.lower() != 'no'):
                sugg.append(f'{len(mig_hosts)} host(s) only offer MIG GPUs ({", ".join(mig_hosts[:6])}); '
                            'request MIG (e.g. -gpu "num=1:mig=2") to use them.')
        if self.details.get('specified_hosts'):
            sugg.append('The job was restricted with -m; widening the host list may help.')
        sugg.append('Modify the job with bmod, or kill and resubmit it with a smaller request.')
        return sugg


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

COLORS = {'NEVER': '31', 'BLOCKED': '35', 'WAITING': '33', 'READY': '32', 'NOT_PENDING': '36'}


def color(text, code, enabled):
    return f'\033[{code}m{text}\033[0m' if enabled else text


def print_report(result: dict, verbose: bool):
    use_color = sys.stdout.isatty()
    job, req, verdict = result['job'], result['request'], result['verdict']
    pend = (f", pending {fmt_duration(job['pending_seconds'])}"
            if job.get('pending_seconds') and job['status'] in ('PEND', 'PSUSP') else '')
    print(f"Job {job['id']} ({job['user']}) queue={job['queue']} status={job['status']}{pend}")
    if job.get('service_class'):
        print(f"  Service class: {job['service_class']}")
    if job.get('exec_host'):
        print(f"  Running: on {job['exec_host']} since {job.get('start_time') or '?'}"
              f", run time {job.get('run_time') or '?'}")
    if job.get('max_mem') or job.get('avg_mem'):
        print(f"  Used   : max memory {job.get('max_mem') or '-'}, average {job.get('avg_mem') or '-'}")
    print(f"  Request: {req['slots']} slots, {req['layout']}")
    if req.get('mem_per_slot_mb'):
        print(f"  Memory : {fmt_mb(req['mem_per_slot_mb'])} per slot")
    if req.get('gpu'):
        g = req['gpu']
        kind = f"MIG {g['mig']}" if g['mig'] else 'whole (non-MIG)'
        print(f"  GPUs   : {g['num']:g} per {g['per']}, {kind}"
              f"{', model ' + g['gmodel'] if g['gmodel'] else ''}{', exclusive' if g['exclusive'] else ''}")
    if req.get('select'):
        print(f"  Select : {req['select']}")
    if req.get('specified_hosts'):
        print(f"  -m     : {' '.join(req['specified_hosts'])}")
    if 'queue' in result:
        q = result['queue']
        print(f"  Queue  : {q['status']}, {q['hosts']} host(s) from {' '.join(q['host_list'])}")

    code = verdict['code']
    print()
    print(color(f"VERDICT: {code}", COLORS.get(code, '0') + ';1', use_color) + f" - {verdict['summary']}")
    for d in verdict['details']:
        print(f"  - {d}")
    for s in verdict['suggestions']:
        print(f"  > {s}")
    for n in result.get('notes', []):
        print(f"  note: {n}")

    checks = result.get('checks', [])
    if checks:
        print("\n  Checks:")
        status_codes = {'pass': '32', 'fail': '31', 'warn': '33', 'info': '36', 'skip': '2'}
        for c in checks:
            tag = color(f"{c['status'].upper():<4}", status_codes.get(c['status'], '0'), use_color)
            print(f"    [{tag}] {c['label']:<36} {c['detail']}")

    rows = result.get('hosts', [])
    if rows and (verbose or len(rows) <= 40):
        print()
        print(f"  {'HOST':<16}{'STATUS':<13}{'SLOTS':>11}{'MEM':>14}{'GPUS':>12}  STATE")
        order = {'free': 0, 'busy': 1, 'down': 2, 'never': 3}
        for r in sorted(rows, key=lambda r: (order.get(r['state'], 9), r['host'])):
            if 'free_slots' in r:
                slots = f"{r['free_slots']}/{r['max_slots']}"
                mem = f"{fmt_mb(max(r['free_mem_mb'], 0)) if r['free_mem_mb'] is not None else '-'}/{fmt_mb(r['maxmem_mb'])}"
                gpus = f"{r['free_gpus']}/{r['eligible_gpus']}" if req.get('gpu') else f"-/{r['gpus']}"
            else:
                slots, mem = f"-/{r['max_slots']}", f"-/{fmt_mb(r['maxmem_mb'])}"
                gpus = f"{r['eligible_gpus']}/{r['gpus']}" if req.get('gpu') else f"-/{r['gpus']}"
            state = r['state']
            if state == 'never':
                info = '; '.join(r['fails'])
            elif state == 'busy':
                info = '; '.join(r.get('busy') or [r['status']])
            elif state == 'down':
                info = r['status']
            else:
                info = ''
            state_code = {'free': '32', 'busy': '33', 'down': '35', 'never': '31'}[state]
            print(f"  {r['host']:<16}{r['status']:<13}{slots:>11}{mem:>14}{gpus:>12}  "
                  f"{color(state.upper(), state_code, use_color)} {info}")
        print("  (SLOTS/MEM/GPUS = free now / host total; GPUS counts only GPUs that match the request)")
    elif rows:
        print(f"\n  {len(rows)} hosts analysed; use -v to list them.")

    reasons = result.get('reasons', [])
    if reasons:
        print("\n  LSF pending reasons (bjobs -p3):")
        for r in reasons:
            if r['section'] == 'non-candidate' and not verbose:
                continue
            hosts = f" ({r['hosts']} hosts)" if r['hosts'] else ''
            print(f"    [{r['section']}/{r['category']}] {r['reason']}{hosts}")
        if not verbose and any(r['section'] == 'non-candidate' for r in reasons):
            print("    (non-candidate host reasons hidden; use -v)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0].strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__.split('\n\n', 1)[1])
    parser.add_argument('jobid', help='LSF job ID (array element as JOBID[INDEX])')
    parser.add_argument('--json', action='store_true', help='print the analysis as JSON')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='list every host and the non-candidate pending reasons')
    parser.add_argument('--timeout', type=int, default=TIMEOUT,
                        help=f'timeout in seconds of each LSF command (default {TIMEOUT})')
    args = parser.parse_args()

    try:
        result = inspect_job(args.jobid, timeout=args.timeout)
    except SystemExit as e:
        if not args.json:
            raise
        # Errors are raised as SystemExit('ERROR: ...') by the LSF loaders
        error = str(e.code) if e.code is not None else 'unknown error'
        print(json.dumps({'schema': SCHEMA, 'job': {'id': args.jobid},
                          'error': re.sub(r'^ERROR:\s*', '', error)}, indent=2))
        return EXIT_ERROR

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return EXIT_OK

    print_report(result, args.verbose)
    code = result['verdict']['code']
    return {'NEVER': EXIT_NEVER, 'BLOCKED': EXIT_BLOCKED}.get(code, EXIT_OK)


def inspect_job(jobid: str, timeout: Optional[int] = None) -> dict:
    """ Analysis of an LSF job (see the module docstring) as a dict. The queue
    and hosts are only loaded (slow on big clusters) for pending jobs. """
    global TIMEOUT
    if timeout:
        TIMEOUT = timeout
    job = load_job(jobid)
    pending = job.get('STAT') in ('PEND', 'PSUSP')
    details = load_job_details(jobid)
    reasons = load_pending_reasons(jobid) if pending else []
    queue = load_queue(job['QUEUE']) if pending else {'status': 'unknown', 'hosts': [], 'users': []}
    hosts = load_hosts() if pending else {}
    return Analysis(job, details, reasons, queue, hosts).run()


if __name__ == '__main__':
    sys.exit(main())
