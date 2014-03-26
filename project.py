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
'''Projection of 1-electron orbitals to a new basis set'''


import numpy as np
from horton.log import log
from horton.matrix import DenseLinalgFactory
from horton.gbasis.cext import GOBasis
from horton.meanfield.wfn import RestrictedWFN, UnrestrictedWFN


__all__ = ['ProjectionError', 'project_orbitals_mgs', 'project_orbitals_mgs_low']


class ProjectionError(Exception):
    pass


def project_orbitals_mgs(obasis, wfn, old_wfn, old_obasis, eps=1e-10):
    '''Project orbitals from the ``old_wfn`` (wrt ``old_basis``) on the wfn of the ``system`` object with the modified Gram-Schmidt algorithm.

       **Arguments:**

       system
            The system with the new orbital basis. It must have a
            wavefunction object compatible with the old wavefunction (restricted
            versus unrestricted).

       old_wfn
            The old (mean-field) wavefunction object

       old_obasis
            The orbital basis for the old wavefunction

       **Optional arguments:**

       eps
            A threshold for the renormalization in the Gram-Schmidt procedure.

       See ``project_orbitals_mgs_low`` for details.
    '''
    if log.do_medium:
        log('Projecting the wavefunction on a new basis.')
        log.blank()
    if isinstance(old_wfn, RestrictedWFN):
        assert isinstance(wfn, RestrictedWFN)
        if 'exp_alpha' not in wfn._cache:
            wfn.init_exp('alpha')
        project_orbitals_mgs_low(old_obasis, obasis, old_wfn.exp_alpha, wfn.exp_alpha, eps)
    else:
        assert isinstance(wfn, UnrestrictedWFN)
        if 'exp_alpha' not in wfn._cache:
            wfn.init_exp('alpha')
            wfn.init_exp('beta')
        project_orbitals_mgs_low(old_obasis, obasis, old_wfn.exp_alpha, wfn.exp_alpha, eps)
        project_orbitals_mgs_low(old_obasis, obasis, old_wfn.exp_beta, wfn.exp_beta, eps)
    wfn.clear_dm()


def project_orbitals_mgs_low(obasis0, obasis1, exp0, exp1, eps=1e-10):
    '''Project the orbitals in ``exp0`` (wrt ``obasis0``) on ``obasis1`` and store in ``exp1`` with the modified Gram-Schmidt algorithm.

       **Arguments:**

       obasis0
            The orbital basis for the original wavefunction expansion.

       obasis1
            The new orbital basis for the projected wavefunction expansion.

       exp0
            The expansion of the original orbitals.

       exp1 (output)
            An output argument in which the projected orbitals will be stored.

       **Optional arguments:**

       eps
            A threshold for the renormalization in the Gram-Schmidt procedure

       The projection is based on the Modified Gram-Schmidt (MGS) process. In
       each iteration of the MGS, a renormalization is carried out. If the norm
       in this step is smaller than ``eps``, an error is raised.

       Note that ``exp1`` will be incomplete in several ways. The orbital
       energies are not copied. Only the occupied orbitals in ``exp0`` are
       projected. Coefficients of higher orbitals are set to zero. The orbital
       occupations are simply copied. This should be sufficient to construct
       an initial guess in a new orbital basis set based on a previous solution.

       If the number of orbitals in ``exp1`` is too small to store all projected
       orbitals, an error is raised.
    '''
    # Compute the overlap matrix of the combined orbital basis
    obasis_both = GOBasis.concatenate(obasis0, obasis1)
    lf = DenseLinalgFactory(obasis_both.nbasis)
    olp_both = lf.create_one_body()
    obasis_both.compute_overlap(olp_both)

    # Select the blocks of interest from the big overlap matrix
    olp_21 = olp_both._array[obasis0.nbasis:, :obasis0.nbasis]
    olp_22 = olp_both._array[obasis0.nbasis:, obasis0.nbasis:]

    # construct the projector
    projector = np.dot(np.linalg.pinv(olp_22), olp_21)

    # project occupied orbitals
    i1 = 0
    for i0 in xrange(exp0.nfn):
        if exp0.occupations[i0] == 0.0:
            continue
        if i1 > exp1.nfn:
            raise ProjectionError('Not enough functions available in exp1 to store the projected orbitals.')
        exp1.coeffs[:,i1] = np.dot(projector, exp0.coeffs[:,i0])
        exp1.occupations[i1] = exp0.occupations[i0]
        i1 += 1

    # clear all parts of exp1 that were not touched by the projection loop
    ntrans = i1
    del i1
    exp1.coeffs[:,ntrans:] = 0.0
    exp1.occupations[ntrans:] = 0.0
    exp1.energies[:] = 0.0

    # auxiliary function for the MGS algo
    def dot22(a, b):
        return np.dot(np.dot(a, olp_22), b)

    # Apply the MGS algorithm to orthogonalize the orbitals
    for i1 in xrange(ntrans):
        orb = exp1.coeffs[:,i1]

        # Subtract overlap with previous orbitals
        for j1 in xrange(i1):
            other = exp1.coeffs[:,j1]
            orb -= other*dot22(other, orb)/np.sqrt(dot22(orb, orb))

        # Renormalize
        norm = np.sqrt(dot22(orb, orb))
        if norm < eps:
            raise ProjectionError('The norm of a vector in the MGS algorithm becomes too small. Orbitals are redundant in new basis.')
        orb /= norm
