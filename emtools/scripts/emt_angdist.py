#!/usr/bin/env python
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

""" This script serve to plot angular distribution from a Relion refinement
STAR file. It can also be used to select overrepresent areas and balance
the distribution of particles creating a new STAR files with a more even
angular distribution.

Plot code was taken from

"""

import os
import json
import argparse
import numpy as np

import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.colors import LogNorm
from matplotlib.widgets import RectangleSelector

from emtools.utils import Timer, Color
from emtools.metadata import StarFile, Table


def point_in_rect(x, y, rect):
    lx, ly, rx, ry = rect
    return lx < x < rx and ry < y < ly


def rect_area(rect):
    lx, ly, rx, ry = rect
    return (rx - lx) * (ly - ry)


class AngularDistPlot:
    def __init__(self, starfile):
        """Plot a 2D histogram of Euler angles distribution from a run_data.star
        file produced by RELION."""
        print(f"Input STAR file: {Color.cyan(starfile)}")
        t = Timer()

        with StarFile(starfile) as sf:
            size = sf.getTableSize('particles')
            info = sf.getTableInfo('particles')
            #info = sf.getTable('particles')
            anglesRot = np.zeros(size)
            anglesTilt = np.zeros(size)
            print("\nLoading particles...")
            for i, p in enumerate(sf.iterTable('particles')):
                anglesRot[i] = p.rlnAngleRot
                anglesTilt[i] = p.rlnAngleTilt

        self.anglesRot = anglesRot
        self.anglesTilt = anglesTilt
        self.starfile = starfile
        self.tableInfo = info

        t.toc()
        print()

        print(f"anglesRot: min={min(anglesRot):0.2f}, max={max(anglesRot):0.2f}")
        print(f"anglesTilt: min={min(anglesTilt):0.2f}, max={max(anglesTilt):0.2f}")
        a = (360 * 180)
        print(f"Total particles: {Color.green(size)}, density: {self._density(size / a)}")

    def _density(self, d):
        return Color.warn("%0.2f" % d)

    def balance(self, areas, density, outputStar):
        selected = self.points_in_areas(areas)
        size = len(selected)
        a = sum(rect_area(rect) for rect in areas)
        d = size / a  # density in selected areas
        print(f"\nSelected areas: {Color.bold([list(r) for r in areas])}")
        print(f"Selected particles: {Color.green(size)}, density: {self._density(d)}")
        x = size - int((density / d) * size)
        print(f"\nTo achieve desired density of {self._density(density)} "
              f"will remove {Color.red(x)} random particles from selected areas. ")

        print(f"Writing output STAR file: {Color.cyan(outputStar)}")
        t = Timer()

        # Elements to remove sorted ascending
        to_remove = np.sort(np.random.choice(selected, x, replace=False))

        with StarFile(self.starfile) as sf:
            with StarFile(outputStar, 'w') as outSf:
                # Preserve all tables, except particles that will be a subset
                for tableName in sf.getTableNames():
                    if tableName == 'particles':
                        table = Table(columns=self.tableInfo.getColumns())
                        outSf.writeHeader('particles', table)
                        counter = 0
                        for i, p in enumerate(sf.iterTable('particles')):
                            if i == to_remove[counter]:  # Skip this item
                                counter += 1
                                continue
                            outSf.writeRow(p)
                    else:
                        table = sf.getTable(tableName)
                        outSf.writeTable(tableName, table)

        t.toc()
        print()

    def plot(self):
        title = ''
        colormap = 'jet'  # 'viridis'
        gridsize = 50
        self.build_histogram(self.anglesRot,
                             self.anglesTilt, title, colormap, gridsize)
        plt.show()

    def points_in_areas(self, areas):
        points = [i for i, (x, y) in enumerate(zip(self.anglesRot, self.anglesTilt))
                  if any(point_in_rect(x, y, rect) for rect in areas)]
        return points

    def line_select_callback(self, eclick, erelease):
        'eclick and erelease are the press and release events'
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        lx, ly = min(x1, x2), max(y1, y2)
        rx, ry = max(x1, x2), min(y1, y2)
        rect = (lx, ly, rx, ry)

        points = self.points_in_areas([rect])
        size = len(points)
        a = rect_area(rect)

        print(f"Rect: {Color.bold('[%3.2f, %3.2f, %3.2f, %3.2f]' % rect)}")
        if size:
            print(f"Selected particles: {Color.green(size)}, "
                  f"density: {size / a:0.2f}")

            # with StarFile('selection.star', 'w') as outSf:
            #     table = Table(self.tableInfo.getColumns())
            #     for p in points:
            #         table.addRow(self.tableInfo[p])
            #     outSf.writeTable('particles', table)
            #
            # os.system('scipion show selection.star')

    def build_histogram(self, anglesRot, anglesTilt, title, colormap, gridsize):
        """Build a 2D histogram of number of particles per Euler angle pair."""
        fig, ax = plt.subplots()
        hb = ax.hexbin(anglesRot, anglesTilt, bins='log', cmap=colormap, gridsize=gridsize)
        ax.set(xlim=(-180, 180), ylim=(0, 180))
        ax.set_xlabel('$\phi$ (rlnAngleRot, deg)')
        ax.set_xticks(range(-180, 181, 45))
        ax.set_ylabel('$\\theta$ (rlnAngleTilt, deg)')
        ax.set_yticks(range(0, 181, 45))
        ax.set_title(title)
        fig.gca().set_aspect('equal', adjustable='box')
        divider = make_axes_locatable(ax)
        cax = divider.append_axes('right', size='5%', pad=0.1)
        cb = fig.colorbar(hb, ax=ax, cax=cax)
        cb.set_label('Number of particles')
        fig.tight_layout()

        # drawtype is 'box' or 'line' or 'none'
        self.rect_selector = RectangleSelector(ax, self.line_select_callback,
                                               drawtype='box', useblit=True,
                                               button=[1, 3],  # don't use middle button
                                               minspanx=5, minspany=5,
                                               spancoords='pixels',
                                               interactive=True)
        # plt.connect('key_press_event', self.toggle_selector)

        return fig

    def build_hist(self, anglesRot, anglesTilt, nbins):
        plt.hist2d(anglesRot, anglesTilt, bins=nbins, cmap='jet', norm=LogNorm())
        plt.colorbar()
        plt.title("Rot vs Tilt euler angle histogram")
        plt.xlabel("Rot")
        plt.ylabel("Tilt")


def main():
    p = argparse.ArgumentParser(prog='emt-angdist')
    p.add_argument('input_star', metavar='INPUT_STARFILE',
                    help="Input STAR file from Relion refine containing "
                         "particle angular distribution. "
                         "e.g. relion_it015_data.star")
    p.add_argument('--balance', '-b', nargs=3,
                   metavar=('AREAS_JSON_STR', 'DENSITY', 'OUTPUT_STARFILE'))

    p.add_argument('--class3d', '-c', type=int)

    args = p.parse_args()

    if not os.path.exists(args.input_star):
        raise Exception(f"Input file {args.input_star} does not exists")

    adp = AngularDistPlot(args.input_star)

    if args.balance:
        areas = [tuple(r) for r in json.loads(args.balance[0])]
        density = float(args.balance[1])
        outputStar = args.balance[2]
        adp.balance(areas, density, outputStar)
    else:
        adp.plot()


if __name__ == '__main__':
    main()
