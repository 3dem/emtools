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

from doctest import OutputChecker
import io
import numpy as np
import base64
import mrcfile
import tifffile

import PIL
from PIL import Image

from emtools.utils import Path, Pretty


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
            pil_img = PIL.ImageOps.autocontrast(pil_img, cutoff=self.contrast_factor)

        if self.gaussian_radius is not None:
            pil_img = pil_img.filter(PIL.ImageFilter.GaussianBlur(radius=self.gaussian_radius))

        return self.__format(pil_img)

    def from_path(self, path):
        """ Read the image path as a PIL image and encode it as base64.
        """
        try:
            img = PIL.Image.open(path)
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

        pil_img = PIL.Image.fromarray(im255)

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
        """ Shortcut method with presets for Micrograph thumbnail.
        All settings can be overwritten with kwargs.
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
        """ Shortcut method with presets for PSD thumbnails.
        All settings can be overwritten with kwargs.
        """
        defaults = {
            'output_format': 'base64',
            'max_size': (128, 128),
            'contrast_factor': 1
        }
        defaults.update(kwargs)
        return Thumbnail(**defaults)

    @staticmethod
    def Preview(imagePath, **kwargs):
        imageLower = imagePath.lower()
        thumb = Thumbnail.Micrograph(max_size=(256, 256))

        if not (Path.isImage(imagePath) or Path.isEmImage(imagePath)):
            raise Exception("Can not generate preview for: %s" % imagePath)

        if Path.isImage(imagePath):
            return thumb.from_path(imagePath)

        if imageLower.endswith('.mrc'):
            dims = Image.get_dimensions(imagePath)
            mrc = mrcfile.open(imagePath, permissive=True)
            thumb = Thumbnail.Micrograph()
            if len(dims) == 2:
                array = mrc.data 
            elif len(dims) == 3:
                x, y, z = dims
                if mrc.is_volume() or (x == y and y == z):
                    thumb = Thumbnail(max_size=(256, 256), output_format='base64')
                    iMax = mrc.data.max()  # min(imean + 10 * isd, imageArray.max())
                    iMin = mrc.data.min()  # max(imean - 10 * isd, imageArray.min())
                    im255 = ((mrc.data - iMin) / (iMax - iMin) * 255).astype(np.uint8)

                    # 1. Setup
                    ximg = PIL.Image.fromarray(im255[:, :, x // 2])
                    yimg = PIL.Image.fromarray(im255[:, y // 2, :])
                    zimg = PIL.Image.fromarray(im255[z // 2, :, :])

                    xw, xh = ximg.size
                    yw, yh = yimg.size
                    zw, zh = zimg.size

                    pad = 2  # The thickness of the dark gray lines/borders

                    # 2. Calculate canvas size for a full grid with outer borders
                    # Total Width = (2 * image width) + (3 * padding for left, middle, right)
                    canvas_w = (xw + yw) + (3 * pad)
                    canvas_h = (xh + zh) + (3 * pad)

                    # Create canvas with a white background (matching your image)
                    bg_color = (256, 256, 256) 
                    montage = PIL.Image.new('RGB', (canvas_w, canvas_h), bg_color)

                    # Top-Left: x slice
                    montage.paste(ximg, (pad, pad))                    
                    # Bottom-Left: z slice
                    montage.paste(zimg, (pad, xh + 2 * pad))
                    # Bottom-Right: y slice
                    montage.paste(yimg, (xw + 2 * pad, xh + 2 * pad))

                    return thumb.from_pil(montage)
                    Pretty.dprint("Loading MRC volume: %s" % str(array.shape))
                else:
                    array = mrc.data[z//2, :, :] # FIXME
                    Pretty.dprint("Loading MRC 2D: %s" % str(array.shape))
                return thumb.from_array(array)
            else:
                raise Exception("Invalid dimensions: %s" % dims)


class Image:
    @staticmethod
    def get_dimensions(imagePath):
        imageLower = imagePath.lower()
        if imageLower.endswith('.mrc') or imageLower.endswith('.mrcs'):
            with mrcfile.open(imagePath) as mrc:
                return mrc.data.shape[::-1]  # in reverse order
        elif (imageLower.endswith('.tif') or
              imageLower.endswith('.tiff') or
              imageLower.endswith('.eer') or
              imageLower.endswith('.gain')):
            with tifffile.TiffFile(imagePath) as tif:
                n = len(tif.pages)
                y, x = tif.pages[0].shape
                return (x, y, n) if n > 1 else (x, y)
