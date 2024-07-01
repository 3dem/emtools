#!/usr/bin/env python

# This script reads the optics group from a movies star file and change it
# accordingly in the particles starfile and writes a new particles star file
# with the updated values

import sys
import os
import argparse

from emtools.utils import Color
from emtools.metadata import StarFile, EPU, Table


def parse(inputDir, outputStar):
    """ Parse all xml files from the inputDir for each movie. """
    if not os.path.exists(inputDir):
        raise Exception(f"Input dir '{Color.red(inputDir)}' does not exist.")

    if not os.path.isdir(inputDir):
        raise Exception(f"Input '{Color.red(inputDir)}' must be a path.")

    out = StarFile(outputStar, 'w') if outputStar else StarFile(sys.stdout)

    t = Table(['movieBaseName', 'beamShiftX', 'beamShiftY'])
    out.writeHeader('Movies', t)

    i = 0
    for base, x, y in EPU.get_beam_shifts(inputDir):
        i += 1
        print("\rParsed: ", i, end="")
        out.writeRow(t.Row(movieBaseName=base, beamShiftX=x, beamShiftY=y))

    print()

    if outputStar:
        out.close()


class Cluster:
    """ Create cluster of points based on a given distance. """
    def __init__(self, distance):
        self.distance = distance
        self.d2 = distance ** 2
        self.groups = []

    def addPoint(self, p):
        best_dist = None
        best_group = None
        x, y = p['x'], p['y']
        for i, g in enumerate(self.groups):
            m = g['mean']
            d2 = (m['x'] - x) ** 2 + (m['y'] - y) ** 2

            if i == 0 or d2 < best_dist:
                best_group = i
                best_dist = d2
        # Create a new group if there are no groups or the best distance
        # is larger that the minimum group distance
        if best_group is None or best_dist > self.d2:
            best_group = len(self.groups)
            self.groups.append({'mean': p, 'points': [p]})
        else:  # Update best group with the new point
            g = self.groups[best_group]
            g['points'].append(p)
            m = g['mean']
            m['x'] = (m['x'] + x) / 2
            m['y'] = (m['y'] + y) / 2

        return best_group


def plot(inputStar, distance=0.005):
    """ Make a scatter plot from the star files with x, y beam shifts. """
    import matplotlib.pyplot as plt
    xvalues = []
    yvalues = []
    colors = []
    points = []
    cluster = Cluster(distance)

    with StarFile(inputStar) as sf:
        for i, row in enumerate(sf.iterTable('Movies')):
            xvalues.append(row.beamShiftX)
            yvalues.append(row.beamShiftY)
            points.append({'x': row.beamShiftX, 'y': row.beamShiftY, 'i': i + 1})

        for p in points:
            group = cluster.addPoint(p)
            colors.append(group)

    print("Groups: ", len(cluster.groups))

    plt.scatter(xvalues, yvalues, c=colors)

    for i, g in enumerate(cluster.groups):
        gid = str(i + 1)
        m = g['mean']
        plt.text(m['x'], m['y'], gid)

    plt.show()


def make_groups(inputStar, outputStar, distance=0.005):
    """ Make a scatter plot from the star files with x, y beam shifts. """
    cluster = Cluster(distance)

    with StarFile(inputStar) as sf:
        for row in sf.iterTable('Movies'):
            cluster.addPoint({'x': row.beamShiftX,
                              'y': row.beamShiftY,
                              'movieName': row.movieBaseName})

    t = Table(['rlnMicrographMovieName', 'rlnOpticsGroup'])

    for i, g in enumerate(cluster.groups):
        for point in g['points']:
            t.addRowValues(point['movieName'], i + 1)

    with StarFile(outputStar, 'w') as sf:
        sf.writeTable('movies', t)

    print("Groups: ", len(cluster.groups))


def main():
    parser = argparse.ArgumentParser(prog='emt_beamshifts')
    g = parser.add_mutually_exclusive_group()
    g.add_argument('--parse', metavar='XML_ROOT_FOLDER',
                   help="Parse beam shifts from this root folder for all "
                        "movies' xml files. Output file will be a star file "
                        "with movies basename and x and y shifts. This file "
                        "can be used for creating the groups with option "
                        "--make_groups")
    g.add_argument('--make_groups', metavar='BEAMSHIFTS_STAR',
                   help='Create optics groups')
    g.add_argument('--plot', '-p', metavar='BEAMSHIFTS_STAR',
                   help='Make a scatter plot with shift values from star file')

    parser.add_argument('--output', '-o', default='',
                        help="Output file depending in the action. ")
    parser.add_argument('--distance', '-d', default=0.005, type=float,
                        help="Distance for clusters")

    args = parser.parse_args()

    if args.parse:
        parse(args.parse, args.output)
    elif args.plot:
        plot(args.plot, args.distance)
    elif args.make_groups:
        make_groups(args.make_groups, args.output, args.distance)


if __name__ == '__main__':
    main()
