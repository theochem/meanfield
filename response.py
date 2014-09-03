# -*- coding: utf-8 -*-
# Horton is a development platform for electronic structure methods.
# Copyright (C) 2011-2013 Toon Verstraelen <Toon.Verstraelen@UGent.be>
#
# This file is part of Horton.
#
# Horton is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# Horton is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>
#
#--


import numpy as np

from horton.log import timer


__all__ = ['compute_noninteracting_response']


@timer.with_section('KS Response')
def compute_noninteracting_response(exp, operators, work=None):
    '''Compute the non-interacting response matrix for a given orbital expansion

       **Arguments:**

       exp
            An instance of DenseExpansion.

       operators
            A list of one-body operators.

       **Optional arguments:**

       work
            A work array with shape (len(operators), nfn, nfn), where nfn is
            the number of occupied and virtual orbitals.

       **Returns:** a symmetric matrix where each element corresponds to a pair
       of operators.
    '''
    # Convert the operators to the orbital basis
    coeffs = exp.coeffs
    norb = exp.nfn
    nop = len(operators)

    if work is None:
        work = np.zeros((nop, norb, norb))
    for iop in xrange(nop):
        work[iop] = np.dot(coeffs.T, np.dot(operators[iop]._array, coeffs))

    # Put the orbital energies and the occupations in a convenient array
    energies = exp.energies
    occupations = exp.occupations
    with np.errstate(invalid='ignore'):
        prefacs = np.subtract.outer(occupations, occupations)/np.subtract.outer(energies, energies)
    for iorb in xrange(norb):
        prefacs[iorb,iorb] = 0.0

    # Double loop over all pairs for operators. The diagonal element is computed
    # as a double check
    result = np.zeros((nop, nop), float)
    for iop0 in xrange(nop):
        for iop1 in xrange(iop0+1):
            # evaluate the sum over states expression
            state_sum = (work[iop0]*work[iop1]*prefacs).sum()

            # store the state sum
            result[iop0, iop1] = state_sum
            result[iop1, iop0] = state_sum

    return result
