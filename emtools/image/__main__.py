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
from .thumbnail import Image


def main():
    p = argparse.ArgumentParser()
    p.add_argument('path', metavar="IMAGE_PATH",
                   help="Image path")

    args = p.parse_args()

    print(Image.get_dimensions(args.path))


if __name__ == '__main__':
    main()
