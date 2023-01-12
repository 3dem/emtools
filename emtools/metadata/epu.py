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

from emtools.utils import Pretty, Path


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
    def get_session_info(sessionPath):
        """ Check for metadata and images under the session's path and return
        updated info.
        """
        movies_count = size = 0
        first = last = xml = None
        acq = {}
        ed = Path.ExtDict()

        for root, dirs, files in os.walk(sessionPath):
            for fn in files:
                f = os.path.join(root, fn)
                s = os.stat(f)
                ed.register(f, s)
                size += s.st_size
                t = (f, s.st_mtime)
                if fn.startswith('FoilHole_') and fn.endswith('_fractions.tiff'):
                    movies_count += 1
                    first = t if not first or s.st_mtime < first[1] else first
                    last = t if not last or s.st_mtime > last[1] else last
                    if not acq:
                        xmlFn = f.replace('_fractions.tiff', '.xml')
                        if os.path.exists(xmlFn):
                            acq = EPU.get_acquisition(xmlFn)

        first_creation = datetime.fromtimestamp(first[1])
        last_creation = datetime.fromtimestamp(last[1])
        hours = (last_creation - first_creation).seconds / 3600
        return {
            'size': size,
            'movies': movies_count,
            'sizeH': Pretty.size(size),
            'first_movie': os.path.relpath(first[0], sessionPath),
            'first_movie_creation': Pretty.timestamp(first[1]),
            'last_movie': os.path.relpath(last[0], sessionPath),
            'last_movie_creation': Pretty.timestamp(last[1]),
            'duration': f'{hours:0.2f} hours',
            'acquisition': acq,
            'files': ed
        }
