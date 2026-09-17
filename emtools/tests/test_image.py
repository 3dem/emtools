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
import math
from pprint import pprint
from datetime import datetime

import numpy as np

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

    def test_apply_transform(self):
        """
        Image.apply_transform should resample a raw tilt image following
        the same (IMOD-style) raw -> aligned convention used elsewhere in
        emtools for RELION-5 tomography alignments (RelionStar.alignment_to_xf
        / alignment_from_xf): a point at (x, y), relative to the image
        centre, is mapped to (A11*x + A12*y + DX, A21*x + A22*y + DY) in the
        aligned image.
        """
        def alignment_to_xf(z_rot_deg, shift_x_angst, shift_y_angst, pixel_size):
            angle = math.radians(z_rot_deg)
            a11 = float('%.3f' % math.cos(angle))
            a12 = float('%.3f' % math.sin(angle))
            a21 = float('%.3f' % -math.sin(angle))
            a22 = float('%.3f' % math.cos(angle))
            sx = shift_x_angst / pixel_size
            sy = shift_y_angst / pixel_size
            dx = -(a11 * sx + a12 * sy)
            dy = -(a21 * sx + a22 * sy)
            return [a11, a12, a21, a22, dx, dy]

        n = 161
        center = n // 2

        def gaussian_blob(px, py, sigma=1.5):
            yy, xx = np.mgrid[0:n, 0:n]
            d2 = (xx - (center + px)) ** 2 + (yy - (center + py)) ** 2
            return np.exp(-(d2 / (2 * sigma ** 2))).astype(np.float32)

        def centroid(image):
            total = image.sum()
            yy, xx = np.mgrid[0:image.shape[0], 0:image.shape[1]]
            return (image * xx).sum() / total, (image * yy).sum() / total

        rnd = random.Random(123)
        max_err = 0.0
        for _ in range(50):
            z_rot = rnd.uniform(-179, 179)
            shift_x_angst = rnd.uniform(-20, 20)
            shift_y_angst = rnd.uniform(-20, 20)
            pixel_size = rnd.choice([1.0, 1.35, 2.7])
            px = rnd.uniform(-10, 10)
            py = rnd.uniform(-10, 10)

            xf = alignment_to_xf(z_rot, shift_x_angst, shift_y_angst, pixel_size)
            a11, a12, a21, a22, dx, dy = xf
            expected_x = center + (a11 * px + a12 * py + dx)
            expected_y = center + (a21 * px + a22 * py + dy)

            aligned = Image.apply_transform(gaussian_blob(px, py), xf)
            cx, cy = centroid(aligned)
            err = math.hypot(cx - expected_x, cy - expected_y)
            max_err = max(max_err, err)

        self.assertLess(max_err, 0.05)

        # A 6-value XF row and its equivalent 3x3 matrix must be interchangeable.
        xf_row = [1.0, 0.0, 0.0, 1.0, 5.0, -3.0]
        matrix = Image.matrix_from_xf(xf_row)
        self.assertEqual(matrix.shape, (3, 3))
        image = gaussian_blob(0, 0)
        from_row = Image.apply_transform(image, xf_row)
        from_matrix = Image.apply_transform(image, matrix)
        np.testing.assert_allclose(from_row, from_matrix)

    def test_rescale_array(self):
        """
        Image.rescale_array should Fourier-rescale a 2D array, the same
        way Image.fourier_crop does for a file on disk.
        """
        n = 128
        yy, xx = np.mgrid[0:n, 0:n]
        image = np.exp(-(((xx - n // 2) ** 2 + (yy - n // 2) ** 2) / (2 * 8.0 ** 2)))

        half = Image.rescale_array(image, 0.5)
        self.assertEqual(half.shape, (n // 2, n // 2))

        same = Image.rescale_array(image, 1.0)
        np.testing.assert_allclose(same, image)
