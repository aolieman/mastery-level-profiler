#!/usr/bin/python
# -*- coding: utf-8 -*-

def matrix_to_string(matrix, header=None):
    """
    Return a pretty, aligned string representation of a nxm matrix.
    From: http://mybravenewworld.wordpress.com/2010/09/19/print-tabular-data-nicely-using-python/

    This representation can be used to print any tabular data, such as
    database results. It works by scanning the lengths of each element
    in each column, and determining the format string dynamically.

    @param matrix: Matrix representation (list with n rows of m elements).
    @param header: Optional tuple or list with header elements to be displayed.
    """
    if type(header) is list:
        header = tuple(header)
    lengths = []
    if header:
        for column in header:
            lengths.append(len(column))
    for row in matrix:
        for column in row:
            i = row.index(column)
            column = str(column)
            cl = len(column)
            try:
                ml = lengths[i]
                if cl > ml:
                    lengths[i] = cl
            except IndexError:
                lengths.append(cl)

    lengths = tuple(lengths)
    format_string = ""
    for length in lengths:
        format_string += "%-" + str(length) + "s "
    format_string += "\n"

    matrix_str = ""
    if header:
        matrix_str += format_string % header
    for row in matrix:
        matrix_str += format_string % tuple(row)

    return matrix_str

if __name__ == "__main__":
    header = ("Word1", "Word2", "Word3")
    rows = [["Heeeeeeeeeeeeeey", "Hey", "Eh"],
            ["Orange", "Nonononono", "Pineapple"],
            ["Egg", "Spam", "Bacon"]]
    result = matrix_to_string(rows, header)
    print result
