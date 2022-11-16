#!/usr/bin/env python
import math
import sys
import os
import json
from collections import OrderedDict
from glob import glob
from pprint import pprint
import argparse

from emtools.utils import Pretty, Color, Path
from datetime import datetime

import xmltodict
from .config import *
from .base import SessionsBase


class SessionsRaw(SessionsBase):
    def __init__(self, **kwargs):
        self.cache_file = 'raw.json'
        self.pattern = kwargs.get('pattern', SESSIONS_RAW_PATTERN)
        SessionsBase.__init__(self, **kwargs)

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

    def get_info(self, raw_folder):
        """ Return some information (group, users, year, scope, etc) from the raw data path. """
        if not raw_folder.startswith(SESSIONS_RAW_FOLDER):
            raise Exception("Invalid root for RAW folder")

        raw_folder = os.path.relpath(raw_folder, SESSIONS_RAW_FOLDER)
        parts = Path.splitall(raw_folder)

        if len(parts) < 7:
            raise Exception("Invalid number of subfolders")

        group = parts[0]
        microscope = parts[1]
        year = parts[2]
        user = parts[5]

        if not group.endswith('grp'):
            raise Exception("Invalid group %s" % group)
        elif microscope not in ['Krios01', 'Arctica01']:
            raise Exception("Invalid microscope %s" % microscope)

        return {
            'group': group,
            'microscope': microscope,
            'year': year,
            'user': user,
            'new_raw_folder': os.path.join(SESSIONS_RAW_FOLDER, os.path.sep.join(parts[:7]))
        }

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
            parts = Path.splitall(folder)
            group_name = [p for p in parts if p.endswith('grp')][0]

            for root, dirs, files in os.walk(folder):
                for name in dirs:
                    if name.startswith('Images-Disc'):
                        sessions[root] = {'group': group_name, 'path': root}
                        dirs[:] = []
                        break
        return sessions

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
        sr = SessionsRaw(verbose=args.verbose)
        if args.list:
            sr.list()
        elif args.session_path:
            path = os.path.join(SESSIONS_RAW_FOLDER, args.session_path)
            if args.use_raw or path not in sr.sessions:
                print(Color.bold(">>> Checking path from raw data"))
                if not os.path.exists(path):
                    raise Exception("Input folder does not exists.")
                s = {'path': path}
                sr.update_session(s)
            else:
                print(Color.bold(">>> Reading session info from cache"))
                s = sr.sessions[path]
            pprint(s)
        else:
            sessions = sr.find_sessions()
            print(f'Total sessions from RAW data: {len(sessions)}')
            print(f'Sessions already parsed: {len(sr.sessions)}')

            new_sessions = [s for s in sessions if s not in sr.sessions]
            if new_sessions:
                print(Color.warn("NEW: "))
                pprint(new_sessions)

            missing_sessions = [s for s in sr.sessions if s not in sessions]
            if missing_sessions:
                print(Color.bold("Missing: "))
                pprint(missing_sessions)

            if args.update:
                sr.update([s for k, s in sessions.items() if k not in sr.sessions])

