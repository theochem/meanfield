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
'''Mean-field DFT/HF Hamiltonian data structures'''


from horton.log import log
from horton.cache import Cache
from horton.meanfield.core import KineticEnergy, ExternalPotential
from horton.meanfield.builtin import Hartree
from horton.meanfield.wfn import UnrestrictedWFN


__all__ = [
    'Hamiltonian',
]


class Hamiltonian(object):
    def __init__(self, system, scf_cache, terms, grid=None, idiot_proof=True):
        '''
           **Arguments:**

           system
                The System object for which the energy must be computed.

           terms
                The terms in the Hamiltonian.

           **Optional arguments:**

           grid
                The integration grid, in case some terms need one.

           idiot_proof
                When set to False, the kinetic energy, external potential and
                Hartree terms are not added automatically and a error is raised
                when no exchange is present.
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

        if idiot_proof:
            # Check if an exchange term is present
            if not any(term.exchange for term in self.terms):
                raise ValueError('No exchange term is given and idiot_proof option is set to True.')
            # Add standard terms if missing
            #  1) Kinetic energy
            if sum(isinstance(term, KineticEnergy) for term in terms) == 0:
                self.terms.append(KineticEnergy(system.obasis, system.cache,
                                                system.lf, system.wfn)
                                  )
            #  2) Hartree (or HatreeFock, which is a subclass of Hartree)
            if sum(isinstance(term, Hartree) for term in terms) == 0:
                self.terms.append(Hartree(scf_cache, system.lf, system.wfn,
                                           system.get_electron_repulsion()))
            #  3) External Potential
            if sum(isinstance(term, ExternalPotential) for term in terms) == 0:
                self.terms.append(ExternalPotential(system.obasis, system.cache,
                                                    system.lf, system.wfn,
                                                    system.numbers,
                                                    system.coordinates)
                                  )


        # Create a cache for shared intermediate results. This cache should only
        # be used for derived quantities that depend on the wavefunction and
        # need to be updated at each SCF cycle.
        self.cache = scf_cache

        # bind the terms to this hamiltonian such that certain shared
        # intermediated results can be reused for the sake of efficiency.
        for term in self.terms:
            term.set_hamiltonian(self)

    def add_term(self, term):
        '''Add a new term to the hamiltonian'''
        self.terms.append(term)
        term.set_hamiltonian(self)

    def clear(self):
        '''Mark the properties derived from the wfn as outdated.

           This method does not recompute anything, but just marks operators
           as outdated. They are recomputed as they are needed.
        '''
        self.cache.clear()

    def compute(self):
        '''Compute the energy.

           **Returns:**

           The total energy, including nuclear-nuclear repulsion.
        '''
        total = 0.0
        for term in self.terms:
            energy = term.compute()
            self.system.extra['energy_%s' % term.label] = energy
            total += energy
        energy = self.system.compute_nucnuc()
        self.system.extra['energy_nn'] = energy
        total += energy
        self.system.extra['energy'] = total
        return total

    def log_energy(self):
        '''Write an overview of the last energy computation on screen'''
        log('Contributions to the energy:')
        log.hline()
        log('                                       Energy term                 Value')
        log.hline()
        for term in self.terms:
            energy = self.system.extra['energy_%s' % term.label]
            log('%50s  %20.12f' % (term.label, energy))
        log('%50s  %20.12f' % ('nn', self.system.extra['energy_nn']))
        log('%50s  %20.12f' % ('total', self.system.extra['energy']))
        log.hline()
        log.blank()

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
        # Loop over all terms and add contributions to the Fock matrix. Some
        # terms will actually only evaluate potentials on grids and add these
        # results to the total potential on a grid.
        for term in self.terms:
            term.add_fock_matrix(fock_alpha, fock_beta, postpone_grid=True)
        # Collect all the total potentials and turn them into contributions
        # for the fock matrix/matrices.

        # Collect potentials for alpha electrons
        # d = density
        if 'dpot_total_alpha' in self.cache:
            dpot = self.cache.load('dpot_total_alpha')
            self.system.compute_grid_density_fock(self.grid.points, self.grid.weights, dpot, fock_alpha)
        # g = gradient
        if 'gpot_total_alpha' in self.cache:
            gpot = self.cache.load('gpot_total_alpha')
            self.system.compute_grid_gradient_fock(self.grid.points, self.grid.weights, gpot, fock_alpha)

        if isinstance(self.system.wfn, UnrestrictedWFN):
            # Colect potentials for beta electrons
            # d = density
            if 'dpot_total_beta' in self.cache:
                dpot = self.cache.load('dpot_total_beta')
                self.system.compute_grid_density_fock(self.grid.points, self.grid.weights, dpot, fock_beta)
            # g = gradient
            if 'gpot_total_beta' in self.cache:
                gpot = self.cache.load('gpot_total_beta')
                self.system.compute_grid_gradient_fock(self.grid.points, self.grid.weights, gpot, fock_beta)
