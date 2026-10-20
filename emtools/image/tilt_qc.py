# **************************************************************************
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
""" Image content measures of the tilts of a tilt series, from their jpegs
(emtools.image.thumbnail.TiltThumbnails: the size and recipe the measures
were calibrated on), and the curation rule.

What curators reject a tilt for is mostly in the image: blank, partly
blacked out (a lamella edge or a grid bar), or showing another area.  For
each tilt this measures:

    texture     median standard deviation of 16 px blocks (grey levels)
    darkArea    fraction of 16 px blocks with a mean below 40
    matchPeak   phase correlation peak with the last good tilt before it
                on its side of the first acquired tilt
    matchNcc    normalised cross correlation with that tilt
    fieldShift  shift from the first acquired tilt, in fractions of the
                field of view, accumulated along the same path

They are raw values: a reader makes texture and darkArea relative to the
series (median), so a series dark or low in contrast throughout is not
penalised.  The measures and the walk are the ones calibrated with the
tomo-data-curation skill on a hand curation (ChlamyBrnA, EMPIAR-11830).

One json per tilt series, <tomoName>_imageqc.json beside the jpegs:

    python -m emtools.image.tilt_qc PROJECT_OR_JOB [...] [--force]

writes it for tilt series processed before emwrap did it itself.

The curation rule (curate_series) turns the measures and the motion and CTF
values of the star file into the tilts to leave out: the OTF dashboard
proposes them, the emw-tilt-curation job applies them.
"""

import os
import sys
import json
import glob
import argparse

import numpy as np
from PIL import Image as PILImage

from .thumbnail import TiltThumbnails

VERSION = 1
SUFFIX = '_imageqc.json'
MEASURES = ('texture', 'darkArea', 'matchPeak', 'matchNcc', 'fieldShift')

N = 128            # side of the images compared, px
BLOCK = 16         # px, for texture and darkArea
DARK_LEVEL = 40    # grey level of a black block in the jpeg
# A neighbour this well matched becomes the reference for the next tilt
GOOD_PEAK = 0.08
_BILINEAR = getattr(PILImage, 'Resampling', PILImage).BILINEAR
# The high-pass filter and window of the compared images, made once
_KY, _KX = np.meshgrid(np.fft.fftfreq(N), np.fft.fftfreq(N), indexing='ij')
# high-pass: smooth shading (a dark corner) must not drive the match
_HIGHPASS = 1 - np.exp(-(_KX ** 2 + _KY ** 2) / (2 * 0.02 ** 2))
_WINDOW = np.outer(np.hanning(N), np.hanning(N))


def load_jpeg(path):
    return np.asarray(PILImage.open(path).convert('L'), dtype=np.float32)


def block_measures(a):
    """ (texture, darkArea) of a grey level image. """
    h, w = (a.shape[0] // BLOCK) * BLOCK, (a.shape[1] // BLOCK) * BLOCK
    blocks = a[:h, :w].reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK)
    return (float(np.median(blocks.std(axis=(1, 3)))),
            float((blocks.mean(axis=(1, 3)) < DARK_LEVEL).mean()))


def _prep(a):
    small = np.asarray(PILImage.fromarray(a).resize((N, N), _BILINEAR), dtype=np.float32)
    hp = np.real(np.fft.ifft2(np.fft.fft2(small) * _HIGHPASS))
    hp = (hp - hp.mean()) / (hp.std() + 1e-6)
    return hp * _WINDOW


def _match(a, b):
    """ Shift (fractions of the field), phase correlation peak and
    normalised cross correlation between two prepared images. """
    fa, fb = np.fft.fft2(a), np.fft.fft2(b)
    cross = fa * np.conj(fb)
    r = np.real(np.fft.ifft2(cross / (np.abs(cross) + 1e-6)))
    y, x = np.unravel_index(np.argmax(r), r.shape)
    peak = float(r[y, x])
    y, x = (y - N if y > N // 2 else y), (x - N if x > N // 2 else x)
    ncc = float(np.real(np.fft.ifft2(cross)).max() / (np.sqrt((a ** 2).sum() * (b ** 2).sum()) + 1e-6))
    return x / N, y / N, peak, ncc


def series_measures(tilts):
    """ Measures of each tilt of one tilt series.

    tilts: dicts with 'movie' (index, acquisition order), 'angle' and
    'image' (grey level array, or None if there is no jpeg).  Returns one
    dict per tilt, in tilt angle order, with 'movie', 'angle' and the
    measures it has (the first acquired tilt has no match values).
    """
    tilts = sorted(tilts, key=lambda t: t['angle'])
    rows, imgs = [], {}
    for i, t in enumerate(tilts):
        r = {k: t[k] for k in ('movie', 'angle', 'name') if k in t}
        if t.get('image') is not None:
            r['texture'], r['darkArea'] = block_measures(t['image'])
            imgs[i] = _prep(t['image'])
        rows.append(r)
    # Follow the field outward from the first acquired tilt, each tilt
    # compared with the last good one before it on its side (by position,
    # so a repeated movie index does not merge two tilts)
    if rows:
        i0 = min(range(len(tilts)), key=lambda i: tilts[i]['movie'])
        for side in (range(i0 + 1, len(tilts)), range(i0 - 1, -1, -1)):
            ref, pos = i0, np.zeros(2)
            for i in side:
                if i not in imgs or ref not in imgs:
                    continue
                dx, dy, peak, ncc = _match(imgs[ref], imgs[i])
                rows[i].update(matchPeak=peak, matchNcc=ncc,
                               fieldShift=float(np.hypot(*(pos + [dx, dy]))))
                if peak > GOOD_PEAK:
                    pos, ref = pos + [dx, dy], i
    return rows


# --------------------------------------------------------------------------
# The curation rule: the only implementation.  The OTF dashboard flags and
# proposes with it, the emw-tilt-curation job applies it and the
# tomo-data-curation skill uses it.
# --------------------------------------------------------------------------
# Limits a tilt is left out beyond; None leaves the check out.  Calibrated
# on a hand curation of lamella tilt series (ChlamyBrnA, EMPIAR-11830).
DEFAULT_LIMITS = {
    'texture': 0.5,          # image texture under this fraction of the series median: blank
    'darkArea': 0.10,        # fraction of the field black beyond the series median: blacked out
    'matchPeak': 0.04,       # phase correlation with the tilt before under this...
    'matchNcc': 0.15,        # ...and normalised correlation under this: a different field
    'fieldShift': 0.30,      # shift from the first tilt, fractions of the field of view
    # Motion was no reason to reject below this; 50-75 Å flagged 34 kept tilts
    'motion': 75.0,          # accumulated motion, Å
    'ctfResolution': 10.0,   # CTF fit resolution, Å
    'ctfCorrelation': 0.15,  # CTF profile correlation (<movie>_ctf.json written by emwrap)
    'figureOfMerit': 0.03,   # CTF figure of merit (Warp does not report one)
    'astigmatism': 4000.0,   # Å
    'defocus': 60000.0,      # Å; overfocus (negative defocus) too
    'beyond': True,          # also the tilts acquired after one that lost the field
}
# Reasons meaning the tilt series lost the field: the tilts acquired after
# it on the same side of the first tilt are not trusted either ('beyond')
FIELD_REASONS = ('blank', 'blacked', 'field', 'shifted')
REASON_LABELS = {
    'motion': 'motion', 'ctf': 'CTF fit resolution', 'ctfcorr': 'CTF profile correlation',
    'fom': 'CTF figure of merit', 'astigmatism': 'astigmatism', 'defocus': 'defocus',
    'blank': 'blank image', 'blacked': 'blacked out', 'field': 'different field',
    'shifted': 'field shifted', 'beyond': 'after a tilt that lost the field',
}
# What a tilt dict may carry (missing or None: not measured, not judged):
#   movie, angle      movie index (acquisition order) and tilt angle
#   texture, darkArea, matchPeak, matchNcc, fieldShift    from series_measures
#   motion, ctfResolution, ctfCorrelation, figureOfMerit, astigmatism, defocus
#   dropped           processing dropped it: counts for the series medians,
#                     is not judged, and the field is not followed through it


def _median(values):
    v = [x for x in values if x is not None]
    return float(np.median(v)) if v else None


def relative_measures(tilts):
    """ (texture / series median, dark area - series median) of each tilt,
    in order, None where not measured.  Medians over every tilt given, so
    a tilt series dark or low in contrast throughout is not penalised. """
    texture = _median(t.get('texture') for t in tilts)
    dark = _median(t.get('darkArea') for t in tilts)
    return [(t['texture'] / texture if t.get('texture') is not None and texture else None,
             t['darkArea'] - dark if t.get('darkArea') is not None and dark is not None else None)
            for t in tilts]


def tilt_flags(tilts, limits=None):
    """ The reasons to leave out each tilt of one tilt series, in order
    (an empty list for a tilt kept or dropped).  Limits default to
    DEFAULT_LIMITS; 'beyond' is not applied here, see beyond_field. """
    lim = dict(DEFAULT_LIMITS, **(limits or {}))

    def over(v, key):
        return v is not None and lim.get(key) is not None and v > lim[key]

    def under(v, key):
        return v is not None and lim.get(key) is not None and v < lim[key]

    flags = []
    for t, (texture, dark) in zip(tilts, relative_measures(tilts)):
        why = []
        if not t.get('dropped'):
            if over(t.get('motion'), 'motion'):
                why.append('motion')
            if over(t.get('ctfResolution'), 'ctfResolution'):
                why.append('ctf')
            if under(t.get('ctfCorrelation'), 'ctfCorrelation'):
                why.append('ctfcorr')
            if under(t.get('figureOfMerit'), 'figureOfMerit'):
                why.append('fom')
            if t.get('astigmatism') is not None and over(abs(t['astigmatism']), 'astigmatism'):
                why.append('astigmatism')
            d = t.get('defocus')
            if d is not None and lim.get('defocus') is not None and (d < 0 or d > lim['defocus']):
                why.append('defocus')
            if under(texture, 'texture'):
                why.append('blank')
            if over(dark, 'darkArea'):
                why.append('blacked')
            if under(t.get('matchPeak'), 'matchPeak') and under(t.get('matchNcc'), 'matchNcc'):
                why.append('field')
            if over(t.get('fieldShift'), 'fieldShift'):
                why.append('shifted')
        flags.append(why)
    return flags


def beyond_field(tilts, flags):
    """ Add 'beyond' to the flags (aligned with tilts) of the tilts
    acquired after one that lost the field (FIELD_REASONS), on the same
    side of the first acquired tilt.  Dropped tilts, and those without a
    movie index or angle, are left out of the walk. """
    walk = [(t, f) for t, f in zip(tilts, flags) if not t.get('dropped')
            and t.get('movie') is not None and t.get('angle') is not None]
    if not walk:
        return flags
    first = min(walk, key=lambda x: x[0]['movie'])[0]['angle']
    for sign in (1, -1):
        lost = False
        for t, f in sorted((x for x in walk if (x[0]['angle'] - first) * sign > 0),
                           key=lambda x: abs(x[0]['angle'] - first)):
            if set(f) & set(FIELD_REASONS):
                lost = True
            elif lost and not f:
                f.append('beyond')
    return flags


def curate_series(tilts, limits=None):
    """ {movie index: [reasons]} for the tilts of one tilt series to leave
    out: tilt_flags, and beyond_field unless limits['beyond'] is off. """
    limits = dict(DEFAULT_LIMITS, **(limits or {}))
    flags = tilt_flags(tilts, limits)
    if limits.get('beyond'):
        beyond_field(tilts, flags)
    return {t['movie']: f for t, f in zip(tilts, flags) if f and t.get('movie') is not None}


def json_path(thumbnails_dir, tomo_name):
    return os.path.join(thumbnails_dir, tomo_name + SUFFIX)


def read_series_json(path, tilts=None):
    """ The measures (rows) of a series json, or None if it is missing,
    unreadable, of another version, or, given tilts, older than one of
    their jpegs or missing one of them. """
    try:
        with open(path) as f:
            data = json.load(f)
        rows = data['tilts'] if data.get('version') == VERSION else None
        if rows is not None and tilts is not None:
            jpegs = [t['jpeg'] for t in tilts if t.get('jpeg') and os.path.exists(t['jpeg'])]
            names = {r.get('name') for r in rows}
            if (any(t['name'] not in names for t in tilts if t.get('jpeg'))
                    or (jpegs and os.path.getmtime(path) < max(map(os.path.getmtime, jpegs)))):
                return None
        return rows
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def write_series_json(path, tomo_name, tilts, force=False):
    """ Measure the tilts of a series and write the json, unless it is
    up to date: newer than every jpeg and listing the same tilts.

    tilts: dicts with 'movie', 'angle', 'name' (the micrograph base name,
    which is how readers match a tilt) and 'jpeg' (path, None for a tilt
    without an average: left out).  Returns (rows, written): the measures,
    None if no jpeg exists.  Written to a temporary file then renamed, so a
    reader never gets a partial file.
    """
    tilts = [t for t in tilts if t.get('jpeg')]
    if not any(os.path.exists(t['jpeg']) for t in tilts):
        return None, False
    if not force:
        rows = read_series_json(path, tilts)
        if rows is not None and len(rows) == len(tilts):
            return rows, False
    rows = series_measures([
        dict(movie=t['movie'], angle=t['angle'], name=t['name'],
             image=load_jpeg(t['jpeg']) if os.path.exists(t['jpeg']) else None)
        for t in tilts])
    data = {'version': VERSION, 'tomoName': tomo_name,
            'source': 'tilt jpegs', 'jpegSize': TiltThumbnails.SIZE,
            'blockSize': BLOCK, 'darkLevel': DARK_LEVEL, 'tilts': rows}
    TiltThumbnails.save_json(data, path)
    return rows, True


def _star_float(d, key, placeholder_zero=False):
    """ A star value as a float, None when missing or, for the values the
    pipeline leaves at 0 when it did not measure them, a zero. """
    v = d.get(key)
    if v in (None, '', 'None'):
        return None
    v = float(v)
    return None if placeholder_zero and v == 0 else v


def tilts_from_star_rows(rows, root='', ctf_correlation=True, thumbnails=None):
    """ The tilts of a tilt series star file as the measures and the rule
    take them: 'movie', 'angle', 'name' (micrograph base name), 'mic' and
    'jpeg' (the tilt average and its jpeg, TiltThumbnails; None without an
    average, or the jpeg None if the average is not in a job folder), the
    star values of the rule (placeholder zeros as None) and the CTF profile
    correlation.

    rows: dicts of the star rows (values as strings or numbers); root: what
    the paths in them are relative to; ctf_correlation: whether to read
    the _ctf.json of each tilt; thumbnails: the folder of the jpegs and
    jsons, by default the one of the job of each file.  Raises ValueError
    without the movie index or the tilt angle.
    """
    tilts = []
    for d in rows:
        for col in ('rlnTomoTiltMovieIndex', 'rlnTomoNominalStageTiltAngle'):
            if d.get(col) in (None, '', 'None'):
                raise ValueError(f"no '{col}': it is needed to follow the tilts in "
                                 "acquisition order")
        mic = d.get('rlnMicrographName')
        mic = None if mic in (None, '', 'None') else mic
        ps = d.get('rlnCtfPowerSpectrum')
        ps = None if ps in (None, '', 'None') else ps
        name = os.path.splitext(os.path.basename(mic or d.get('rlnMicrographMovieName') or ''))[0]
        jpeg = TiltThumbnails.tilt_jpeg(mic, thumbnails) if mic else None
        tilts.append({
            'movie': int(float(d['rlnTomoTiltMovieIndex'])),
            'angle': float(d['rlnTomoNominalStageTiltAngle']),
            'name': name,
            'mic': os.path.join(root, mic) if mic else None,
            'jpeg': os.path.join(root, jpeg) if jpeg else None,
            'motion': _star_float(d, 'rlnAccumMotionTotal', True),
            'ctfResolution': _star_float(d, 'rlnCtfMaxResolution', True),
            'figureOfMerit': _star_float(d, 'rlnCtfFigureOfMerit', True),
            'astigmatism': _star_float(d, 'rlnCtfAstigmatism'),
            'defocus': _star_float(d, 'rlnDefocusU'),
            'ctfCorrelation': (TiltThumbnails.read_ctf_correlation(os.path.join(root, ps), thumbnails)
                               if ctf_correlation and ps else None),
        })
    return tilts


def star_tilts(star_path, root):
    """ The tilts of a tilt series star file (tilts_from_star_rows) and
    the thumbnails folder of their jpegs, None without averages. """
    from emtools.metadata import StarFile
    with StarFile(star_path) as sf:
        rows = [r._asdict() for r in sf.iterTable(sf.getTableNames()[0], guessType=False)]
    tilts = tilts_from_star_rows(rows, root, ctf_correlation=False)
    jpeg = next((t['jpeg'] for t in tilts if t['jpeg']), None)
    return tilts, os.path.dirname(jpeg) if jpeg else None


def backfill_job(job_dir, force=False, log=print):
    """ Write the json of every tilt series a job's tilt_series.star lists. """
    from emtools.metadata import StarFile
    job_dir = os.path.abspath(job_dir)
    root = os.path.dirname(os.path.dirname(job_dir))
    star = os.path.join(job_dir, 'tilt_series.star')
    if not os.path.exists(star):
        return 0, 0
    with StarFile(star) as sf:
        series = [(r.rlnTomoName, r.rlnTomoTiltSeriesStarFile)
                  for r in sf.iterTable('global', guessType=False)]
    written = 0
    for name, ts_star in series:
        path = os.path.join(root, ts_star)
        if not os.path.exists(path):
            continue
        try:
            tilts, folder = star_tilts(path, root)
            # Only the job that wrote the jpegs: later jobs point at the same
            # folder with fewer tilts (those they dropped), and the series
            # medians must be over the tilts motion correction gave
            if (folder and os.path.isdir(folder)
                    and os.path.abspath(folder).startswith(job_dir + os.sep)):
                written += write_series_json(json_path(folder, name), name, tilts, force=force)[1]
        except Exception as e:
            log(f'  {name}: {e}')
    return written, len(series)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('paths', nargs='+', help='RELION project folders (every job with a tilt_series.star '
                                            'is done) or job folders')
    p.add_argument('--force', action='store_true', help='rewrite jsons that are up to date')
    args = p.parse_args()
    for path in args.paths:
        if os.path.exists(os.path.join(path, 'default_pipeline.star')):
            jobs = sorted(os.path.dirname(s) for s in glob.glob(os.path.join(path, '*', 'job*', 'tilt_series.star')))
        else:
            jobs = [path]
        for job in jobs:
            written, total = backfill_job(job, force=args.force)
            if total:
                print(f'{job}: {written} of {total} tilt series written', flush=True)


if __name__ == '__main__':
    sys.exit(main())
