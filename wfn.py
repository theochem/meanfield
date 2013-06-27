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
"""Wavefunction implementations

   The essential part of the wavefunction consists of the expansion coefficients
   in a certain basis.

   Abbreviations used in this module:

   * wfn = wavefunction
   * exp = expansion (orbitals, energies and occupations)
   * dm = density matrix
"""


import numpy as np

from horton.cache import Cache
from horton.log import log
from horton.exceptions import ElectronCountError


__all__ = [
    'setup_mean_field_wfn',
    'MeanFieldWFN', 'RestrictedWFN', 'UnrestrictedWFN',
    'AufbauOccModel', 'AufbauSpinOccModel'
]



def setup_mean_field_wfn(system, charge=0, mult=None, restricted=None):
    '''Initialize a mean-field wavefunction and assign it to the given system.

       **Arguments:**

       system
            A System instance.

       **Optional Arguments:**

       charge
            The total charge of the system. Defaults to zero.

       mult
            The spin multiplicity. Defaults to lowest possible.

       restricted
            Set to True or False to enforce a restricted or unrestricted
            wavefunction. Note that restricted open shell is not yet
            supported. When not set, restricted is used when mult==1 and
            unrestricted otherwise.

       If a wavefunction of the correct type is already present, it will be
       configured with the requested charge and multiplicity.
    '''
    if system._obasis is None:
        raise RuntimeError('A wavefunction can only be initialized when a basis is specified.')

    # Determine charge, spin, mult and restricted
    if charge is None:
        charge = 0
    nel = system.numbers.sum() - charge
    if isinstance(nel, int):
        if mult is None:
            mult = nel%2+1
        elif ((nel%2 == 0) ^ (mult%2 != 0)):
            raise ValueError('Not compatible: number of electrons = %i and spin multiplicity = %i' % (nel, mult))
    else:
        if mult is None:
            if restricted is True:
                mult = 1.0
            else:
                raise ValueError('In case of an unrestricted wfn and a fractional number of electrons, mult must be given explicitly')
    if mult < 1:
        raise ValueError('mult must be strictly positive.')
    if restricted is True and mult != 1:
        raise ValueError('Restricted==True only works when mult==1. Restricted open shell is not supported yet.')
    if restricted is None:
        restricted = mult==1

    # Show some thing on screen.
    if log.do_medium:
        log('Wavefunction initialization, without initial guess.')
        log.deflist([
            ('Charge', charge),
            ('Multiplicity', mult),
            ('Number of e', nel),
            ('Restricted', restricted),
        ])

    # Create a model for the occupation numbers
    if restricted:
        occ_model = AufbauOccModel(nel/2)
    else:
        occ_model = AufbauOccModel((nel + (mult-1))/2, (nel - (mult-1))/2)


    if system._wfn is not None:
        # Check if the existing wfn is consistent with the arguments
        if not isinstance(system.wfn, MeanFieldWFN):
            raise ValueError('A wavefunction is already present and it is not a mean-field wavefunction.')
        elif system.wfn.nbasis != system.obasis.nbasis:
            raise ValueError('The number of basis functions in the wfn is incorrect.')
        elif restricted ^ isinstance(system.wfn, RestrictedWFN):
            raise ValueError('The wfn does not match the restricted argument.')

        # Assign occ_model
        system.wfn.occ_model = occ_model

        # If the wfn contains an expansion, update the occupations and remove density matrices. Otherwise clean up
        if 'exp_alpha' in system.wfn._cache:
            if restricted:
                system.wfn.occ_model.assign(system.wfn.exp_alpha)
            else:
                system.wfn.occ_model.assign(system.wfn.exp_alpha, system.wfn.exp_beta)
            for select in 'alpha', 'beta', 'full', 'spin':
                system.wfn._cache.clear_item('dm_%s' % select)
        else:
            system.wfn.invalidate()
    else:
        # if the wfn does not exist yet, create a proper one.
        if restricted:
            system._wfn = RestrictedWFN(occ_model, system.lf, system.obasis.nbasis)
        else:
            system._wfn = UnrestrictedWFN(occ_model, system.lf, system.obasis.nbasis)


class PropertyHelper(object):
    '''Auxiliary class to set up dm_xxx and exp_xxx attributes of MeanFieldWFN class.'''
    def __init__(self, method, arg):
        self.method = method
        self.arg = arg

    def __get__(self, obj, objtype):
        try:
            return self.method(obj, self.arg)
        except KeyError, e:
            raise AttributeError('The requested attribute (%s) is not available.' % e.args[0])



class MeanFieldWFN(object):
    def __init__(self, occ_model, lf, nbasis, norb=None):
        """
           **Arguments:**

           occ_model
                A model for the occupation numbers to be assigned after
                diagonalization of the Fock matrix.

           lf
                A LinalgFactory instance.

           nbasis
                The number of basis functions.

           **Optional arguments:**

           norb
               the number of orbitals (occupied + virtual). When not given,
               it is set to nbasis.
        """
        self._lf = lf
        self._nbasis = nbasis
        self.occ_model = occ_model
        if norb is None:
            self._norb = nbasis
        else:
            self._norb = norb
        # The cache is used to store different representations of the
        # wavefunction, i.e. as expansion, as density matrix or both.
        self._cache = Cache()
        # Write some screen log
        self._log_init()

    @classmethod
    def from_hdf5(cls, grp, lf):
        # make the wfn object
        from horton.checkpoint import load_hdf5_low
        occ_model = load_hdf5_low(grp['occ_model'], lf)
        result = cls(occ_model, lf, nbasis=grp['nbasis'][()], norb=grp['norb'][()])
        # load stuff into cache
        for spin in 'alpha', 'beta':
            if 'exp_%s' % spin in grp:
                exp = result.init_exp(spin)
                exp.read_from_hdf5(grp['exp_%s' % spin])
            if 'dm_%s' % spin in grp:
                dm = result.init_dm(spin)
                dm.read_from_hdf5(grp['dm_%s' % spin])
        return result

    def to_hdf5(self, grp):
        grp.attrs['class'] = self.__class__.__name__
        grp['nbasis'] = self._nbasis
        grp['norb'] = self._norb
        tmp = grp.create_group('occ_model')
        self.occ_model.to_hdf5(tmp)
        for spin in 'alpha', 'beta':
            if 'exp_%s' % spin in self._cache:
                tmp = grp.create_group('exp_%s' % spin)
                self._cache.load('exp_%s' % spin).to_hdf5(tmp)
            if 'dm_%s' % spin in self._cache:
                tmp = grp.create_group('dm_%s' % spin)
                self._cache.load('dm_%s' % spin).to_hdf5(tmp)

    def _get_nbasis(self):
        '''The number of basis functions.'''
        return self._nbasis

    nbasis = property(_get_nbasis)

    def _get_norb(self):
        '''The number of orbitals in the expansion(s)'''
        return self._norb

    norb = property(_get_norb)

    def _log_init(self):
        '''Write a summary of the wavefunction to the screen logger'''
        if log.do_medium:
            log('Initialized: %s' % self)
            self.occ_model.log()

    def _iter_expansions(self):
        '''Iterate over all expansion in the cache'''
        for spin in 'alpha', 'beta':
            if 'exp_%s' % spin in self._cache:
                yield self._cache.load('exp_%s' % spin)

    def _iter_density_matrices(self):
        '''Iterate over all density matrices in the cache'''
        for select in 'alpha', 'beta', 'full', 'spin':
            if 'dm_%s' % select in self._cache:
                yield self._cache.load('dm_%s' % select)

    def _assign_dm_full(self, dm):
        raise NotImplementedError

    def _assign_dm_spin(self, dm):
        raise NotImplementedError

    def invalidate(self):
        '''Must be called when the wavefunction is outdated'''
        self._cache.clear()

    def init_exp(self, spin):
        if spin not in ['alpha', 'beta']:
            raise ValueError('The select argument must be alpha or beta')
        exp, new = self._cache.load('exp_%s' % spin, alloc=(self._lf, 'expansion', self._nbasis, self._norb))
        if not new:
            raise RuntimeError('The expansion exp_%s already exists. Call wfn.invalidate prior to updating the wfn.' % spin)
        return exp

    def init_dm(self, select):
        if select not in ['alpha', 'beta', 'full', 'spin']:
            raise ValueError('The select argument must be one of alpha, beta, full or spin.')
        dm, new = self._cache.load('dm_%s' % select, alloc=(self._lf, 'one_body', self.nbasis))
        if not new:
            raise RuntimeError('The density matrix dm_%s already exists. Call wfn.invalidate prior to updating the wfn.' % select)
        return dm

    def update_dm(self, select, dm=None):
        """Derive the density matrix from the expansion(s) and store in cache

           **Optional arguments:**

           select
                'alpha', 'beta', 'full' or 'spin'.
        """
        cached_dm = self.init_dm(select)
        if dm is None:
            if select == 'alpha':
                exp_alpha = self._cache.load('exp_alpha')
                exp_alpha.compute_density_matrix(cached_dm)
            elif select == 'beta':
                exp_beta = self._cache.load('exp_beta')
                exp_beta.compute_density_matrix(cached_dm)
            elif select == 'full':
                self._assign_dm_full(cached_dm)
            elif select == 'spin':
                self._assign_dm_spin(cached_dm)
        else:
            cached_dm.assign(dm)
        return cached_dm

    def get_dm(self, select):
        '''Get a density matrix. If not available, it will be created (if possible)

           select
                'alpha', 'beta', 'full' or 'spin'.
        '''
        if not 'dm_%s' % select in self._cache:
            self.update_dm(select)
        return self._cache.load('dm_%s' % select)

    def get_exp(self, spin):
        '''Return an expansion of the wavefunction, if available.

           **Optional arguments:**

           select
                the spin component: 'alpha' or 'beta'.
        '''
        return self._cache.load('exp_%s' % spin)

    dm_alpha = PropertyHelper(get_dm, 'alpha')
    dm_beta = PropertyHelper(get_dm, 'beta')
    dm_full = PropertyHelper(get_dm, 'full')
    dm_spin = PropertyHelper(get_dm, 'spin')
    exp_alpha = PropertyHelper(get_exp, 'alpha')
    exp_beta = PropertyHelper(get_exp, 'beta')

    def apply_basis_permutation(self, permutation):
        """Reorder the expansion coefficients and the density matrices"""
        for exp in self._iter_expansions():
            exp.apply_basis_permutation(permutation)
        for dm in self._iter_density_matrices():
            dm.apply_basis_permutation(permutation)

    def apply_basis_signs(self, signs):
        """Fix the signs of the expansion coefficients and the density matrices"""
        for exp in self._iter_expansions():
            exp.apply_basis_signs(signs)
        for dm in self._iter_density_matrices():
            dm.apply_basis_signs(signs)

    def check_normalization(self, olp, eps=1e-4):
        '''Run an internal test to see if the orbitals are normalized

           **Arguments:**

           olp
                The overlap one_body operators

           **Optional arguments:**

           eps
                The allowed deviation from unity, very loose by default.
        '''
        for exp in self._iter_expansions():
            exp.check_normalization(olp, eps)


class RestrictedWFN(MeanFieldWFN):
    def _assign_dm_full(self, dm):
        dm.assign(self.dm_alpha)
        dm.iscale(2)

    def _assign_dm_spin(self, dm):
        dm.reset()

    def update_exp(self, fock_alpha, overlap, dm_alpha=None):
        '''Update the expansion based on the given fock matrix

           **Arguments:**

           fock_alpha
                A DenseOneBody object with the Fock operator

           overlap
                A DenseOneBody object with the overlap operator

           ***Optional arguments:**

           dm_alpha
                A DenseOneBody object with the density matrix

        '''
        # Load the orbital expansion of the alpha density.
        exp_alpha = self.init_exp('alpha')
        if dm_alpha is None:
            # Diagonalize the Fock matrix and
            # use simple rules to derive the occupations
            exp_alpha.derive_from_fock_matrix(fock_alpha, overlap)
            self.occ_model.assign(exp_alpha)
        else:
            # Diagonalize the Fock matrix and
            # use the density matrix to derive the occupations
            cached_dm_alpha = self.init_dm('alpha')
            cached_dm_alpha.assign(dm_alpha)
            exp_alpha.derive_from_density_and_fock_matrix(dm_alpha, fock_alpha, overlap)
        return exp_alpha

    def _get_nel(self):
        return self.nep*2

    nel = property(_get_nel)

    def _get_nep(self):
        if 'exp_alpha' in self._cache:
            return self._cache.load('exp_alpha').occupations.sum()
        else:
            raise NotImplementedError

    nep = property(_get_nep)

    def _get_mult(self):
        return 1.0

    mult = property(_get_mult)

    def get_spin(self):
        '''Returns the expectation values of the projecte and squared spin'''
        return 0.0, 0.0

    def _get_homo_energy(self):
        '''The HOMO of the wavefunction'''
        return self.exp_alpha.get_homo_energy()

    homo_energy = property(_get_homo_energy)

    def _get_lumo_energy(self):
        '''The LUMO of the wavefunction'''
        return self.exp_alpha.get_lumo_energy()

    lumo_energy = property(_get_lumo_energy)



class UnrestrictedWFN(MeanFieldWFN):
    def _assign_dm_full(self, dm):
        dm.assign(self.dm_alpha)
        dm.iadd(self.dm_beta)

    def _assign_dm_spin(self, dm):
        dm.assign(self.dm_alpha)
        dm.iadd(self.dm_beta, factor=-1)

    def update_exp(self, fock_alpha, fock_beta, overlap, dm_alpha=None, dm_beta=None):
        '''Update the expansion based on the given fock matrix

           **Arguments:**

           fock_alpha, fock_beta
                DenseOneBody objects with the Fock operators

           overlap
                A DenseOneBody object with the overlap operator

           ***Optional arguments:**

           dm_alpha, dm_beta
                DenseOneBody objects with the density matrices
        '''
        if ((dm_alpha is None) ^ (dm_beta is None)):
            raise ValueError('Either no or both density matrices must be given')

        # Load the orbital expansions.
        exp_alpha = self.init_exp('alpha')
        exp_beta = self.init_exp('beta')
        if dm_alpha is None:
            # Diagonalize the Fock matrix and
            # use simple rules to derive the occupations
            exp_alpha.derive_from_fock_matrix(fock_alpha, overlap)
            if fock_alpha is fock_beta:
                # take a shortcut
                exp_beta.assign(exp_alpha)
            else:
                exp_beta.derive_from_fock_matrix(fock_beta, overlap)
            self.occ_model.assign(exp_alpha, exp_beta)
        else:
            # Diagonalize the Fock matrix and
            # use the density matrix to derive the occupations
            #   alpha
            cached_dm_alpha = self.init_dm('alpha')
            cached_dm_alpha.assign(dm_alpha)
            exp_alpha.derive_from_density_and_fock_matrix(dm_alpha, fock_alpha, overlap)
            #   beta
            cached_dm_beta = self.init_dm('beta')
            cached_dm_beta.assign(dm_beta)
            exp_beta.derive_from_density_and_fock_matrix(dm_beta, fock_beta, overlap)
        return exp_alpha, exp_beta

    def _get_nel(self):
        return self.nalpha + self.nbeta

    nel = property(_get_nel)

    def _get_nalpha(self):
        if 'exp_alpha' in self._cache:
            return self._cache.load('exp_alpha').occupations.sum()
        else:
            raise NotImplementedError

    nalpha = property(_get_nalpha)

    def _get_nbeta(self):
        if 'exp_beta' in self._cache:
            return self._cache.load('exp_beta').occupations.sum()
        else:
            raise NotImplementedError

    nbeta = property(_get_nbeta)

    def _get_mult(self):
        return 1 + abs(self.nalpha - self.nbeta)

    mult = property(_get_mult)

    def get_spin(self, olp):
        '''Returns the expectation values of the projected and squared spin

           **Arguments:**

           olp
                The overlap matrix
        '''
        nbeta = self.nbeta
        sz = (self.nalpha - nbeta)/2

        # The correction due to the mismatch in overlap between alpha and beta
        # orbitals.
        correction = 0.0
        nfn_alpha = self.exp_alpha.nfn
        nfn_beta = self.exp_beta.nfn
        occupations_alpha = self.exp_alpha.occupations
        occupations_beta = self.exp_beta.occupations
        coeffs_alpha = self.exp_alpha.coeffs
        coeffs_beta = self.exp_beta.coeffs
        for ialpha in xrange(nfn_alpha):
            if occupations_alpha[ialpha] == 0.0:
                continue
            for ibeta in xrange(nfn_beta):
                if occupations_beta[ibeta] == 0.0:
                    continue
                correction += olp.dot(coeffs_alpha[:,ialpha], coeffs_beta[:,ibeta])**2

        ssq = sz*(sz+1) + nbeta - correction
        return sz, ssq

    def _get_homo_energy(self):
        '''The HOMO of the wavefunction'''
        return max(self.exp_alpha.get_homo_energy(), self.exp_beta.get_homo_energy())

    homo_energy = property(_get_homo_energy)

    def _get_lumo_energy(self):
        '''The LUMO of the wavefunction'''
        es = [self.exp_alpha.get_lumo_energy(), self.exp_beta.get_lumo_energy()]
        es = [e for e in es if e is not None]
        if len(es) > 0:
            return min(es)

    lumo_energy = property(_get_lumo_energy)


class AufbauOccModel(object):
    def __init__(self, nalpha, nbeta=None):
        if nbeta is None:
            nbeta = nalpha

        if nalpha < 0 or nbeta < 0:
            raise ElectronCountError('Negative number of electrons is not allowed.')
        if nalpha == 0 and nbeta == 0:
            raise ElectronCountError('At least one alpha or beta electron is required.')

        self.nalpha = nalpha
        self.nbeta = nbeta

    @classmethod
    def from_hdf5(cls, grp, lf):
        return cls(grp['nalpha'][()], grp['nbeta'][()])

    def to_hdf5(self, grp):
        grp.attrs['class'] = self.__class__.__name__
        grp['nalpha'] = self.nalpha
        grp['nbeta'] = self.nbeta

    def assign(self, exp_alpha, exp_beta=None):
        '''Assign occupation numbers to the expansion objects

           **Arguments:**

           exp_alpha
                An alpha DenseExpansion object

           **Optional arguments:**

           exp_beta
                A beta DenseExpansion object
        '''
        exps = [(exp_alpha, self.nalpha)]
        if exp_beta is not None:
            exps.append((exp_beta, self.nbeta))
        for exp, nocc in exps:
            nfn = len(exp.energies)
            assert nfn == len(exp.occupations)
            if nfn < nocc:
                raise ElectronCountError('The number of orbitals must not be lower than the number of alpha or beta electrons.')
            assert (exp.energies[1:] >= exp.energies[:-1]).all()
            if nocc == int(nocc):
                exp.occupations[:nocc] = 1.0
                exp.occupations[nocc:] = 0.0
            else:
                exp.occupations[:int(np.floor(nocc))] = 1.0
                exp.occupations[int(np.floor(nocc))] = nocc - np.floor(nocc)
                exp.occupations[int(np.ceil(nocc)):] = 0.0

    def log(self):
        log('Occupation model: %s' % self)
        log.deflist([('nalpha', self.nalpha), ('nbeta', self.nbeta)])


class AufbauSpinOccModel(object):
    '''This Aufbau model only applies to unrestricted wavefunctions'''
    def __init__(self, nel):
        if nel <= 0:
            raise ElectronCountError('The number of electron must be positive.')

        self.nel = nel

    @classmethod
    def from_hdf5(cls, grp, lf):
        return cls(grp['nel'][()])

    def to_hdf5(self, grp):
        grp.attrs['class'] = self.__class__.__name__
        grp['nel'] = self.nel

    def assign(self, exp_alpha, exp_beta):
        '''Assign occupation numbers to the expansion objects

           **Arguments:**

           exp_alpha, exp_beta
                Alpha and beta DenseExpansion object
        '''
        nel = self.nel
        ialpha = 0
        ibeta = 0
        while nel > 0:
            if exp_alpha.energies[ialpha] <= exp_beta.energies[ibeta]:
                exp_alpha.occupations[ialpha] = 1.0
                ialpha += 1
            else:
                exp_beta.occupations[ibeta] = 1.0
                ibeta += 1
            nel -= 1
        #print 'AufbauSpinOccModel', ialpha, ibeta

    def log(self):
        log('Occupation model: %s' % self)
        log.deflist([('nel', self.nbeta)])
