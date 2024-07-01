
StarFile
========

This class allows you to read and write data blocks from STAR files.
There are some features that make this class useful for the manipulation of data in STAR format:


* Inspect data blocks, columns, and the number of elements without parsing the entire file.
* Iterate over the rows without reading the whole table in memory.
* Read or iterate over a subset of rows only.


Inspecting without fully parsing
--------------------------------

For example, let's inspect a Relion output STAR file such as the one
here:

https://github.com/3dem/em-testdata/blob/main/metadata/run_it025_data.star

.. code-block:: python

    from emtools.metadata import StarFile

    filename = 'run_it025_data.star'

    # Let's inspect how what data blocks are in the file
    sf = StarFile(filename)
    print(sf.getTableNames())

    #>>> ['optics', 'particles']

    # Let's check number of columns and rows on each data block
    for tableName in sf.getTableNames():
        size = sf.getTableSize(tableName)
        # The info is a table with same columns but no rows
        info = sf.getTableInfo(tableName)
        print(f"data {tableName}: "
              f"\n\t  items: {size} "
              f"\n\tcolumns: {len(info.getColumnNames())}")

    #>>> data optics:
    #>>>       items: 1
    #>>>     columns: 10
    #>>> data particles:
    #>>>       items: 4786
    #>>>     columns: 25

    sf.close()


The methods used in the previous example (`getTableNames`, `getTableSize`, and `getTableInfo`)
all inspect the STAR file without fully parsing all rows. This way is much more faster
that parsing rows if not needed. These methods will also create an index of where
data blocks are in the file, so if you need to read a data table, it will jump to
that position in the file.

Reading a Table
---------------

After opening a StarFile, we can easily read any table using the function `getTable`
as shown in the following example:

.. code-block:: python

    with StarFile(movieStar) as sf:
        # Read table in a different order as they appear in file
        # also before the getTableNames() call that create the offsets
        t1 = sf.getTable('local_shift')
        t2 = sf.getTable('general')

This function has some optional arguments such as *guessType* for inferring
the column type from the first row. In some cases this is not desired and one
can pass *guessType=False* and then all columns will be treated as strings.
For example, reading the ``job.star`` file:

.. code-block:: python

    with StarFile('job.star') as sf:
        print(f"Tables: {sf.getTableNames()}")  # ['job', 'joboptions_values']
        t = sf.getTable('joboptions_values', guessType=False)
        values = {row.rlnJobOptionVariable: row.rlnJobOptionValue for row in t}


Iterating over the Table rows
-----------------------------

In some cases, we just want to iterate over the rows and operate on them one by one.
In that case, it is not necessary to fully load the whole table in memory. Iteration
also allows to read range of rows but not all of them. This is specially useful
for visualization purposes, where we can show a number of elements and allow to go
through all of them in an efficient manner.

Please check the :ref:`Examples` for practical use cases.


Writing STAR files
------------------

It is easy to write STAR files using the :class:`StarFile` class. We just need to
open it with write mode enabled. Then we could just write a table header
and then write rows one by one, or we could write an entire table at once.

Please check the :ref:`Examples` for practical use cases.

Examples
--------

Parsing EPU's XML files
.......................

Although the :py:class:`StarFile` class has been used mainly to handle Relion STAR files,
we can use any label and table names. For example, if we want to parse the
XML files from EPU to extract the beam shift per movie, and write an output
STAR file:

.. code-block:: python

    out = StarFile(outputStar, 'w')
    t = Table(['movieBaseName', 'beamShiftX', 'beamShiftY'])
    out.writeHeader('Movies', t)

    for base, x, y in EPU.get_beam_shifts(inputDir):
        out.writeRow(t.Row(movieBaseName=base, beamShiftX=x, beamShiftY=y))

    out.close()


Note in this example that we are not storing the whole table in memory. We just
create an empty table with the desired columns and then we write one row for
each XML file parsed.


Balancing Particles views based on orientation angles
.....................................................

We could read angle Rot and Tilt from a particles STAR file as numpy arrays:

.. code-block:: python

    with StarFile('particles.star') as sf:
        size = sf.getTableSize('particles')
        info = sf.getTableInfo('particles')
        # Initialize the numpy arrays with zero and the number of particles
        anglesRot = np.zeros(size)
        anglesTilt = np.zeros(size)
        # Then iterate the rows and store only these values
        for i, p in enumerate(sf.iterTable('particles')):
            anglesRot[i] = p.rlnAngleRot
            anglesTilt[i] = p.rlnAngleTilt


Then we can use these arrays to plot the values and assess angular regions
more dense and create a subset of points to make it more evenly distributed.
Let's assume we computed the list of points to remove in the list *to_remove*.
Now, we can go through the input *particles.star* and we will create a similar
one, but with some particles removed. We will copy every table into the output
STAR files, except for the *particles* one, were whe need to filter out some
particles. We can do it with the following code:

.. code-block:: python

    with StarFile('particles.star') as sf:
        with StarFile('output_particles.star', 'w') as outSf:
            # Preserve all tables, except particles that will be a subset
            for tableName in sf.getTableNames():
                if tableName == 'particles':
                    info = sf.getTableInfo('particles')
                    table = Table(columns=info.getColumns())
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

Converting from Scipion to micrographs STAR file
................................................

The following function shows how we can write a *micrographs.star* file
from a Scipion set of CTFs:

.. code-block:: python

    def write_micrographs_star(micStarFn, ctfs):
        firstCtf = ctfs.getFirstItem()
        firstMic = firstCtf.getMicrograph()
        acq = firstMic.getAcquisition()

        with StarFile(micStarFn, 'w') as sf:
            optics = Table(['rlnOpticsGroupName',
                            'rlnOpticsGroup',
                            'rlnMicrographOriginalPixelSize',
                            'rlnVoltage',
                            'rlnSphericalAberration',
                            'rlnAmplitudeContrast',
                            'rlnMicrographPixelSize'])
            ps = firstMic.getSamplingRate()
            op = 1
            opName = f"opticsGroup{op}"
            optics.addRowValues(opName, op, ps,
                                acq.getVoltage(),
                                acq.getSphericalAberration(),
                                acq.getAmplitudeContrast(),
                                ps)

            sf.writeLine("# version 30001")
            sf.writeTable('optics', optics)

            mics = Table(['rlnMicrographName',
                          'rlnOpticsGroup',
                          'rlnCtfImage',
                          'rlnDefocusU',
                          'rlnDefocusV',
                          'rlnCtfAstigmatism',
                          'rlnDefocusAngle',
                          'rlnCtfFigureOfMerit',
                          'rlnCtfMaxResolution',
                          'rlnMicrographMovieName'])
            sf.writeLine("# version 30001")
            sf.writeHeader('micrographs', mics)

            for ctf in ctfs:
                mic = ctf.getMicrograph()
                u, v, a = ctf.getDefocus()
                micName = mic.getMicName()
                movName = os.path.join('data', 'Images-Disc1',
                                       micName.replace('_Data_FoilHole_',
                                                       '/Data/FoilHole_'))
                row = mics.Row(mic.getFileName(), op,
                               ctf.getPsdFile(),
                               u, v, abs(u - v), a,
                               ctf.getFitQuality(),
                               ctf.getResolution(),
                               movName)

                sf.writeRow(row)

Reference
---------

.. autoclass:: emtools.metadata.StarFile
   :members:



