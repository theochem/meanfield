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
#pylint: skip-file


import numpy as np
from horton import *


def test_guess_hamcore_cs():
    fn_fchk = context.get_fn('test/hf_sto3g.fchk')
    mol = Molecule.from_file(fn_fchk)
    olp = mol.obasis.compute_overlap(mol.lf)
    kin = mol.obasis.compute_kinetic(mol.lf)
    na = mol.obasis.compute_nuclear_attraction(mol.coordinates, mol.pseudo_numbers, mol.lf)
    guess_core_hamiltonian(mol.wfn, olp, kin, na)
    # just a few simple checks
    assert abs(mol.wfn.exp_alpha.energies[0] - (-2.59083334E+01)) > 1e-5 # values from fchk must be overwritten
    assert (mol.wfn.exp_alpha.energies.argsort() == np.arange(mol.obasis.nbasis)).all()


def test_guess_hamcore_os():
    fn_fchk = context.get_fn('test/li_h_3-21G_hf_g09.fchk')
    mol = Molecule.from_file(fn_fchk)
    olp = mol.obasis.compute_overlap(mol.lf)
    kin = mol.obasis.compute_kinetic(mol.lf)
    na = mol.obasis.compute_nuclear_attraction(mol.coordinates, mol.pseudo_numbers, mol.lf)
    guess_core_hamiltonian(mol.wfn, olp, kin, na)
    # just a few simple checks
    assert abs(mol.wfn.exp_alpha.energies[0] - (-2.76116635E+00)) > 1e-5 # values from fchk must be overwritten
    assert abs(mol.wfn.exp_beta.energies[0] - (-2.76031162E+00)) > 1e-5 # values from fchk must be overwritten
    assert (mol.wfn.exp_alpha.energies.argsort() == np.arange(mol.obasis.nbasis)).all()
    assert abs(mol.wfn.exp_alpha.energies - mol.wfn.exp_beta.energies).max() < 1e-10
    assert abs(mol.wfn.exp_alpha.coeffs - mol.wfn.exp_beta.coeffs).max() < 1e-10
