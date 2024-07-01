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
from datetime import datetime, timedelta
import xmltodict

from emtools.utils import Pretty, Path, Color, Process
from .table import Table
from .starfile import StarFile
from .misc import MovieFiles


class EPU:
    MOVIES_SUFFICES = ['_fractions.tiff', '_EER.eer']
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
            Iterator over the parsed files. Each iteration will yield:
                MovieBaseName, xshift, yshift
        """
        missing_xml = []
        for root, dirs, files in os.walk(xmlDir):
            for fn in files:
                # Check existing movies first
                if xmlFn := EPU.get_movie_xml(fn):
                    xmlPath = os.path.join(root, xmlFn)
                    if os.path.exists(xmlPath):
                        x, y = EPU.parse_beam_shifts(xmlPath)
                        yield fn, x, y
                    else:
                        missing_xml.append(xmlPath)

        if missing_xml:
            print('Missing XML files for the following movies:')
            for f in missing_xml:
                print('\t- ', f)

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
            elif p.startswith('Images-Disc1_GridSquare_'):
                loc['gs'] = p.replace('Images-Disc1_', '')
            elif p.startswith('FoilHole_'):
                parts = p.split('_')
                loc['fh'] = f'{parts[0]}_{parts[1]}'

        return loc

    @staticmethod
    def is_movie_fn(fn):
        return (fn.startswith('FoilHole_') and
                any(fn.endswith(s) for s in EPU.MOVIES_SUFFICES))

    @staticmethod
    def get_movie_xml(fn):
        if EPU.is_movie_fn(fn):
            for s in EPU.MOVIES_SUFFICES:
                if fn.endswith(s):
                    return fn.replace(s, '.xml')
        return ''

    class Data:
        """ Class to keep track of EPU files and associated metadata.
        The information can be read/write from/to a STAR file.
        """
        def __init__(self, rootFolder, epuStar):
            self._acq = None
            self._rootFolder = rootFolder
            self._epuStar = epuStar

            # If the file already exist, read from disk
            if os.path.exists(self._epuStar):
                with StarFile(self._epuStar) as sf:
                    self.gsTable = sf.getTable('GridSquares')
                    self.moviesTable = sf.getTable('Movies')
            else:  # if not, create the empty tables
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
                gsPath = os.path.join(self._rootFolder, gsFolder)
                if os.path.exists(gsPath):
                    for fn in os.listdir(gsPath):
                        if fn.startswith('GridSquare'):
                            if fn.endswith('.jpg'):
                                values['image'] = fn
                            elif fn.endswith('.xml'):
                                values['xml'] = fn
                else:
                    print(f"Missing folder: {gsPath}")
                self.gsDict[gridSquare] = self.gsTable.addRowValues(**values)

            mtime = movieStat.st_mtime

            values = {
                'movieBaseName': movieFn,
                'gsId': gridSquare, 'fhId': loc['fh'],
                'beamShiftX': -9999.0,
                'beamShiftY': -9999.0,
                'timeStamp': mtime
            }
            xmlFn = EPU.get_movie_xml(movieFn)
            if os.path.exists(xmlFn):
                x, y = EPU.parse_beam_shifts(xmlFn)
                if self._acq is None:
                    self._acq = EPU.get_acquisition(xmlFn)
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

    class Session:
        """
        Monitor EPU session files and allow to make a copy of GridSquares
        images and xml files.
        """
        def __init__(self, inputDir, outputStar=None, backupFolder=None, pl=None):
            """
            Create a new EPU.Session instance.

            Args:
                inputDir: input path where the session files are.
                outputStar: If not None, parse image parameters from the XML and write to this star file
                backupFolder: If not None, copy some jpg and xml files to this location
                pl: ProcessLogger instance, by default use just a default logger to stdout
            """
            self.inputDir = inputDir
            self.outputStar = outputStar
            self.backupFolder = backupFolder
            self.pl = pl or Process.Logger()

            if not os.path.exists(inputDir):
                raise Exception(f"Input dir '{Color.red(inputDir)}' does not exist.")

            if not os.path.isdir(inputDir):
                raise Exception(f"Input '{Color.red(inputDir)}' must be a path.")

            if backupFolder and not os.path.exists(backupFolder):
                self.pl.mkdir(backupFolder)

            self.df = MovieFiles(root=inputDir)
            self.all_movies = []

        def scan(self):
            """ Scan new files from the EPU session. """
            df = self.df
            movies = []
            now = datetime.now()
            td = timedelta(minutes=1)

            def _rel(fn):
                return os.path.relpath(fn, self.inputDir)

            def _backup(fn):
                if self.backupFolder:
                    folder, file = os.path.split(fn)
                    dstFolder = os.path.join(self.backupFolder, _rel(folder))
                    dstFile = os.path.join(dstFolder, file)

                    if not os.path.exists(dstFile):
                        self.pl.logger.info(f"Missing file: {dstFile}")
                        if not os.path.exists(dstFolder):
                            self.pl.mkdir(dstFolder)
                        self.pl.cp(fn, dstFile)

            def _backup_pair(jpgFn):
                """ Count files and size. """
                for fn in [jpgFn, jpgFn.replace('.jpg', '.xml')]:
                    _backup(fn)

            for root, dirs, files in os.walk(self.inputDir):
                for f in files:
                    fn = os.path.join(root, f)
                    try:
                        s = os.stat(fn)
                    except FileNotFoundError:
                        continue  # just ignore temporary files
                    dt = datetime.fromtimestamp(s.st_mtime)
                    if now - dt >= td and fn not in df:
                        df.register(fn, s)
                        if f.startswith('GridSquare_') and f.endswith('.jpg'):
                            _backup_pair(fn)
                        # Check existing movies first
                        if f.startswith('FoilHole_'):
                            if EPU.is_movie_fn(f):
                                movies.append((fn, s))
                            elif f.endswith('.xml'):
                                _backup(fn)

            movies.sort(key=lambda m: m[1].st_mtime)

            if self.outputStar and movies:
                # Write first to a temporary file and then overwrite
                tmpStar = self.outputStar + '-tmp.star'
                print(f"Writing star {tmpStar} -> {self.outputStar}, "
                      f"movies: {len(movies)}, total: {len(self.all_movies)}")
                self.pl.rm(tmpStar)
                data = EPU.Data(self.inputDir, tmpStar)
                self.all_movies.extend(movies)
                for i, m in enumerate(self.all_movies):
                    movieFn, movieStat = m
                    data.addMovie(_rel(movieFn), movieStat)
                data.write()
                self.pl.mv(tmpStar, self.outputStar)

        def info(self):
            return self.df.info()
