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

import os
import sys
import time
import argparse
from glob import glob
from datetime import datetime, timedelta
from pprint import pprint
import numpy as np
from collections import defaultdict

from emtools.utils import Process, Color, Path, Timer, Pretty
from emtools.metadata import StarFile, Table


ALL_TABLES = 'all'
OP_DROP = 'DROP'
OP_UPDATE = 'UPDATE'
OP_FILTER = 'FILTER'
VALID_OPERATIONS = {OP_DROP, OP_UPDATE, OP_FILTER}


def _normalizeOperation(op):
    op = op.strip().upper()
    if op not in VALID_OPERATIONS:
        raise ValueError(
            f"Unknown operation '{op}'. Valid values: {', '.join(sorted(VALID_OPERATIONS))}")
    return op


def _resolveTableName(table, tableNames):
    """Resolve table name; only the special 'all' token is case-insensitive."""
    table = table.strip()
    if table.lower() == ALL_TABLES:
        return ALL_TABLES
    if table not in tableNames:
        raise ValueError(f"Table '{table}' not found in input STAR file")
    return table


def _parseOperateArgs(operateArgs):
    """Flatten --operate argument groups into (TABLE, OPERATION, EXPR) tuples."""
    operations = []
    for group in operateArgs:
        if len(group) % 3 != 0:
            raise ValueError(
                "--operate expects groups of TABLE OPERATION EXPR "
                f"(multiple of 3 arguments), got {len(group)} in one --operate")
        for i in range(0, len(group), 3):
            operations.append((group[i], group[i + 1], group[i + 2]))
    return operations


def _parseOperateActions(operations, tableNames):
    """Build per-table action lists and the set of tables to drop."""
    explicitTables = set()
    dropTables = set()
    tableActions = defaultdict(list)
    allActions = []
    allDrop = False

    for table, operation, expr in operations:
        tableName = _resolveTableName(table, tableNames)
        operation = _normalizeOperation(operation)

        if tableName == ALL_TABLES:
            if operation == OP_DROP:
                allDrop = True
            else:
                allActions.append((operation, expr))
            continue

        explicitTables.add(tableName)

        if operation == OP_DROP:
            dropTables.add(tableName)
        else:
            tableActions[tableName].append((operation, expr))

    if allDrop:
        for tableName in tableNames:
            if tableName not in explicitTables:
                dropTables.add(tableName)

    return explicitTables, dropTables, tableActions, allActions


def _iterTableRows(sf, tableName, subset=None):
    kwargs = {'limit': subset} if subset is not None else {}
    return list(sf.iterTable(tableName, **kwargs))


def _writeProcessedTable(sfOut, tableName, tableInfo, rows, singleRow):
    if not rows:
        sfOut.writeTable(tableName, tableInfo)
        return

    if singleRow:
        sfOut.writeSingleRow(tableName, rows[0])
    else:
        result = tableInfo.cloneColumns()
        for row in rows:
            result.addRow(row)
        sfOut.writeTable(tableName, result)


def _writeUnchangedTable(sfIn, sfOut, tableName, subset=None):
    sfIn.getTableInfo(tableName)
    singleRow = sfIn._singleRow
    rows = _iterTableRows(sfIn, tableName, subset=subset)
    tableInfo = sfIn.getTableInfo(tableName)
    _writeProcessedTable(sfOut, tableName, tableInfo, rows, singleRow)


def _processTable(sf, tableName, actions, subset=None):
    tableInfo = sf.getTableInfo(tableName)
    singleRow = sf._singleRow
    table = tableInfo.cloneColumns()
    kwargs = {'limit': subset} if subset is not None else {}
    for row in sf.iterTable(tableName, **kwargs):
        table.addRow(row)

    for operation, expr in actions:
        if operation == OP_UPDATE:
            table.update(expr)
        elif operation == OP_FILTER:
            table.filter(expr)

    return tableInfo, list(table), singleRow


def operateStarFile(inputStar, operations, subset=None, output=None):
    if not operations:
        raise ValueError("At least one --operate action is required")

    if not os.path.exists(inputStar):
        raise FileNotFoundError(f"Input star file does not exist: {inputStar}")

    closeOutput = output is not None
    out = open(output, 'w') if closeOutput else sys.stdout

    try:
        with StarFile(inputStar) as sfIn:
            tableNames = sfIn.getTableNames()
            explicitTables, dropTables, tableActions, allActions = (
                _parseOperateActions(operations, tableNames))

            with StarFile(out, closeFile=closeOutput) as sfOut:
                sfOut.writeTimeStamp()

                for tableName in tableNames:
                    if tableName in dropTables:
                        continue

                    if tableName in explicitTables:
                        actions = tableActions.get(tableName, [])
                    else:
                        actions = list(allActions)

                    if not actions:
                        _writeUnchangedTable(sfIn, sfOut, tableName, subset=subset)
                    else:
                        tableInfo, rows, singleRow = _processTable(
                            sfIn, tableName, actions, subset=subset)
                        _writeProcessedTable(sfOut, tableName, tableInfo, rows, singleRow)
    finally:
        if closeOutput:
            out.close()


def printStarInfo(starFile):
    with StarFile(starFile) as sf:
        tables = sf.getTableNames()
        for t in tables:
            cols = sf.getTableInfo(t).getColumnNames()
            tSize = sf.getTableSize(t)
            print(f">>> {Color.bold('Table')}: {Color.green(t)}"
                  f"\n    - Columns: {Color.cyan(len(cols))} [{' '.join(c for c in cols)}]"
                  f"\n    -    Rows: {Color.cyan(tSize)}")


def groupBy(starFile, table, column):
    group = defaultdict(lambda: 0)

    with StarFile(starFile) as sf:
        for row in sf.iterTable(table):
            group[row.get(column)] += 1

    for k, v in group.items():
        print(k, v)


def checkDuplicates(inputStar, table, column):
    items = set()
    duplicates = []

    with StarFile(inputStar) as sf:
        for row in sf.iterTable(table):
            value = row.get(column)
            if value in items:
                duplicates.append(value)
            else:
                items.add(value)

    print(f">>> Duplicates: {len(duplicates)}\n"
          f"    {duplicates}")

def printColumns(inputStar, tableName=None, columns=None, subset=None):
    if not os.path.exists(inputStar):
        raise FileNotFoundError(f"Input star file does not exist: {inputStar}")

    with StarFile(inputStar) as sf:
        existingTables = sf.getTableNames()
        if tableName is None:
            if not existingTables:
                return
            tableName = existingTables[0]
        elif tableName not in existingTables:
            raise ValueError(f"Table name does not exist: {tableName}")

        columnList = columns.split() if columns else sf.getTableInfo(tableName).getColumnNames()
        table = _buildPrintTable(sf, tableName, columnList, subset=subset)
        StarFile.printTable(table, tableName)


def printAllTables(inputStar, subset=None):
    if not os.path.exists(inputStar):
        raise FileNotFoundError(f"Input star file does not exist: {inputStar}")

    with StarFile(inputStar) as sf:
        for tableName in sf.getTableNames():
            tableInfo = sf.getTableInfo(tableName)
            table = _buildPrintTable(sf, tableName, tableInfo.getColumnNames(),
                                     subset=subset)
            StarFile.printTable(table, tableName)


def _buildPrintTable(sf, tableName, columnList, subset=None):
    tableInfo = sf.getTableInfo(tableName)
    cols = [col for col in tableInfo.getColumns() if col.getName() in columnList]
    newTable = Table(columns=cols)
    kwargs = {'limit': subset} if subset is not None else {}
    for row in sf.iterTable(tableName, **kwargs):
        values = {k: getattr(row, k) for k in columnList}
        newTable.addRowValues(**values)
    return newTable


def splitBy(starFile, column, minSize):
    with StarFile(starFile) as sf:
        tOptics = sf.getTable('optics')
        tParticles = sf.getTableInfo('particles')
        rows = []
        count = 0
        map = {}

        def _writeStar(minSize=0):
            nonlocal count
            nonlocal rows

            if len(rows) <= minSize:
                return

            count += 1
            outStarFile = Path.replaceExt(starFile, f'_{count:03}.star')
            with StarFile(outStarFile, 'w') as sfOut:
                sfOut.writeTimeStamp()
                sfOut.writeTable('optics', tOptics)
                sfOut.writeHeader('particles', tParticles)
                for row in rows:
                    sfOut.writeRow(row)
            rows = []

        lastValue = None
        lastIndex = 0

        for row in sf.iterTable('particles'):
            value = getattr(row, column)
            if lastValue is not None and lastValue != value:
                _writeStar(int(minSize))
            rows.append(row)
            lastValue = value

        if rows:
            _writeStar(0)  # Write all remaining


def main():
    p = argparse.ArgumentParser(prog='emt-star')
    p.add_argument('input',
                   help="Input STAR file. ")
    p.add_argument('--group_by', '-g', nargs=2,
                   metavar=('TABLE', 'COLUMN'),
                   help="Count rows grouped by a given label")
    p.add_argument('--split_particles', '-s', nargs='+', metavar=('COLUMN', 'minsize'),
                   help="Split input particles by some column")
    p.add_argument('--duplicates', '-d', nargs=2,
                   metavar=('TABLE', 'COLUMN'),
                   help="Check duplicates values for a given label")
    outputMode = p.add_mutually_exclusive_group()
    outputMode.add_argument('--print', '-p', nargs='*',
                            metavar=('COLUMNS', 'TABLE'),
                            help="Print columns from STAR file tables to stdout. "
                                 "With no arguments, print all tables and all columns. "
                                 "With COLUMNS only, print from the first table. "
                                 "With COLUMNS and TABLE, print from the given table.")
    outputMode.add_argument('--operate', '-e', action='append', nargs='+',
                            metavar='TRIPLET',
                            help="Apply one or more operations. Each operation is a triplet "
                                 "TABLE OPERATION EXPR; multiple triplets can be passed in a "
                                 "single --operate. TABLE is the exact table name from the "
                                 "input STAR file, or 'all' (case insensitive) for all tables "
                                 "not explicitly listed in other operations. OPERATION can be "
                                 "UPDATE, FILTER, or DROP. For UPDATE, EXPR is comma-separated "
                                 "column=expression assignments. For FILTER, EXPR is a boolean "
                                 "expression per row. For DROP, EXPR is ignored.")
    p.add_argument('--subset', '-n', type=int, default=None, metavar='N',
                   help="Process at most N rows per table (for debugging)")
    p.add_argument('--output', '-o', default=None, metavar='FILE',
                   help="Write output STAR file to this path (default: stdout)")

    args = p.parse_args()
    inputStar = args.input

    if args.operate:
        operateStarFile(inputStar, _parseOperateArgs(args.operate),
                        subset=args.subset, output=args.output)
    elif args.group_by:
        table, column = args.group_by
        groupBy(inputStar, table, column)
    elif split := args.split_particles:
        column = split[0]
        minSize = split[1] if len(split) > 1 else 0
        splitBy(inputStar, column, minSize)
    elif args.duplicates:
        table, column = args.duplicates
        checkDuplicates(inputStar, table, column)
    elif args.print is not None:
        if len(args.print) == 0:
            printAllTables(inputStar, subset=args.subset)
        else:
            tableName = None
            cols = args.print[0]
            if len(args.print) > 2:
                raise ValueError("Only pass columns and optionally the table name")
            elif len(args.print) > 1:
                tableName = args.print[1]

            printColumns(inputStar, tableName, cols, subset=args.subset)
    else:
        printStarInfo(args.input)


if __name__ == '__main__':
    main()
