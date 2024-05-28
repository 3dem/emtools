# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [1]
# *
# * [1] SciLifeLab, Stockholm University
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
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'delarosatrevin@scilifelab.se'
# *
# **************************************************************************

import io
import numpy as np
import base64
import mrcfile

from PIL import Image, ImageOps, ImageFilter


class Thumbnail:
    """ Create image thumbnails from different input types.
    Possible inputs:
        - PIL images
        - numpy arrays
        - MRC files
        - Other file formats that can be read with PIL
    """
    def __init__(self, **kwargs):
        self.max_size = kwargs.get('max_size', (512, 512))
        self.contrast_factor = kwargs.get('contrast_factor', None)
        self.gaussian_radius = kwargs.get('gaussian_radius', None)
        self.scale = 1.0
        self.output_format = kwargs.get('output_format', None)
        self.min_max = kwargs.get('min_max', None)
        self.std_threshold = kwargs.get('std_threshold', 0)


    def __format(self, pil_img):
        format = self.output_format

        if format:
            format_func = getattr(self, '_format_%s' % format, None)
            if format_func is None:
                raise Exception('Invalid output format: %s' % format)
            return format_func(pil_img)

        return pil_img

    def _format_base64(self, pil_img):
        img_io = io.BytesIO()
        pil_img.save(img_io, format='PNG')

        return base64.b64encode(img_io.getvalue()).decode("utf-8")

    def from_pil(self, pil_img):
        """ Convert a PIL image into Base64. """
        scale = 1.0
        w1, _ = pil_img.size
        if self.max_size is not None:
            pil_img.thumbnail(self.max_size)
            w2, _ = pil_img.size
            scale = w1 / w2

        self.scale = scale

        if self.contrast_factor is not None:
            pil_img = ImageOps.autocontrast(pil_img, cutoff=self.contrast_factor)

        if self.gaussian_radius is not None:
            pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=self.gaussian_radius))

        return self.__format(pil_img)

    def from_path(self, path):
        """ Read the image path as a PIL image and encode it as base64.
        """
        try:
            img = Image.open(path)
            encoded = self.from_pil(img)
            img.close()
        except:
            encoded = ''

        return encoded

    def from_array(self, imageArray):

        if self.min_max:
            iMin, iMax = self.min_max
            array = imageArray
        else:
            if self.std_threshold > 0:
                array = np.array(imageArray)
                imean = array.mean()
                isd = array.std()
                isdTh = self.std_threshold * isd
                minTh = imean - isdTh
                maxTh = imean + isdTh
                array[array < minTh] = minTh
                array[array > maxTh] = maxTh
            else:
                array = imageArray

            iMax = array.max()
            iMin = array.min()

        im255 = ((array - iMin) / (iMax - iMin) * 255).astype(np.uint8)

        pil_img = Image.fromarray(im255)

        return self.from_pil(pil_img)

    def from_mrc(self, mrc_path):
        """ Convert real float32 mrc to base64.
        Convert to int8 first, then scale with Pillow.
        """
        mrc_img = mrcfile.open(mrc_path, permissive=True)

        if mrc_img.is_volume():
            imfloat = mrc_img.data[0, :, :]
        else:
            imfloat = mrc_img.data

        result = self.from_array(imfloat)
        mrc_img.close()

        return result

    @staticmethod
    def Micrograph(**kwargs):
        """ Shortcut method with presets for Micrograph thumbail.
        All settings can be overwriten with kwargs.
        """
        defaults = {
            'output_format': 'base64',
            'max_size': (512, 512),
            'contrast_factor': 0.15,
            'std_threshold': 1
        }
        defaults.update(kwargs)
        return Thumbnail(**defaults)

    @staticmethod
    def Psd(**kwargs):
        """ Shortcut method with presets for PSD thumbails.
        All settings can be overwriten with kwargs.
        """
        defaults = {
            'output_format': 'base64',
            'max_size': (128, 128),
            'contrast_factor': 1
        }
        defaults.update(kwargs)
        return Thumbnail(**defaults)

