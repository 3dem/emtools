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
import unittest
import tempfile
import random
import time
import threading
import tempfile
from pprint import pprint
from datetime import datetime

from emtools.utils import Timer, Color, Pretty
from emtools.metadata import StarFile, SqliteFile, EPU, StarMonitor
from emtools.jobs import BatchManager
from emtools.tests import testpath
from emtools.image import Image

from .star_pipeline_tester import StarPipelineTester


class TestImage(unittest.TestCase):
    """
    Tests for Image class.
    """

    def test_dimensions(self):
        """
        Read a star file with several blocks
        """
        names = ['May08_03.05.02.bin.mrc',
                 'gain.mrc',
                 '20170629_00021_frameImage.tiff']
        dims = [(1240, 1200, 50),
                (3710, 3838),
                (3710, 3838, 24)]
        files = [testpath('movies', n) for n in names]

        if any(f is None for f in files):
            return

        for f, d in zip(files, dims):
            self.assertEqual(Image.get_dimensions(f), d)

