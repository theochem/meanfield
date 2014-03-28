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
'''Linear energy terms (Core Hamiltonian)'''


from horton.matrix import OneBody
from horton.meanfield.observable import Observable
from horton.meanfield.wfn import RestrictedWFN


__all__ = ['LinearObservable', 'CustomLinearObservable']


class LinearObservable(Observable):
    '''Abstract base class for all observables that are linear in the
       density matrix

       This is (technically) a special class because the Fock operator does not
       have to be recomputed when the density matrix changes. However, it must
       be recomputed when the basis set (and geometry) changes.

       A restriction of this implementation is that the fock operator for the
       alpha and the beta electrons are the same.
    '''
    def __init__(self, obasis, lf, wfn, label):
        self._obasis = obasis
        self._wfn = wfn
        Observable.__init__(self, lf, label)

    def get_operator(self):
        # subclasses should override this method such that it
        # returns the operator.
        raise NotImplementedError

    def compute(self):
        '''See Observable.compute'''
        operator = self.get_operator()
        if isinstance(self._wfn, RestrictedWFN):
            return 2 * operator.expectation_value(self._wfn.dm_alpha)
        else:
            return operator.expectation_value(self._wfn.dm_full)

    def add_fock_matrix(self, fock_alpha, fock_beta, scale=1,
                        postpone_grid=False):
        '''See Observable.add_fock_matrix'''
        operator = self.get_operator()
        for fock in fock_alpha, fock_beta:
            if fock is not None:
                fock.iadd(operator, scale)



class CustomLinearObservable(LinearObservable):
    '''This is a user-defined observable that is linear in the density matrix

       This term can be used to implemented custom perturbations by
       finite fields.
    '''
    def __init__(self, obasis, lf, wfn, label, operator):
        '''
           **Arguments:**

           operator
                A OneBody object.
        '''
        self._operator = operator
        LinearObservable.__init__(self, obasis, lf, wfn, label)

    def get_operator(self):
        return self._operator
