# -*- coding: utf-8 -*-
# HORTON: Helpful Open-source Research TOol for N-fermion systems.
# Copyright (C) 2011-2016 The HORTON Development Team
#
# This file is part of HORTON.
#
# HORTON is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# HORTON is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>
#
# --
"""Base classes for energy terms and other observables of the wavefunction"""

from horton.utils import doc_inherit


__all__ = [
    'compute_dm_full',
    'Observable',
    'RTwoIndexTerm', 'UTwoIndexTerm',
    'RDirectTerm', 'UDirectTerm',
    'RExchangeTerm', 'UExchangeTerm',
]


def compute_dm_full(cache):
    """Add the spin-summed density matrix to the cache unless it is already present."""
    dm_alpha = cache['dm_alpha']
    dm_beta = cache['dm_beta']
    dm_full, new = cache.load('dm_full', alloc=dm_alpha.new)
    if new:
        dm_full.assign(dm_alpha)
        dm_full.iadd(dm_beta)
    return dm_full


class Observable(object):
    """Base class for contribution to EffHam classes.

    These are usually energy expressions (as function of one or more density matrices).
    One may also add in other observables, e.g. to construct a Lagrangian instead of a
    Hessian.
    """
    def __init__(self, label):
        """Initialize an Observable instance.

        Parameters
        ----------
        label : str
            A short string to identify the observable.
        """
        self.label = label

    def compute_energy(self, cache):
        """Compute the expectation value of the observable.

        Parameters
        ----------
        cache : Cache
            Used to store intermediate results that can be reused or inspected later.
        """
        raise NotImplementedError

    def add_fock(self, cache, *focks):
        """Add contributions to the Fock matrices.

        Parameters
        ----------
        cache : Cache
            Used to store intermediate results that can be reused or inspected later.
        fock1, fock2, ... : TwoIndex
            A list of output fock operators. The caller is responsible for setting these
            operators initially to zero (if desired).
        """
        raise NotImplementedError

        raise NotImplementedError


class RTwoIndexTerm(Observable):
    """Observable linear in the density matrix (restricted)."""

    def __init__(self, op_alpha, label):
        """Initialize a RTwoIndexTerm instance.

        Parameters
        ----------
        op_alpha : TwoIndex
            Expansion of one-body operator in basis of alpha orbitals. Same is used for
            beta.
        label : str
            A short string to identify the observable.
        """
        self.op_alpha = op_alpha
        Observable.__init__(self, label)

    @doc_inherit(Observable)
    def compute_energy(self, cache):
        return 2 * self.op_alpha.contract_two('ab,ab', cache['dm_alpha'])

    @doc_inherit(Observable)
    def add_fock(self, cache, fock_alpha):
        fock_alpha.iadd(self.op_alpha)


class UTwoIndexTerm(Observable):
    """Observable linear in the density matrix (unrestricted)."""

    def __init__(self, op_alpha, label, op_beta=None):
        """Initialize a RTwoIndexTerm instance.

        Parameters
        ----------
        op_alpha : TwoIndex
            Expansion of one-body operator in basis of alpha orbitals.
        label : str
            A short string to identify the observable.
        op_beta : TwoIndex
            Expansion of one-body operator in basis of beta orbitals. When not given,
            op_alpha is used.
        """
        self.op_alpha = op_alpha
        self.op_beta = op_alpha if op_beta is None else op_beta
        Observable.__init__(self, label)

    @doc_inherit(Observable)
    def compute_energy(self, cache):
        if self.op_alpha is self.op_beta:
            # when both operators are references to the same object, take a
            # shortcut
            compute_dm_full(cache)
            return self.op_alpha.contract_two('ab,ab', cache['dm_full'])
        else:
            # If the operator is different for different spins, do the normal
            # thing.
            return self.op_alpha.contract_two('ab,ab', cache['dm_alpha']) + \
                   self.op_beta.contract_two('ab,ab', cache['dm_beta'])

    @doc_inherit(Observable)
    def add_fock(self, cache, fock_alpha, fock_beta):
        fock_alpha.iadd(self.op_alpha)
        fock_beta.iadd(self.op_beta)


class RDirectTerm(Observable):
    """Direct term of the expectation value of a two-body operator (restricted)."""

    def __init__(self, op_alpha, label):
        """Initialize a RDirectTerm instance.

        Parameters
        ----------
        op_alpha : FourIndex
            Expansion of two-body operator in basis of alpha orbitals. Same is used for
            beta orbitals.
        label : str
            A short string to identify the observable.
        """
        self.op_alpha = op_alpha
        Observable.__init__(self, label)

    def _update_direct(self, cache):
        """Recompute the direct operator if it has become invalid.

        Parameters
        ----------
        cache : Cache
            Used to store intermediate results that can be reused or inspected later.
        """
        dm_alpha = cache['dm_alpha']
        direct, new = cache.load('op_%s_alpha' % self.label, alloc=dm_alpha.new)
        if new:
            self.op_alpha.contract_two_to_two('abcd,bd->ac', dm_alpha, direct)
            direct.iscale(2) # contribution from beta electrons is identical

    @doc_inherit(Observable)
    def compute_energy(self, cache):
        self._update_direct(cache)
        direct = cache.load('op_%s_alpha' % self.label)
        return direct.contract_two('ab,ab', cache['dm_alpha'])

    @doc_inherit(Observable)
    def add_fock(self, cache, fock_alpha):
        self._update_direct(cache)
        direct = cache.load('op_%s_alpha' % self.label)
        fock_alpha.iadd(direct)


class UDirectTerm(Observable):
    """Direct term of the expectation value of a two-body operator (unrestricted)."""

    def __init__(self, op_alpha, label, op_beta=None):
        """Initialize a UDirectTerm instance.

        Parameters
        ----------
        op_alpha : FourIndex
            Expansion of two-body operator in basis of alpha orbitals.
        label : str
            A short string to identify the observable.
        op_beta : FourIndex
            Expansion of two-body operator in basis of beta orbitals. When not given,
            op_alpha is used.
        """
        self.op_alpha = op_alpha
        self.op_beta = op_alpha if op_beta is None else op_beta
        Observable.__init__(self, label)

    def _update_direct(self, cache):
        """Recompute the direct operator(s) if it/they has/have become invalid.

        Parameters
        ----------
        cache : Cache
            Used to store intermediate results that can be reused or inspected later.
        """
        if self.op_alpha is self.op_beta:
            # This branch is nearly always going to be followed in practice.
            dm_full = compute_dm_full(cache)
            direct, new = cache.load('op_%s' % self.label, alloc=dm_full.new)
            if new:
                self.op_alpha.contract_two_to_two('abcd,bd->ac', dm_full, direct)
        else:
            # This is probably never going to happen. In case it does, please
            # add the proper code here.
            raise NotImplementedError

    @doc_inherit(Observable)
    def compute_energy(self, cache):
        self._update_direct(cache)
        if self.op_alpha is self.op_beta:
            # This branch is nearly always going to be followed in practice.
            direct = cache['op_%s' % self.label]
            dm_full = cache['dm_full']
            return 0.5 * direct.contract_two('ab,ab', dm_full)
        else:
            # This is probably never going to happen. In case it does, please
            # add the proper code here.
            raise NotImplementedError

    @doc_inherit(Observable)
    def add_fock(self, cache, fock_alpha, fock_beta):
        self._update_direct(cache)
        if self.op_alpha is self.op_beta:
            # This branch is nearly always going to be followed in practice.
            direct = cache['op_%s' % self.label]
            fock_alpha.iadd(direct)
            fock_beta.iadd(direct)
        else:
            # This is probably never going to happen. In case it does, please
            # add the proper code here.
            raise NotImplementedError


class RExchangeTerm(Observable):
    """Exchange term of the expectation value of a two-body operator (restricted)."""

    def __init__(self, op_alpha, label, fraction=1.0):
        """Initialize a RExchangeTerm instance.

        Parameters
        ----------
        op_alpha : FourIndex
            Expansion of two-body operator in basis of alpha orbitals. Same is used for
            beta orbitals.
        fraction : float
            Amount of exchange to be included (1.0 corresponds to 100%).
        label : str
            A short string to identify the observable.
        """
        self.op_alpha = op_alpha
        self.fraction = fraction
        Observable.__init__(self, label)

    def _update_exchange(self, cache):
        """Recompute the Exchange operator if invalid.

        Parameters
        ----------
        cache : Cache
            Used to store intermediate results that can be reused or inspected later.
        """
        dm_alpha = cache['dm_alpha']
        exchange_alpha, new = cache.load('op_%s_alpha' % self.label,
                                         alloc=dm_alpha.new)
        if new:
            self.op_alpha.contract_two_to_two('abcd,cb->ad', dm_alpha, exchange_alpha)

    @doc_inherit(Observable)
    def compute_energy(self, cache):
        self._update_exchange(cache)
        exchange_alpha = cache['op_%s_alpha' % self.label]
        dm_alpha = cache['dm_alpha']
        return -self.fraction * exchange_alpha.contract_two('ab,ab', dm_alpha)

    @doc_inherit(Observable)
    def add_fock(self, cache, fock_alpha):
        self._update_exchange(cache)
        exchange_alpha = cache['op_%s_alpha' % self.label]
        fock_alpha.iadd(exchange_alpha, -self.fraction)


class UExchangeTerm(Observable):
    """Exchange term of the expectation value of a two-body operator (unrestricted)."""

    def __init__(self, op_alpha, label, fraction=1.0, op_beta=None):
        """Initialize a UExchangeTerm instance.

        Parameters
        ----------
        op_alpha : FourIndex
            Expansion of two-body operator in basis of alpha orbitals.
        label : str
            A short string to identify the observable.
        fraction : float
            Amount of exchange to be included (1.0 corresponds to 100%).
        op_beta : FourIndex
            Expansion of two-body operator in basis of beta orbitals. When not given,
            op_alpha is used.
        """
        self.op_alpha = op_alpha
        self.op_beta = op_alpha if op_beta is None else op_beta
        self.fraction = fraction
        Observable.__init__(self, label)

    def _update_exchange(self, cache):
        """Recompute the Exchange operator(s) if invalid.

        Parameters
        ----------
        cache : Cache
            Used to store intermediate results that can be reused or inspected later.
        """
        # alpha
        dm_alpha = cache['dm_alpha']
        exchange_alpha, new = cache.load('op_%s_alpha' % self.label,
                                         alloc=dm_alpha.new)
        if new:
            self.op_alpha.contract_two_to_two('abcd,cb->ad', dm_alpha, exchange_alpha)
        # beta
        dm_beta = cache['dm_beta']
        exchange_beta, new = cache.load('op_%s_beta' % self.label,
                                         alloc=dm_beta.new)
        if new:
            self.op_beta.contract_two_to_two('abcd,cb->ad', dm_beta, exchange_beta)

    @doc_inherit(Observable)
    def compute_energy(self, cache):
        self._update_exchange(cache)
        exchange_alpha = cache['op_%s_alpha' % self.label]
        exchange_beta = cache['op_%s_beta' % self.label]
        dm_alpha = cache['dm_alpha']
        dm_beta = cache['dm_beta']
        return -0.5 * self.fraction * exchange_alpha.contract_two('ab,ab', dm_alpha) \
               -0.5 * self.fraction * exchange_beta.contract_two('ab,ab', dm_beta)

    @doc_inherit(Observable)
    def add_fock(self, cache, fock_alpha, fock_beta):
        self._update_exchange(cache)
        exchange_alpha = cache['op_%s_alpha' % self.label]
        fock_alpha.iadd(exchange_alpha, -self.fraction)
        exchange_beta = cache['op_%s_beta' % self.label]
        fock_beta.iadd(exchange_beta, -self.fraction)
