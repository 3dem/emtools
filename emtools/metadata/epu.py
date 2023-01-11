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

from emtools.utils import Pretty


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
        images_pattern = 'Images-Disc*/GridSquare_*/Data/FoilHole_*_fractions.tiff'
        files = glob(os.path.join(sessionPath, images_pattern))

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
        session = {
            'size': size,
            'movies': len(files),
            'sizeH': Pretty.size(size),
            'first_movie': os.path.relpath(first[0], sessionPath),
            'first_movie_creation': Pretty.timestamp(first[1]),
            'last_movie': os.path.relpath(last[0], sessionPath),
            'last_movie_creation': Pretty.timestamp(last[1]),
            'duration': f'{hours:0.2f} hours'
        }

        if xml:
            session['acquisition'] = EPU.get_acquisition(xml)

        return session