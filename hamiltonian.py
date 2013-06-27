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

from horton.log import log, timer
from horton.cache import Cache
from horton.meanfield.core import KineticEnergy, ExternalPotential
from horton.meanfield.builtin import Hartree


__all__ = [
    'Hamiltonian',
]


class Hamiltonian(object):
    def __init__(self, system, terms, grid=None, auto_complete=True):
        '''
           **Arguments:**

           system
                The System object for which the energy must be computed.

           terms
                The terms in the Hamiltonian. Kinetic energy, external
                potential (nuclei), and Hartree are added automatically.

           **Optional arguments:**

           grid
                The integration grid, in case some terms need one.

           auto_complete
                When set to False, the kinetic energy, external potential and
                Hartree terms are not added automatically.
        '''
        # check arguments:
        if len(terms) == 0:
            raise ValueError('At least one term must be present in the Hamiltonian.')
        for term in terms:
            if term.require_grid and grid is None:
                raise TypeError('The term %s requires a grid, but not grid is given.' % term)

        # Assign attributes
        self.system = system
        self.terms = list(terms)
        self.grid = grid

        if auto_complete:
            # Add standard terms if missing
            #  1) Kinetic energy
            if sum(isinstance(term, KineticEnergy) for term in terms) == 0:
                self.terms.append(KineticEnergy())
            #  2) Hartree (or HatreeFock, which is a subclass of Hartree)
            if sum(isinstance(term, Hartree) for term in terms) == 0:
                self.terms.append(Hartree())
            #  3) External Potential
            if sum(isinstance(term, ExternalPotential) for term in terms) == 0:
                self.terms.append(ExternalPotential())

        # Create a cache for shared intermediate results.
        self.cache = Cache()

        with timer.section('Prep. Ham.'):
            # Pre-compute stuff
            for term in self.terms:
                term.prepare_system(self.system, self.cache, self.grid)

            # Compute overlap matrix
            self.overlap = system.get_overlap()

    def invalidate(self):
        '''Mark the properties derived from the wfn as outdated.

           This method does not recompute anything, but just marks operators
           as outdated. They are recomputed as they are needed.
        '''
        self.cache.invalidate_all()

    def compute_energy(self):
        '''Compute energy.

           **Returns:**

           The total energy, including nuclear-nuclear repulsion.
        '''
        if log.do_high:
            log('Computing the energy of the system.')
            log.hline()
            log('                   Energy term                 Value')
            log.hline()

        total = 0.0
        for term in self.terms:
            total += term.compute_energy()

        energy = self.system.compute_nucnuc()
        total += energy
        # Store result in chk file
        self.system._props['energy'] = total
        self.system.update_chk('props')

        if log.do_high:
            log('%30s  %20.10f' % ('nn', energy))
            log('%30s  %20.10f' % ('total', total))
            log.hline()

        return total

    def compute_fock(self, fock_alpha, fock_beta):
        '''Compute alpha (and beta) Fock matrix(es).

           **Arguments:**

           fock_alpha
                A One-Body operator output argument for the alpha fock matrix.

           fock_alpha
                A One-Body operator output argument for the beta fock matrix.

           In the case of a closed-shell computation, the argument fock_beta is
           ``None``.
        '''
        for term in self.terms:
            term.add_fock_matrix(fock_alpha, fock_beta)
