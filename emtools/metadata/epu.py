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
    def parse_session(inputDir, outputStar=None, backupFolder=None, doBackup=False, lastMovie=None, limit=0, pl=Process):
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

        movies = []

        stats = {'count': 0, 'size': 0}
        to_backup = []
        ed = Path.ExtDict()

        def _rel(fn):
            return os.path.relpath(fn, inputDir)

        def _backup(fn):
            if backupFolder and doBackup:
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
                for f in files:
                    fn = os.path.join(root, f)
                    s = os.stat(fn)
                    ed.register(fn, s)
                    if f.startswith('GridSquare_') and f.endswith('.jpg'):
                        _backup_pair(fn)
                    # Check existing movies first
                    if f.startswith('FoilHole_'):
                        if f.endswith('_fractions.tiff'):
                            movies.append((fn, s))
                        elif f.endswith('.xml'):
                            _backup(fn)

        _get_movies()
        movies.sort(key=lambda m: m[1].st_mtime)

        info = {
            'size': ed.total_size,
            'sizeH': Pretty.size(ed.total_size),
            'files': ed
        }

        if limit:
            movies = movies[:limit]

        last_movie = movies[-1][0]
        if outputStar and lastMovie != last_movie:
            for fn in to_backup:
                _backup(fn)
            if os.path.exists(outputStar):
                os.remove(outputStar)
            data = EPU.Data(inputDir, inputDir, epuStar=outputStar)
            for i, m in enumerate(movies):
                movieFn, movieStat = m
                data.addMovie(_rel(movieFn), movieStat)
            data.write()

            info.update(data.info())
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
        # FIXME Hack to handle Scipion change of ../Data/FoilHole.. to Data_FoilHole
        if '_Data_FoilHole_' in movieName:
            parts = os.path.basename(movieName).split('_Data_')
        else:
            parts = Path.splitall(movieName)
        for p in parts:
            if p.startswith('GridSquare_'):
                loc['gs'] = p
            elif p.startswith('FoilHole_'):
                parts = p.split('_')
                loc['fh'] = f'{parts[0]}_{parts[1]}'
        return loc

    class Data:
        def __init__(self, dataFolder, epuFolder, epuStar=None):
            self._acq = None
            self._dataFolder = dataFolder
            self._epuFolder = epuFolder
            self._epuStar = epuStar or os.path.join(self._epuFolder, 'movies.star')

            if os.path.exists(self._epuStar):
                with StarFile(self._epuStar) as sf:
                    self.gsTable = sf.getTable('GridSquares')
                    self.moviesTable = sf.getTable('Movies')
            else:
                self.gsTable = Table(['id', 'folder', 'image', 'xml'])
                self.moviesTable = Table(['movieBaseName', 'gsId', 'fhId',
                                          'timeStamp', 'beamShiftX',
                                          'beamShiftY'])
            self.gsDict = {row.id: row for row in self.gsTable}

        def write(self):
            with StarFile(self._epuStar, 'w') as sf:
                sf.writeTable('GridSquares', self.gsTable)
                sf.writeTable('Movies', self.moviesTable)

        def addMovie(self, movieFn, movieStat):
            """ Add this movie and try to parse its corresponding XML file.
            NOTE 1: movieFn should be relative path from the EPU folder
            NOTE 2: movies should be added in ascending order regarding
                modification time.
            """
            loc = EPU.get_movie_location(movieFn)
            gridSquare = loc['gs']

            if gridSquare not in self.gsDict:
                gsFolder = os.path.join('Images-Disc1', gridSquare)
                values = {'id': gridSquare,
                          'folder': gsFolder,
                          'image': 'None',
                          'xml': 'None'}
                for fn in os.listdir(os.path.join(self._epuFolder, gsFolder)):
                    if fn.startswith('GridSquare'):
                        if fn.endswith('.jpg'):
                            values['image'] = fn
                        elif fn.endswith('.xml'):
                            values['xml'] = fn
                self.gsDict[gridSquare] = self.gsTable.addRowValues(**values)

            mtime = movieStat.st_mtime

            values = {
                'movieBaseName': movieFn,
                'gsId': gridSquare, 'fhId': loc['fh'],
                'beamShiftX': -9999.0,
                'beamShiftY': -9999.0,
                'timeStamp': mtime
            }
            xmlFn = movieFn.replace('_fractions.tiff', '.xml')
            if os.path.exists(xmlFn):
                x, y = EPU.parse_beam_shifts(xmlFn)
                if self._acq is None:
                    acq = EPU.get_acquisition(xmlFn)
                values['beamShiftX'] = x
                values['beamShiftY'] = y

            self.moviesTable.addRowValues(**values)

        def info(self):
            """ Return a dict with some info """

            if len(self.moviesTable) == 0:
                return {}

            def _rowInfo(row):
                dt = datetime.fromtimestamp(row.timeStamp)
                return row.timeStamp, dt, row.movieBaseName

            firstTs, firstCreation, firstMovie = _rowInfo(self.moviesTable[0])
            lastTs, lastCreation, lastMovie = _rowInfo(self.moviesTable[-1])
            hours = (lastCreation - firstCreation).seconds / 3600

            return {
                'movies': len(self.moviesTable),
                'first_movie': firstMovie,
                'first_movie_creation': firstTs,
                'last_movie': lastMovie,
                'last_movie_creation': lastTs,
                'duration': f'{hours:0.2f} hours',
            }