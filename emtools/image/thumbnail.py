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
from PIL import ImageFilter, ImageOps

from emtools.datatypes import STACK_2D, VOLUME

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
            pil_img = ImageOps.autocontrast(pil_img, cutoff=self.contrast_factor)

        if self.gaussian_radius is not None:
            pil_img = pil_img.filter(
                ImageFilter.GaussianBlur(radius=self.gaussian_radius))

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
                array = np.asarray(imageArray, dtype=np.float64)
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
    def _preview_stack_indices(n):
        """Return 4 frame indices: first, two equally spaced, last."""
        if n <= 1:
            return [0, 0, 0, 0]
        if n == 2:
            return [0, 0, 1, 1]
        if n == 3:
            return [0, 1, 1, 2]
        return [
            0,
            int(round((n - 1) / 3)),
            int(round(2 * (n - 1) / 3)),
            n - 1,
        ]

    @staticmethod
    def _array_to_uint8(array):
        i_min = array.min()
        i_max = array.max()
        if i_max == i_min:
            return np.zeros(array.shape, dtype=np.uint8)
        return ((array - i_min) / (i_max - i_min) * 255).astype(np.uint8)

    @staticmethod
    def _montage_grid(pil_images, cols, pad=2, bg_color=(255, 255, 255)):
        w, h = pil_images[0].size
        rows = (len(pil_images) + cols - 1) // cols
        canvas_w = cols * w + (cols + 1) * pad
        canvas_h = rows * h + (rows + 1) * pad
        montage = PIL.Image.new('RGB', (canvas_w, canvas_h), bg_color)

        for i, img in enumerate(pil_images):
            row, col = divmod(i, cols)
            x = pad + col * (w + pad)
            y = pad + row * (h + pad)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            montage.paste(img, (x, y))

        return montage

    @staticmethod
    def _volume_slice_montage(data):
        im255 = Thumbnail._array_to_uint8(data)
        _, y, x = im255.shape
        z = im255.shape[0]

        ximg = PIL.Image.fromarray(im255[:, :, x // 2])
        yimg = PIL.Image.fromarray(im255[:, y // 2, :])
        zimg = PIL.Image.fromarray(im255[z // 2, :, :])

        xw, xh = ximg.size
        yw, yh = yimg.size
        pad = 2
        canvas_w = (xw + yw) + (3 * pad)
        canvas_h = (xh + yh) + (3 * pad)
        montage = PIL.Image.new('RGB', (canvas_w, canvas_h), (255, 255, 255))

        montage.paste(ximg.convert('RGB'), (pad, pad))
        montage.paste(zimg.convert('RGB'), (pad, xh + 2 * pad))
        montage.paste(yimg.convert('RGB'), (xw + 2 * pad, xh + 2 * pad))

        return montage

    @staticmethod
    def _stack_frame_montage(data):
        n = data.shape[0]
        im255 = Thumbnail._array_to_uint8(data)
        indices = Thumbnail._preview_stack_indices(n)
        images = [PIL.Image.fromarray(im255[i, :, :]) for i in indices]
        return Thumbnail._montage_grid(images, cols=2)

    @staticmethod
    def _mrc_is_stack(mrc, image_lower):
        if image_lower.endswith('.mrcs'):
            return True
        if len(mrc.data.shape) < 3:
            return False
        if mrc.is_volume():
            return False
        if mrc.is_image_stack():
            return True
        return True

    @staticmethod
    def Preview(imagePath, **kwargs):
        imageLower = imagePath.lower()
        thumb = Thumbnail.Micrograph(max_size=(256, 256))

        if not (Path.isImage(imagePath) or Path.isEmImage(imagePath)):
            raise Exception("Can not generate preview for: %s" % imagePath)

        if Path.isImage(imagePath):
            return thumb.from_path(imagePath)

        if imageLower.endswith('.mrc') or imageLower.endswith('.mrcs'):
            with mrcfile.open(imagePath, permissive=True) as mrc:
                data = mrc.data
                if len(data.shape) == 2:
                    return thumb.from_array(data)

                if len(data.shape) != 3:
                    raise Exception("Invalid dimensions: %s" % (data.shape,))

                preview_thumb = Thumbnail(
                    max_size=(256, 256), output_format='base64')

                if Thumbnail._mrc_is_stack(mrc, imageLower):
                    montage = Thumbnail._stack_frame_montage(data)
                else:
                    montage = Thumbnail._volume_slice_montage(data)

                return preview_thumb.from_pil(montage)

        raise Exception("Can not generate preview for: %s" % imagePath)


class Image:
    @staticmethod
    def _mrc_data_type(mrc, image_lower):
        if image_lower.endswith('.mrcs'):
            return STACK_2D
        if mrc.is_volume():
            return VOLUME
        if mrc.is_image_stack():
            return STACK_2D
        return None

    @staticmethod
    def get_metadata(imagePath):
        """Return structured metadata for EM image files, or None."""
        imageLower = imagePath.lower()
        if imageLower.endswith('.mrc') or imageLower.endswith('.mrcs'):
            with mrcfile.open(imagePath) as mrc:
                dims = mrc.data.shape[::-1]
                if len(dims) == 2:
                    x, y = dims
                    return {
                        'info': f'{x} x {y}',
                    }
                if len(dims) == 3:
                    x, y, third = dims
                    is_cube = x == y == third
                    data_type = VOLUME if is_cube else Image._mrc_data_type(mrc, imageLower)
                    if data_type == VOLUME:
                        return {
                            'dataType': data_type,
                            'info': f'{x} x {y} x {third}',
                        }
                    return {
                        'dataType': STACK_2D,
                        'info': f'{x} x {y} x {third}',
                    }
            return None

        if (imageLower.endswith('.tif') or
                imageLower.endswith('.tiff') or
                imageLower.endswith('.eer') or
                imageLower.endswith('.gain')):
            dims = Image.get_dimensions(imagePath)
            if len(dims) == 2:
                x, y = dims
                return {
                    'info': f'{x} x {y}',
                }
            if len(dims) == 3:
                x, y, n = dims
                return {
                    'dataType': STACK_2D,
                    'info': f'{x} x {y} x {n}',
                }
        return None

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

    @staticmethod
    def get_array(imagePath):
        imageLower = imagePath.lower()
        if imageLower.endswith('.mrc') or imageLower.endswith('.mrcs'):
            with mrcfile.open(imagePath) as mrc:
                return mrc.data
        elif (imageLower.endswith('.tif') or
              imageLower.endswith('.tiff') or
              imageLower.endswith('.eer') or
              imageLower.endswith('.gain')):
            with tifffile.TiffFile(imagePath) as tif:
                return tif.asarray()
        return None

    @staticmethod
    def _fourier_output_size(size, scale):
        """Return rounded output size for a given scale factor."""
        return max(1, int(round(size * scale)))

    @staticmethod
    def _fourier_axis_slices(in_size, out_size):
        """Return source/destination slices for DC-centered crop or pad.

        The DC component lives at in_size // 2 in the shifted spectrum, so the
        crop/pad is centered there rather than on the array geometric center.
        This keeps even and odd input/output sizes aligned correctly.
        """
        if out_size <= in_size:
            src_start = in_size // 2 - out_size // 2
            dst_start = 0
            length = out_size
        else:
            src_start = 0
            dst_start = out_size // 2 - in_size // 2
            length = in_size
        return src_start, dst_start, length

    @staticmethod
    def _is_volume(imagePath, array):
        """Return True when a 3D array should be treated as a volume."""
        if array.ndim != 3:
            return False

        if Path.exists(imagePath):
            metadata = Image.get_metadata(imagePath)
            if metadata and metadata.get('dataType') == VOLUME:
                return True

        z, y, x = array.shape
        return z == y == x

    @staticmethod
    def _fourier_rescale(image, scale):
        """Resize an n-D image by Fourier cropping or zero-padding."""
        shape = image.shape
        new_shape = tuple(Image._fourier_output_size(s, scale) for s in shape)

        if new_shape == shape:
            return np.array(image, copy=True)

        spectrum = np.fft.fftshift(np.fft.fftn(image))
        resized = np.zeros(new_shape, dtype=spectrum.dtype)

        src_slices = []
        dst_slices = []
        for in_size, out_size in zip(shape, new_shape):
            src_start, dst_start, length = Image._fourier_axis_slices(
                in_size, out_size)
            src_slices.append(slice(src_start, src_start + length))
            dst_slices.append(slice(dst_start, dst_start + length))

        resized[tuple(dst_slices)] = spectrum[tuple(src_slices)]

        # Preserve average intensity when changing the number of pixels.
        amp = np.prod(new_shape) / np.prod(shape)
        result = np.real(np.fft.ifftn(np.fft.ifftshift(resized * amp)))

        if np.issubdtype(image.dtype, np.floating):
            return result.astype(image.dtype, copy=False)
        return result

    @staticmethod
    def fourier_crop(imagePath, scale):
        """Resize an image by Fourier cropping or padding.

        Args:
            imagePath: Path to a supported image file.
            scale: Output-size multiplier per axis (e.g. 0.5 halves the size).

        Returns:
            Rescaled numpy array with the same dimensionality as the input.
        """
        array = Image.get_array(imagePath)
        if array is None:
            raise ValueError("Unsupported image format: %s" % imagePath)
        if scale <= 0:
            raise ValueError("Scale must be positive, got: %s" % scale)

        if array.ndim == 2:
            return Image._fourier_rescale(array, scale)

        if array.ndim == 3:
            if Image._is_volume(imagePath, array):
                return Image._fourier_rescale(array, scale)

            return np.stack(
                [Image._fourier_rescale(array[i], scale)
                 for i in range(array.shape[0])],
                axis=0,
            )

        raise ValueError("Expected 2D or 3D image, got shape: %s" % (array.shape,))

    @staticmethod
    def matrix_from_xf(xf_row):
        """Build a 3x3 homogeneous 2D affine matrix from an IMOD-style XF row.

        Args:
            xf_row: Sequence of 6 floats [A11, A12, A21, A22, DX, DY], as
                returned e.g. by RelionStar.alignment_to_xf or
                Imod.get_alignment_from_xf. Following the IMOD .xf
                convention (also used by RELION-5's tomography data model,
                see Burt et al., FEBS Open Bio 2024), this maps
                image-centred RAW-image coordinates (x, y) onto their
                position in the ALIGNED image:

                    [x']   [A11 A12] [x]   [DX]
                    [y'] = [A21 A22] [y] + [DY]

        Returns:
            np.ndarray: 3x3 matrix [[A11, A12, DX], [A21, A22, DY], [0, 0, 1]],
            suitable for Image.apply_transform.
        """
        a11, a12, a21, a22, dx, dy = xf_row
        return np.array([[a11, a12, dx],
                          [a21, a22, dy],
                          [0.0, 0.0, 1.0]], dtype=np.float64)

    @staticmethod
    def apply_transform(image, matrix, order=1, cval=0.0, output_shape=None):
        """Resample a 2D image with a 3x3 affine transformation matrix.

        This is meant to apply tilt-series alignment (in-plane rotation and
        shift, as produced by AreTomo2/3, IMOD/etomo or the Warp ts-align
        wrapper) on the fly, without writing a new aligned image to disk.

        `matrix` follows the same (x, y), image-centred convention as the
        IMOD .xf format used elsewhere in emtools (see
        Image.matrix_from_xf and RelionStar.alignment_to_xf /
        alignment_from_xf): it maps a RAW image pixel onto its position in
        the ALIGNED image. As in IMOD, the centre of both images is taken
        at (width // 2, height // 2).

        Args:
            image: 2D numpy array (a single tilt image) to be aligned.
            matrix: 3x3 array-like, or a flat 6-value IMOD XF row
                (A11, A12, A21, A22, DX, DY), describing the raw-to-aligned
                transform.
            order: Spline interpolation order forwarded to
                scipy.ndimage.affine_transform (1 = bilinear).
            cval: Fill value used for output pixels that fall outside the
                input image.
            output_shape: Optional (height, width) of the output image.
                Defaults to the shape of `image`.

        Returns:
            np.ndarray: The aligned image; same dtype as the input when it
            is a floating type.
        """
        from scipy.ndimage import affine_transform

        array = np.asarray(image)
        if array.ndim != 2:
            raise ValueError(
                "apply_transform expects a 2D image, got shape: %s" % (array.shape,))

        matrix = np.asarray(matrix, dtype=np.float64)
        if matrix.shape in ((6,), (2, 3)):
            matrix = Image.matrix_from_xf(np.ravel(matrix))
        if matrix.shape != (3, 3):
            raise ValueError(
                "Expected a 3x3 affine matrix (or a 6-value XF row), got "
                "shape: %s" % (matrix.shape,))

        out_shape = tuple(output_shape) if output_shape else array.shape
        in_h, in_w = array.shape
        out_h, out_w = out_shape

        # `matrix` maps raw -> aligned pixels; scipy.ndimage.affine_transform
        # needs the inverse (aligned/output -> raw/input) to resample each
        # output pixel.
        inverse = np.linalg.inv(matrix)
        rotation = inverse[:2, :2]
        translation = inverse[:2, 2]

        # Swap from the (x, y) maths convention used by the alignment
        # matrix to numpy's (row, col) = (y, x) array-index convention.
        swap = np.array([[0.0, 1.0], [1.0, 0.0]])
        rotation_rc = swap @ rotation @ swap
        translation_rc = swap @ translation

        # IMOD (and this codebase's XF <-> RELION conversions) place the
        # coordinate origin at (width // 2, height // 2) of each image.
        center_in = np.array([in_h // 2, in_w // 2], dtype=np.float64)
        center_out = np.array([out_h // 2, out_w // 2], dtype=np.float64)
        offset = center_in + translation_rc - rotation_rc @ center_out

        result = affine_transform(
            array.astype(np.float64, copy=False),
            rotation_rc,
            offset=offset,
            output_shape=out_shape,
            order=order,
            cval=cval,
            mode='constant',
        )

        if np.issubdtype(array.dtype, np.floating):
            return result.astype(array.dtype, copy=False)
        return result

    @staticmethod
    def rescale_array(image, scale):
        """Rescale a 2D image array by Fourier cropping or zero-padding.

        Same operation as Image.fourier_crop, but operating directly on an
        in-memory 2D array instead of reading a file from disk. Used to
        resample a tilt image to a different pixel size (e.g. to match the
        pixel size at which an alignment was computed), and/or to
        downscale large tilt images before generating a preview thumbnail.

        Args:
            image: 2D numpy array.
            scale: Output-size multiplier per axis (e.g. 0.5 halves the
                size).

        Returns:
            np.ndarray: Rescaled 2D array.
        """
        array = np.asarray(image)
        if array.ndim != 2:
            raise ValueError(
                "rescale_array expects a 2D image, got shape: %s" % (array.shape,))
        if scale <= 0:
            raise ValueError("Scale must be positive, got: %s" % scale)
        if scale == 1:
            return np.array(array, copy=True)
        return Image._fourier_rescale(array, scale)
