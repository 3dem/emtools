#!/usr/bin/env python
import math
import sys
import os
import json
from collections import OrderedDict
from glob import glob
from pprint import pprint
import argparse

from emtools.utils import Pretty, Color
from datetime import datetime

import xmltodict
from .config import *


class SessionsRaw:
    def __init__(self, pattern=None, cache_folder=None, verbose=False):
        self.pattern = pattern or SESSIONS_RAW_PATTERN
        self.cache_folder = cache_folder or SESSIONS_CACHE_FOLDER
        self.sessions_json_file = os.path.join(self.cache_folder, 'list.json')
        self.sessions = OrderedDict()
        self.verbose = verbose
        self.load()

    def print(self, *args):
        if self.verbose:
            print(*args)

    def load(self):
        """ Load sessions. """
        self.sessions = OrderedDict()
        with open(self.sessions_json_file) as f:
            for s in json.load(f):
                self.sessions[s['path']] = s

    def save(self):
        with open(self.sessions_json_file, 'w') as f:
            json.dump([s for s in self.sessions.values()], f)

    def get_acquisition(self, fn):
        with open(fn) as f:
            xmljson = xmltodict.parse(f.read())

        pixelSize = xmljson['MicroscopeImage']['SpatialScale'].get('pixelSize', None)
        data = xmljson['MicroscopeImage']['microscopeData']
        instrument = data['instrument']
        camera = data['acquisition']['camera']

        def _pixelSize(k):
            if not pixelSize:
                return ''
            ps = float(pixelSize[k]['numericValue']) * (10**10)
            return f'{ps:0.5f}'

        data = {
            'pixelSize': {'x': _pixelSize('x'), 'y': _pixelSize('y')},
            'voltage': data['gun']['AccelerationVoltage'],
            'instrument': {'id': instrument['InstrumentID'],
                           'model': instrument['InstrumentModel']},
            'magnification': data['optics']['TemMagnification']['NominalMagnification'],
            'camera': {
                'Binning': {'x': camera['Binning']['a:x'],
                            'y': camera['Binning']['a:y']},
                'DarkGainCorrection': camera['DarkGainCorrection'],
                'ExposureTime': camera['ExposureTime'],
                'ReadoutArea': {'height': camera['ReadoutArea']['a:height'],
                                'width': camera['ReadoutArea']['a:width']}
           }
        }

        new_fn = fn.replace(os.path.sep, '___')
        os.system(f'cp {fn} {self.cache_folder}/xml/{new_fn}')
        return data

    def update_session(self, session):
        """ Check for metadata and images under the session's path and update the info.
        """
        path = session['path']
        self.print(Color.bold(f"\nInspecting session: {path}"))

        images_pattern = 'Images-Disc*/GridSquare_*/Data/FoilHole_*_fractions.tiff'
        files = glob(os.path.join(path, images_pattern))

        if not files:
            return

        def _xml(t):
            xmlfn = t[0].replace('_fractions.tiff', '.xml')
            return xmlfn if os.path.exists(xmlfn) else None

        f0 = files[0]
        s0 = os.stat(f0)
        size = s0.st_size
        first = (f0, s0.st_mtime)
        last = (f0, s0.st_mtime)
        xml = _xml(first)

        for f in files[1:]:
            s = os.stat(f)
            size += s.st_size
            t = (f, s.st_mtime)
            if s.st_mtime < first[1]:
                first = t
            if s.st_mtime > last[1]:
                last = t
            if not xml:
                xml = _xml(t)

        first_creation = datetime.fromtimestamp(first[1])
        last_creation = datetime.fromtimestamp(last[1])
        hours = (last_creation - first_creation).seconds / 3600
        session.update({
            'size': size,
            'movies': len(files),
            'sizeH': Pretty.size(size),
            'first_movie': os.path.relpath(first[0], path),
            'first_movie_creation': Pretty.timestamp(first[1]),
            'last_movie': os.path.relpath(last[0], path),
            'last_movie_creation': Pretty.timestamp(last[1]),
            'duration': f'{hours:0.2f} hours'
        })

        if xml:
            self.print(f'>>> Parsing xml: {xml}')
            session['acquisition'] = self.get_acquisition(xml)
        else:
            self.print(f'>>> Not found XML file')

    def find_sessions(self):
        """ Discover all sessions under a given data folder. """
        folders = glob(self.pattern)
        sessions = OrderedDict()

        for folder in folders:
            self.print(Color.warn(f"\n\n>>> Searching in Group folder: {folder}"))
            parts = os.path.normpath(folder).split(os.path.sep)
            group_name = [p for p in parts if p.endswith('grp')][0]

            for root, dirs, files in os.walk(folder):
                for name in dirs:
                    if name.startswith('Images-Disc'):
                        sessions[root] = {'group': group_name, 'path': root}
                        dirs[:] = []
                        break
        return sessions

    def update(self, new_sessions):
        for s in new_sessions:
            self.update_session(s)
            self.sessions[s['path']] = s
        self.save()

    def list(self):
        format_str = u'{start:10} {size:>13}{movies:>7}  {acq}  {path:<}'

        sessions = []
        for s in self.sessions.values():
            size = int(s.get('size', 0))

            if size:
                if 'acquisition' in s:
                    acq = s['acquisition']
                    voltage = float(acq['voltage']) / 1000
                    pixelSize = float(acq['pixelSize']['x'])
                    h = acq['camera']['ReadoutArea']['height']
                    w = acq['camera']['ReadoutArea']['width']
                    bin = acq['camera']['Binning']['x']
                    acqstr = f"{voltage} kV  {pixelSize:0.3f} A/px  {h} x {w} (bin {bin})"
                else:
                    acqstr = f"MISSING ACQUISITION"
                session = {
                    'path': os.path.relpath(s['path'], SESSIONS_RAW_FOLDER),
                    'group': s['group'],
                    'start': s['first_movie_creation'].split()[0],
                    'end': s['last_movie_creation'],
                    'size': s['sizeH'],
                    'movies': s['movies'],
                    'root': s['path'] if 'acquisition' not in s else '',
                    'acq': acqstr,
                    'last': os.path.join(s['path'], s['last_movie'])
                }
                sessions.append(session)

        sessions.sort(key=lambda s: s['start'])

        for s in sessions:
            print(format_str.format(**s))

        print(f"Total {len(sessions)}")


class Main:
    @staticmethod
    def add_arguments(parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('session_path', nargs='?',
                           help="Optional session path to inspect")
        group.add_argument('--list', '-l', action='store_true',
                           help="List all raw sessions stored in the "
                                "cache file. ")
        group.add_argument('--update', '-u', action='store_true',
                           help="Update the cache with new sessions found"
                                "in the root folder. ")
        parser.add_argument('--use_raw', '-i', action="store_true",
                            help="For session inspection to use raw folder"
                                 "and not take into account the cache. ")

    @staticmethod
    def run(args):
        sm = SessionsRaw(verbose=args.verbose)
        if args.list:
            sm.list()
        elif args.session_path:
            path = os.path.join(SESSIONS_RAW_FOLDER, args.session_path)
            if args.use_raw or path not in sm.sessions:
                print(Color.bold(">>> Checking path from raw data"))
                if not os.path.exists(path):
                    raise Exception("Input folder does not exists.")
                s = {'path': path}
                sm.update_session(s)
            else:
                print(Color.bold(">>> Reading session info from cache"))
                s = sm.sessions[path]
            pprint(s)
        else:
            sessions = sm.find_sessions()
            print(f'Total sessions from RAW data: {len(sessions)}')
            print(f'Sessions already parsed: {len(sm.sessions)}')

            new_sessions = [s for s in sessions if s not in sm.sessions]
            if new_sessions:
                print(Color.warn("NEW: "))
                pprint(new_sessions)

            missing_sessions = [s for s in sm.sessions if s not in sessions]
            if missing_sessions:
                print(Color.bold("Missing: "))
                pprint(missing_sessions)

            if args.update:
                sm.update([s for k, s in sessions.items() if k not in sm.sessions])

