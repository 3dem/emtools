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

import argparse
import mrcfile
import numpy as np

from .thumbnail import Image, Thumbnail



def show2D(inputFile, **kwargs):
    import matplotlib.pyplot as plt
    size = kwargs.get('size', 512)
    print("size: ", size)
    thumb = Thumbnail(max_size=(size, size), contrast_factor=0.15, std_threshold=1)
    array = Image.get_array(inputFile)
    plt.imshow(thumb.from_array(array), cmap='gray')
    plt.axis('off')  # Optional: Turn off axis labels and ticks
    plt.show()


def fourier_crop(inputFile, scale):
    array = Image.get_array(inputFile)
    return Image.fourier_crop(inputFile, scale)


def save_array(array, outputFile):
    if outputFile.endswith('.mrc'):
        with mrcfile.new(outputFile, overwrite=True) as mrc:
            mrc.set_data(array)
    elif outputFile.endswith('.png'):
        thumb = Thumbnail(max_size=None, contrast_factor=0.15)#, std_threshold=1)
        pil_img = thumb.from_array(array)
        pil_img.save(outputFile)
    else:
        raise ValueError(f"Unsupported file type: {outputFile}")
    return outputFile


def compare_images(inputFile1, inputFile2):
    array1 = Image.get_array(inputFile1)
    array2 = Image.get_array(inputFile2)
    return np.array_equal(array1, array2)



def main():
    p = argparse.ArgumentParser()
    p.add_argument('path', metavar="IMAGE_PATH",
                   help="Image path")
    p.add_argument('--show', '-s', action='store_true',
                   help="Show the image")
    p.add_argument('--max-size', '-m', type=int, default=512,
                   help="Size of the image")
    p.add_argument('--bin', '-b', type=float, default=None,
                  help="Bin factor for the image, using Fourier cropping. Bin 1 means no cropping, bin 2 means half the original size, etc.")
    p.add_argument('--output', '-o', type=str, default=None,
                  help="Output file name")
    p.add_argument('--compare', '-c', 
                  help="Compare the image with another image.")
    args = p.parse_args()

    if args.show:
        show2D(args.path, size=args.max_size)
    elif args.bin:
        if args.bin > 1:
            scale = 1 / args.bin
            array = fourier_crop(args.path, scale)
            if args.output:
                save_array(array, args.output)
        else:
            print("Bin factor must be greater than 1")
    elif args.compare:
        if compare_images(args.path, args.compare):
            print("Images are the same")
        else:
            print("Images are different")
    else:
        print(Image.get_dimensions(args.path))


if __name__ == '__main__':
    main()
