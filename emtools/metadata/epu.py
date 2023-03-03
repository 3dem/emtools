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
from datetime import datetime
from glob import glob
import xmltodict

from emtools.utils import Pretty, Path, Color, Process
from .table import Table
from .starfile import StarFile


class EPU:
    @staticmethod
    def get_acquisition(movieXmlFn):
        """ Parse acquisition parameters from EPU's xml movie file. """
        with open(movieXmlFn) as f:
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

        return data

    @staticmethod
    def parse_session(inputDir, outputStar=None, backupFolder=None, lastMovie=None, limit=0, pl=Process):
        """ Parse input files from an EPU session.
        Args:
            inputDir: input path where the session files are.
            outputStar: parse image parameters from the XML and write to this star file
            backupFolder: copy files and folder to this location
            lastMovie: last seen movie, used to avoid parsing if no new changes
            limit: development option to limit the number of parsed files
            pl: ProcessLogger instance, by default use just Process.system
        """
        if not os.path.exists(inputDir):
            raise Exception(f"Input dir '{Color.red(inputDir)}' does not exist.")

        if not os.path.isdir(inputDir):
            raise Exception(f"Input '{Color.red(inputDir)}' must be a path.")

        gsTable = Table(['id', 'folder', 'image', 'xml'])
        fhTable = Table(['id', 'image', 'xml', 'gsId'])
        movies = []

        stats = {'count': 0, 'size': 0}
        to_backup = []
        ed = Path.ExtDict()

        def _rel(fn):
            return os.path.relpath(fn, inputDir)

        def _backup(fn):
            if backupFolder:
                folder, file = os.path.split(fn)
                dstFolder = os.path.join(backupFolder, _rel(folder))
                dstFile = os.path.join(dstFolder, file)
                if not os.path.exists(dstFile):
                    if not os.path.exists(dstFolder):
                        pl.system(f"mkdir -p {dstFolder}")
                    pl.system(f'cp {fn} {dstFolder}')

        def _backup_pair(jpgFn):
            """ Count files and size. """
            for fn in [jpgFn, jpgFn.replace('.jpg', '.xml')]:
                to_backup.append(fn)

        def _get_movies():
            for root, dirs, files in os.walk(inputDir):
                if root.endswith('FoilHoles'):
                    # Register the FoilHoles
                    gsFolder = os.path.dirname(root)
                    gsId = os.path.basename(gsFolder)
                    for f in files:
                        fn = os.path.join(root, f)
                        ed.register(fn)
                        if f.startswith('FoilHole_') and f.endswith('.jpg'):
                            loc = EPU.get_movie_location(f)
                            _backup_pair(fn)
                            fhTable.addRowValues(id=loc['fh'],
                                                 image=f,
                                                 xml=f.replace('.jpg', '.xml'),
                                                 gsId=gsId)
                    files = []  # do not iterate already processed files

                for f in files:
                    fn = os.path.join(root, f)
                    s = os.stat(fn)
                    ed.register(fn, s)
                    if f.startswith('GridSquare_') and f.endswith('.jpg'):
                        _backup_pair(fn)
                        gsTable.addRowValues(id=os.path.basename(root),
                                             folder=_rel(root),
                                             image=f,
                                             xml=f.replace('.jpg', '.xml'))

                    # Check existing movies first
                    if f.startswith('FoilHole_'):
                        if f.endswith('_fractions.tiff'):
                            movies.append({
                                'fn': fn,
                                'stat': s
                            })

        _get_movies()
        if movies:
            movies.sort(key=lambda m: m['stat'].st_mtime)
            first_ts = movies[0]['stat'].st_mtime
            first_creation = datetime.fromtimestamp(first_ts)
            first_movie = os.path.relpath(movies[0]['fn'], inputDir)
            last_ts = movies[-1]['stat'].st_mtime
            last_creation = datetime.fromtimestamp(last_ts)
            last_movie = os.path.relpath(movies[-1]['fn'], inputDir)
            hours = (last_creation - first_creation).seconds / 3600
        else:
            first_movie = last_movie = ''
            first_ts = last_ts = None
            hours = 0

        info = {
            'size': ed.total_size,
            'movies': len(movies),
            'sizeH': Pretty.size(ed.total_size),
            'first_movie': first_movie,
            'first_movie_creation': Pretty.timestamp(first_ts) if first_ts else '',
            'last_movie': last_movie,
            'last_movie_creation': Pretty.timestamp(last_ts) if last_ts else '',
            'duration': f'{hours:0.2f} hours',
            'files': ed
        }

        if limit:
            movies = movies[:limit]

        acq = None

        if outputStar and lastMovie != last_movie:
            for fn in to_backup:
                _backup(fn)

            out = StarFile(outputStar, 'w')
            out.writeTable('GridSquares', gsTable)
            out.writeTable('FoilHoles', fhTable)
            t = Table(['movieBaseName', 'gsId', 'fhId', 'timeStamp', 'beamShiftX', 'beamShiftY'])
            out.writeHeader('Movies', t)

            for i, m in enumerate(movies):
                fn = m['fn']
                loc = EPU.get_movie_location(fn)
                values = {
                    'movieBaseName': _rel(fn),
                    'gsId': loc['gs'], 'fhId': loc['fh'],
                    'beamShiftX': -9999,
                    'beamShiftY': -9999,
                    'timeStamp': m['stat'].st_mtime
                }
                xmlFn = fn.replace('_fractions.tiff', '.xml')
                if os.path.exists(xmlFn):
                    _backup(xmlFn)
                    x, y = EPU.parse_beam_shifts(xmlFn)
                    if acq is None:
                        acq = EPU.get_acquisition(xmlFn)
                        info['acquisition'] = acq

                    values['beamShiftX'] = x
                    values['beamShiftY'] = y
                out.writeRow(t.Row(**values))

            out.close()

        return info

    @staticmethod
    def parse_beam_shifts(xmlFile):
        """ Parse x and y shifts from the provided xml file. """
        with open(xmlFile) as f:
            d = xmltodict.parse(f.read())
            bt = d['MicroscopeImage']['microscopeData']['optics']['BeamShift']
            x, y = bt['a:_x'], bt['a:_y']
            return x, y

    @staticmethod
    def get_beam_shifts(xmlDir):
        """ Parse beam tilts from EPU's xml movie files.
        Args:
            xmlDir: Parse beam shifts from all movies' xml in this dir
        Return:
            Iterator over the parsed files. Each iteratorion will yield:
                MovieBaseName, xshift, yshift
        """
        for root, dirs, files in os.walk(xmlDir):
            for fn in files:
                f = os.path.join(root, fn)
                # Check existing movies first
                if fn.startswith('FoilHole_') and fn.endswith('_fractions.tiff'):
                    xmlFn = f.replace('_fractions.tiff', '.xml')
                    if os.path.exists(xmlFn):
                        x, y = EPU.parse_beam_shifts(xmlFn)
                        yield os.path.basename(fn), x, y

    @staticmethod
    def get_movie_location(movieName):
        loc = {'gs': None, 'fh': None}
        for p in Path.splitall(movieName):
            if p.startswith('GridSquare_'):
                loc['gs'] = p
            elif p.startswith('FoilHole_'):
                parts = p.split('_')
                loc['fh'] = f'{parts[0]}_{parts[1]}'
        return loc

    class Data:
        def __init__(self, epuStar):
            with StarFile(epuStar) as sf:
                self.gsTable = sf.getTable('GridSquares')
                self.fhTable = sf.getTable('FoilHoles')
                self.moviesTable = sf.getTable('Movies')


