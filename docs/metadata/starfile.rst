
StarFile
========

This class allows to read and write data blocks from STAR files.
It is also designed to inspect the data blocks, columns
and number of elements in an efficient manner without parsing the entire
file.

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


The methods used in the previous example (`getTableNames`, `getTableSize`, and `getTableInfo`)
all inspect the STAR file without fully parsing all rows. This way is much more faster
that parsing rows if not needed. These methods will also create an index of where
data blocks are in the file, so if you need to read a data table, it will jump to
that position in the file.


Iterating over the rows
-----------------------

In some cases, we just want to iterate over the rows and operate on them one by one.
In that case, it is not necessary to fully load the whole table in memory. Iteration
also allows to read range of rows but not all of them. This is specially useful
for visualization purposes, where we can show a number of elements and allow to go
through all of them in an efficient manner.


Writing STAR files
------------------


Comparison with other libraries
-------------------------------


Reference
---------

.. autoclass:: emtools.metadata.StarFile
   :members:



