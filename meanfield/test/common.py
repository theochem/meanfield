# -*- coding: utf-8 -*-
# HORTON: Helpful Open-source Research TOol for N-fermion systems.
# Copyright (C) 2011-2017 The HORTON Development Team
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
from contextlib import contextmanager

import matplotlib.pyplot as pt
import numpy as np
from os import path

from . import gobasis_data
from . import mol_data as mdata
from gbasis import GOBasis
from horton.grid.molgrid import BeckeMolGrid
from ..builtin import RDiracExchange, UDiracExchange
from ..convergence import convergence_error_eigen
from ..gridgroup import RGridGroup, UGridGroup
from ..guess import guess_core_hamiltonian
from ..hamiltonian import REffHam, UEffHam
from ..libxc import RLibXCLDA, ULibXCLDA, RLibXCGGA, ULibXCGGA, \
    ULibXCMGGA, RLibXCHybridMGGA
from ..observable import RTwoIndexTerm, RDirectTerm, RExchangeTerm
from ..observable import UTwoIndexTerm, UDirectTerm, UExchangeTerm
from ..occ import AufbauOccModel
from ..orbitals import Orbitals
from ..scf_oda import check_cubic

__all__ = [
    'check_cubic_wrapper', 'check_interpolation', 'check_dot_hessian',
    'check_dot_hessian_polynomial', 'check_solve', 'check_dot_hessian_cache',
    'helper_compute',
    'check_hf_cs_hf', 'check_lih_os_hf', 'check_water_cs_hfs',
    'check_n2_cs_hfs', 'check_h3_os_hfs', 'check_h3_os_pbe', 'check_co_cs_pbe',
    'check_water_cs_m05', 'check_methyl_os_tpss',
]


def check_cubic_wrapper(ham, dm0s, dm1s, do_plot=False):
    focks = [np.zeros(dm0.shape) for dm0 in dm0s]

    # evaluate stuff at dm0
    ham.reset(*dm0s)
    e0 = ham.compute_energy()
    ham.compute_fock(*focks)
    g0 = 0.0
    for i in xrange(ham.ndm):
        g0 += np.einsum('ab,ba', focks[i], dm1s[i])
        g0 -= np.einsum('ab,ba', focks[i], dm0s[i])
    g0 *= ham.deriv_scale

    # evaluate stuff at dm1
    ham.reset(*dm1s)
    e1 = ham.compute_energy()
    ham.compute_fock(*focks)
    g1 = 0.0
    for i in xrange(ham.ndm):
        g1 += np.einsum('ab,ba', focks[i], dm1s[i])
        g1 -= np.einsum('ab,ba', focks[i], dm0s[i])
    g1 *= ham.deriv_scale

    check_cubic(ham, dm0s, dm1s, e0, e1, g0, g1, do_plot)


def check_interpolation(ham, olp, kin, na, orbs, do_plot=False):
    dm0s = [orb.to_dm() for orb in orbs]
    guess_core_hamiltonian(olp, kin + na, *orbs)
    dm1s = [orb.to_dm() for orb in orbs]
    check_cubic_wrapper(ham, dm0s, dm1s, do_plot)


def check_dot_hessian(ham, *dms0):
    """Test dot_hessian implementation with finite differences.

    This test is comparable to ``check_delta`` but is a little simpler to use. The small
    displacements from the reference are generated by adding white noise to the reference
    DMs with an amplitude of 1e-4. 100 displacements are constructed. In all other ways,
    the test is working in the same way as ``check_delta``. This also means that this test
    only works well when the reference is not a stationary point, i.e. the Fock matrix
    should not be zero. (This is usually not a problem.)

    Parameters
    ----------
    ham : EffHam
        A Hamiltonian.
    dms0 : list of TwoIndex
        A list of density matrices that define the reference point for the finite
        differences. In the case of a restricted effective Hamiltonian, this is just the
        alpha density matrix. In the case of an unrestricted effective Hamiltonian, these
        are the alpha and beta density matrix.
    """
    assert ham.ndm == len(dms0)
    nbasis = dms0[0].shape[0]
    focks0 = [np.zeros((nbasis, nbasis)) for _i in xrange(ham.ndm)]
    ham.reset(*dms0)
    ham.compute_fock(*focks0)

    eps = 1e-4
    nrep = 100
    diffs = np.zeros(nrep)
    errors = np.zeros(nrep)
    dms1 = [np.zeros((nbasis, nbasis)) for _i in xrange(ham.ndm)]
    focks1 = [np.zeros((nbasis, nbasis)) for _i in xrange(ham.ndm)]
    dots0 = [np.zeros((nbasis, nbasis)) for _i in xrange(ham.ndm)]
    dots1 = [np.zeros((nbasis, nbasis)) for _i in xrange(ham.ndm)]
    for irep in xrange(nrep):
        delta_dms = [np.random.normal(0, eps, (nbasis, nbasis)) for _i in xrange(ham.ndm)]
        for idm in xrange(ham.ndm):
            dms1[idm] = dms0[idm] + delta_dms[idm]
        ham.reset(*dms0)
        ham.reset_delta(*delta_dms)
        ham.compute_dot_hessian(*dots0)

        ham.reset(*dms1)
        ham.reset_delta(*delta_dms)
        ham.compute_fock(*focks1)
        ham.compute_dot_hessian(*dots1)

        diffsq = 0.0
        errorsq = 0.0
        for idm in xrange(ham.ndm):
            tmp1 = focks0[idm] - focks1[idm]
            tmp2 = np.dot(tmp1, dms0[idm])
            diffsq += np.einsum('ab,ab', tmp2, tmp2)
            tmp1 += (0.5 * ham.deriv_scale) * dots0[idm]
            tmp1 += (0.5 * ham.deriv_scale) * dots1[idm]
            tmp2 = np.dot(tmp1, dms0[idm])
            errorsq += np.einsum('ab,ab', tmp2, tmp2)
        diffs[irep] = diffsq ** 0.5
        errors[irep] = errorsq ** 0.5

    threshold = np.median(diffs) * 0.1
    mask = diffs > threshold

    assert abs(errors[mask]).max() < threshold, (
                                                    'The first order approximation off the difference between Fock matrices is too '
                                                    'wrong.\nThe threshold is %.1e.\nDiffs and Errors are:\n%s') % \
                                                (threshold, np.array([diffs, errors]).T)


def check_dot_hessian_polynomial(olp, core, ham, orbs, is_hf=True, extent=1.0,
                                 threshold=1e-2, do_plot=False):
    """Test dot_hessian by making a quadratic energy approximation.

    The quadratic model is used to interpolate the energy between the given solution
    (orbs) and the core Hamiltonian guess.

    Parameters
    ----------
    olp : TwoIndex
        The overlap matrix.
    core : TwoIndex
        The core Hamiltonian.
    ham : EffHam
        An effective Hamiltonian.
    orbs : list of Orbitals objects.
        A set of orbitals (one for restricted, two for unrestricted)
    is_hf : bool
        Set to True when testing with pure HF.
    extent : float
        The extent of the interpolation. 1.0 is whole range.
    threshold : float
        The allowed error between the energies.
    do_plot : bool
        When True, some plots will be made. Useful for debugging.
    """
    # First alpha density matrix is the given matrix
    dms1 = [orb.to_dm() for orb in orbs]

    # Second alpha density matrix is that from the core Hamiltonian
    guess_core_hamiltonian(olp, core, *orbs)
    dms2 = [orb.to_dm() for orb in orbs]

    # Test quadratic interpolation of the energy. This should match very well
    # with normal energy calculations as the energy is quadratic in the
    # density matrix.
    npoint = 11
    xs = np.linspace(0.0, extent, npoint)

    def check(dms_a, dms_b):
        """Check quadratic energy model between two dms."""
        ham.reset(*dms_a)
        energy_a_0 = ham.compute_energy()
        focks_a = [np.zeros(dm_a.shape) for dm_a in dms_a]
        ham.compute_fock(*focks_a)

        delta_dms = []
        for idm in xrange(ham.ndm):
            delta_dms.append(dms_b[idm] - dms_a[idm])
        ham.reset_delta(*delta_dms)
        dots_a = [np.zeros(dm_a.shape) for dm_a in dms_a]
        ham.compute_dot_hessian(*dots_a)

        energy_a_1 = 0.0
        energy_a_2 = 0.0
        for idm in xrange(ham.ndm):
            energy_a_1 += np.einsum('ab,ba', focks_a[idm], delta_dms[idm]) * ham.deriv_scale
            energy_a_2 += np.einsum('ab,ba', dots_a[idm], delta_dms[idm]) * ham.deriv_scale ** 2

        # print 'energy_a_0', energy_a_0
        # print 'energy_a_1', energy_a_1
        # print 'energy_a_2', energy_a_2

        # Compute interpolation and compare
        energies_x = np.zeros(npoint)
        energies_2nd_order = np.zeros(npoint)
        derivs_x = np.zeros(npoint)
        derivs_2nd_order = np.zeros(npoint)
        for ipoint in xrange(npoint):
            x = xs[ipoint]
            dms_x = []
            for idm in xrange(ham.ndm):
                dm_x = dms_a[idm] * (1 - x) + dms_b[idm] * x
                dms_x.append(dm_x)
            ham.reset(*dms_x)
            energies_x[ipoint] = ham.compute_energy()
            ham.compute_fock(*focks_a)
            for idm in xrange(ham.ndm):
                derivs_x[ipoint] += np.einsum('ab,ba', focks_a[idm], delta_dms[idm]) * \
                                    ham.deriv_scale

            energies_2nd_order[ipoint] = energy_a_0 + x * energy_a_1 + 0.5 * x * x * energy_a_2
            derivs_2nd_order[ipoint] = energy_a_1 + x * energy_a_2
            # print '%5.2f %15.8f %15.8f' % (x, energies_x[ipoint], energies_2nd_order[ipoint])

        if do_plot:  # pragma: no cover
            pt.clf()
            pt.plot(xs, energies_x, 'ro')
            pt.plot(xs, energies_2nd_order, 'k-')
            pt.savefig('test_energies.png')
            pt.clf()
            pt.plot(xs, derivs_x, 'ro')
            pt.plot(xs, derivs_2nd_order, 'k-')
            pt.savefig('test_derivs.png')

        assert abs(energies_x - energies_2nd_order).max() / np.ptp(energies_x) < threshold
        assert abs(derivs_x - derivs_2nd_order).max() / np.ptp(derivs_x) < threshold
        return energy_a_0, energy_a_1, energy_a_2

    # 1) using dms1 as reference point
    _energy1_0, _energy1_1, energy1_2 = check(dms1, dms2)

    # 2) using dms2 as reference point
    _energy2_0, _energy2_1, energy2_2 = check(dms2, dms1)

    if is_hf:
        # Final check: curvature should be the same in the HF case.
        assert abs(energy1_2 - energy2_2) < threshold


def check_dot_hessian_cache(ham, *dms):
    """Check the behavior of the cache of an effective Hamiltonian.

    Parameters
    ----------
    ham : EffHam
        An effective Hamiltonian.
    dms : list of TwoIndex
        Density matrices to use in test. (One for restricted, two for unrestricted.)
    """
    # Do a regular Fock build. Take a copy of all names in the cache
    ham.reset(*dms)
    focks = [np.zeros(dm.shape) for dm in dms]
    ham.compute_fock(*focks)
    keys0 = sorted(ham.cache.iterkeys())

    # Do a dot-hessian. Check that some extra elements are present in cache
    ham.reset_delta(*focks)
    dots = [np.zeros(dm.shape) for dm in dms]
    ham.compute_dot_hessian(*dots)
    keys1 = sorted(ham.cache.iterkeys())
    assert len(keys0) < len(keys1)
    for key in keys0:
        assert key in keys1

    # Remove all elements from cache related to dot-hessian.
    # Check that the original list of keys is restored.
    # Keys starting with 'kernel' are allowed.
    ham.cache.clear(tags='d')
    keys2 = sorted(key for key in ham.cache.iterkeys() if not key.startswith('kernel'))
    assert keys0 == keys2


def check_solve(ham, scf_solver, occ_model, olp, kin, na, *orbs):
    guess_core_hamiltonian(olp, kin + na, *orbs)
    if scf_solver.kind == 'orb':
        occ_model.assign(*orbs)
        assert scf_solver.error(ham, olp, *orbs) > scf_solver.threshold
        scf_solver(ham, olp, occ_model, *orbs)
        assert scf_solver.error(ham, olp, *orbs) < scf_solver.threshold
    else:
        occ_model.assign(*orbs)
        dms = [orb.to_dm() for orb in orbs]
        assert scf_solver.error(ham, olp, *dms) > scf_solver.threshold
        scf_solver(ham, olp, occ_model, *dms)
        assert scf_solver.error(ham, olp, *dms) < scf_solver.threshold
        focks = [np.zeros(dms[0].shape) for i in xrange(ham.ndm)]
        ham.compute_fock(*focks)
        for i in xrange(ham.ndm):
            orbs[i].from_fock(focks[i], olp)
        occ_model.assign(*orbs)


def helper_compute(ham, *orbs):
    # Test energy before scf
    dms = [orb.to_dm() for orb in orbs]
    ham.reset(*dms)
    ham.compute_energy()
    focks = [np.zeros(dms[0].shape) for orb in orbs]
    ham.compute_fock(*focks)
    return ham.cache['energy'], focks


def check_hf_cs_hf(scf_solver):
    fname = 'hf_sto3g_fchk'

    olp = load_olp(fname)
    kin = load_kin(fname)
    na = load_na(fname)
    er = load_er(fname)
    external = {'nn': load_nn(fname)}
    terms = [
        RTwoIndexTerm(kin, 'kin'),
        RDirectTerm(er, 'hartree'),
        RExchangeTerm(er, 'x_hf'),
        RTwoIndexTerm(na, 'ne'),
    ]
    ham = REffHam(terms, external)
    occ_model = AufbauOccModel(5)
    orb_alpha = load_orbs_alpha(fname)

    check_solve(ham, scf_solver, occ_model, olp, kin, na, orb_alpha)

    # test orbital energies
    expected_energies = np.array([
        -2.59083334E+01, -1.44689996E+00, -5.57467136E-01, -4.62288194E-01,
        -4.62288194E-01, 5.39578910E-01,
    ])
    assert abs(orb_alpha.energies - expected_energies).max() < 1e-5

    ham.compute_energy()
    # compare with g09
    assert abs(ham.cache['energy'] - -9.856961609951867E+01) < 1e-8
    assert abs(ham.cache['energy_kin'] - 9.766140786239E+01) < 2e-7
    assert abs(ham.cache['energy_hartree'] + ham.cache['energy_x_hf'] - 4.561984106482E+01) < 1e-6
    assert abs(ham.cache['energy_ne'] - -2.465756615329E+02) < 1e-6
    assert abs(ham.cache['energy_nn'] - 4.7247965053) < 1e-8


def check_lih_os_hf(scf_solver):
    fname = 'li_h_3_21G_hf_g09_fchk'

    olp = load_olp(fname)
    kin = load_kin(fname)
    na = load_na(fname)
    er = load_er(fname)
    external = {'nn': load_nn(fname)}
    terms = [
        UTwoIndexTerm(kin, 'kin'),
        UDirectTerm(er, 'hartree'),
        UExchangeTerm(er, 'x_hf'),
        UTwoIndexTerm(na, 'ne'),
    ]
    ham = UEffHam(terms, external)
    occ_model = AufbauOccModel(2, 1)

    orb_alpha = load_orbs_alpha(fname)
    orb_beta = load_orbs_beta(fname)

    check_solve(ham, scf_solver, occ_model, olp, kin, na, orb_alpha, orb_beta)

    expected_alpha_energies = np.array([
        -2.76116635E+00, -7.24564188E-01, -1.79148636E-01, -1.28235698E-01,
        -1.28235698E-01, -7.59817520E-02, -1.13855167E-02, 6.52484445E-03,
        6.52484445E-03, 7.52201895E-03, 9.70893294E-01,
    ])
    expected_beta_energies = np.array([
        -2.76031162E+00, -2.08814026E-01, -1.53071066E-01, -1.25264964E-01,
        -1.25264964E-01, -1.24605870E-02, 5.12761388E-03, 7.70499854E-03,
        7.70499854E-03, 2.85176080E-02, 1.13197479E+00,
    ])
    assert abs(orb_alpha.energies - expected_alpha_energies).max() < 1e-5
    assert abs(orb_beta.energies - expected_beta_energies).max() < 1e-5

    ham.compute_energy()
    # compare with g09
    assert abs(ham.cache['energy'] - -7.687331212191962E+00) < 1e-8
    assert abs(ham.cache['energy_kin'] - 7.640603924034E+00) < 2e-7
    assert abs(ham.cache['energy_hartree'] + ham.cache['energy_x_hf'] - 2.114420907894E+00) < 1e-7
    assert abs(ham.cache['energy_ne'] - -1.811548789281E+01) < 2e-7
    assert abs(ham.cache['energy_nn'] - 0.6731318487) < 1e-8


def check_water_cs_hfs(scf_solver):
    fname = 'water_hfs_321g_fchk'
    mdata = load_mdata(fname)

    grid = BeckeMolGrid(mdata['coordinates'], mdata['numbers'], mdata['pseudo_numbers'],
                        random_rotate=False)
    olp = load_olp(fname)
    kin = load_kin(fname)
    na = load_na(fname)
    er = load_er(fname)

    external = {'nn': load_nn(fname)}
    terms = [
        RTwoIndexTerm(kin, 'kin'),
        RDirectTerm(er, 'hartree'),
        RGridGroup(get_obasis(fname), grid, [
            RDiracExchange(),
        ]),
        RTwoIndexTerm(na, 'ne'),
    ]
    ham = REffHam(terms, external)
    orb_alpha = load_orbs_alpha(fname)

    # The convergence should be reasonable, not perfect because of limited
    # precision in Gaussian fchk file and different integration grids:
    assert convergence_error_eigen(ham, olp, orb_alpha) < 3e-5

    # Recompute the orbitals and orbital energies. This should be reasonably OK.
    dm_alpha = load_orbsa_dms(fname)
    ham.reset(dm_alpha)
    ham.compute_energy()
    fock_alpha = np.zeros(dm_alpha.shape)
    ham.compute_fock(fock_alpha)
    orb_alpha.from_fock(fock_alpha, olp)

    expected_energies = np.array([
        -1.83691041E+01, -8.29412411E-01, -4.04495188E-01, -1.91740814E-01,
        -1.32190590E-01, 1.16030419E-01, 2.08119657E-01, 9.69825207E-01,
        9.99248500E-01, 1.41697384E+00, 1.47918828E+00, 1.61926596E+00,
        2.71995350E+00
    ])

    assert abs(load_orbs_alpha(fname).energies - expected_energies).max() < 2e-4
    assert abs(ham.cache['energy_ne'] - -1.977921986200E+02) < 1e-7
    assert abs(ham.cache['energy_kin'] - 7.525067610865E+01) < 1e-9
    assert abs(
        ham.cache['energy_hartree'] + ham.cache['energy_x_dirac'] - 3.864299848058E+01) < 2e-4
    assert abs(ham.cache['energy'] - -7.474134898935590E+01) < 2e-4
    assert abs(ham.cache['energy_nn'] - 9.1571750414) < 2e-8

    # Converge from scratch and check energies
    occ_model = AufbauOccModel(5)
    check_solve(ham, scf_solver, occ_model, olp, kin, na, load_orbs_alpha(fname))

    ham.compute_energy()
    assert abs(ham.cache['energy_ne'] - -1.977921986200E+02) < 1e-4
    assert abs(ham.cache['energy_kin'] - 7.525067610865E+01) < 1e-4
    assert abs(
        ham.cache['energy_hartree'] + ham.cache['energy_x_dirac'] - 3.864299848058E+01) < 2e-4
    assert abs(ham.cache['energy'] - -7.474134898935590E+01) < 2e-4


def check_n2_cs_hfs(scf_solver):
    fname = 'n2_hfs_sto3g_fchk'
    mdata = load_mdata(fname)
    grid = BeckeMolGrid(mdata['coordinates'], mdata['numbers'], mdata['pseudo_numbers'], 'veryfine',
                        random_rotate=False)
    olp = load_olp(fname)
    kin = load_kin(fname)
    na = load_na(fname)
    er = load_er(fname)
    external = {'nn': load_nn(fname)}

    libxc_term = RLibXCLDA('x')
    terms1 = [
        RTwoIndexTerm(kin, 'kin'),
        RDirectTerm(er, 'hartree'),
        RGridGroup(get_obasis(fname), grid, [libxc_term]),
        RTwoIndexTerm(na, 'ne'),
    ]
    ham1 = REffHam(terms1, external)

    builtin_term = RDiracExchange()
    terms2 = [
        RTwoIndexTerm(kin, 'kin'),
        RDirectTerm(er, 'hartree'),
        RGridGroup(get_obasis(fname), grid, [builtin_term]),
        RTwoIndexTerm(na, 'ne'),
    ]
    ham2 = REffHam(terms2, external)

    # Compare the potential computed by libxc with the builtin implementation
    energy1, focks1 = helper_compute(ham1, load_orbs_alpha(fname))
    energy2, focks2 = helper_compute(ham2, load_orbs_alpha(fname))
    libxc_pot = ham1.cache.load('pot_libxc_lda_x_alpha')
    builtin_pot = ham2.cache.load('pot_x_dirac_alpha')
    # Libxc apparently approximates values of the potential below 1e-4 with zero.
    assert abs(libxc_pot - builtin_pot).max() < 1e-4
    # Check of the libxc energy matches our implementation
    assert abs(energy1 - energy2) < 1e-10
    ex1 = ham1.cache['energy_libxc_lda_x']
    ex2 = ham2.cache['energy_x_dirac']
    assert abs(ex1 - ex2) < 1e-10

    # The convergence should be reasonable, not perfect because of limited
    # precision in Gaussian fchk file:
    assert convergence_error_eigen(ham1, olp, load_orbs_alpha(fname)) < 1e-5
    assert convergence_error_eigen(ham2, olp, load_orbs_alpha(fname)) < 1e-5

    occ_model = AufbauOccModel(7)
    for ham in ham1, ham2:
        # Converge from scratch
        check_solve(ham, scf_solver, occ_model, olp, kin, na, load_orbs_alpha(fname))

        # test orbital energies
        expected_energies = np.array([
            -1.37107053E+01, -1.37098006E+01, -9.60673085E-01, -3.57928483E-01,
            -3.16017655E-01, -3.16017655E-01, -2.12998316E-01, 6.84030479E-02,
            6.84030479E-02, 7.50192517E-01,
        ])
        assert abs(load_orbs_alpha(fname).energies - expected_energies).max() < 3e-5

        ham.compute_energy()
        assert abs(ham.cache['energy_ne'] - -2.981579553570E+02) < 1e-5
        assert abs(ham.cache['energy_kin'] - 1.061620887711E+02) < 1e-5
        assert abs(ham.cache['energy'] - -106.205213597) < 1e-4
        assert abs(ham.cache['energy_nn'] - 23.3180604505) < 1e-8
    assert abs(
        ham1.cache['energy_hartree'] + ham1.cache['energy_libxc_lda_x'] - 6.247259253877E+01) < 1e-4
    assert abs(
        ham2.cache['energy_hartree'] + ham2.cache['energy_x_dirac'] - 6.247259253877E+01) < 1e-4


def check_h3_os_hfs(scf_solver):
    fname = 'h3_hfs_321g_fchk'
    mdata = load_mdata(fname)
    grid = BeckeMolGrid(mdata['coordinates'], mdata['numbers'], mdata['pseudo_numbers'], 'veryfine',
                        random_rotate=False)
    olp = load_olp(fname)
    kin = load_kin(fname)
    na = load_na(fname)
    er = load_er(fname)
    external = {'nn': load_nn(fname)}

    libxc_term = ULibXCLDA('x')
    terms1 = [
        UTwoIndexTerm(kin, 'kin'),
        UDirectTerm(er, 'hartree'),
        UGridGroup(get_obasis(fname), grid, [libxc_term]),
        UTwoIndexTerm(na, 'ne'),
    ]
    ham1 = UEffHam(terms1, external)

    builtin_term = UDiracExchange()
    terms2 = [
        UTwoIndexTerm(kin, 'kin'),
        UDirectTerm(er, 'hartree'),
        UGridGroup(get_obasis(fname), grid, [builtin_term]),
        UTwoIndexTerm(na, 'ne'),
    ]
    ham2 = UEffHam(terms2, external)

    # Compare the potential computed by libxc with the builtin implementation
    energy1, focks1 = helper_compute(ham1, load_orbs_alpha(fname), load_orbs_beta(fname))
    energy2, focks2 = helper_compute(ham2, load_orbs_alpha(fname), load_orbs_beta(fname))
    libxc_pot = ham1.cache.load('pot_libxc_lda_x_both')[:, 0]
    builtin_pot = ham2.cache.load('pot_x_dirac_alpha')
    # Libxc apparently approximates values of the potential below 1e-4 with zero.
    assert abs(libxc_pot - builtin_pot).max() < 1e-4
    # Check of the libxc energy matches our implementation
    assert abs(energy1 - energy2) < 1e-10
    ex1 = ham1.cache['energy_libxc_lda_x']
    ex2 = ham2.cache['energy_x_dirac']
    assert abs(ex1 - ex2) < 1e-10

    # The convergence should be reasonable, not perfect because of limited
    # precision in Gaussian fchk file:
    assert convergence_error_eigen(ham1, olp, load_orbs_alpha(fname), load_orbs_beta(fname)) < 1e-5
    assert convergence_error_eigen(ham2, olp, load_orbs_alpha(fname), load_orbs_beta(fname)) < 1e-5

    occ_model = AufbauOccModel(2, 1)
    for ham in ham1, ham2:
        # Converge from scratch
        check_solve(ham, scf_solver, occ_model, olp, kin, na, load_orbs_alpha(fname),
                    load_orbs_beta(fname))

        # test orbital energies
        expected_energies = np.array([
            -4.93959157E-01, -1.13961330E-01, 2.38730924E-01, 7.44216538E-01,
            8.30143356E-01, 1.46613581E+00
        ])
        assert abs(load_orbs_alpha(fname).energies - expected_energies).max() < 1e-5
        expected_energies = np.array([
            -4.34824166E-01, 1.84114514E-04, 3.24300545E-01, 7.87622756E-01,
            9.42415831E-01, 1.55175481E+00
        ])
        assert abs(load_orbs_beta(fname).energies - expected_energies).max() < 1e-5

        ham.compute_energy()
        # compare with g09
        assert abs(ham.cache['energy_ne'] - -6.832069993374E+00) < 1e-5
        assert abs(ham.cache['energy_kin'] - 1.870784279014E+00) < 1e-5
        assert abs(ham.cache['energy'] - -1.412556114057104E+00) < 1e-5
        assert abs(ham.cache['energy_nn'] - 1.8899186021) < 1e-8

    assert abs(
        ham1.cache['energy_hartree'] + ham1.cache['energy_libxc_lda_x'] - 1.658810998195E+00) < 1e-6
    assert abs(
        ham2.cache['energy_hartree'] + ham2.cache['energy_x_dirac'] - 1.658810998195E+00) < 1e-6


def check_co_cs_pbe(scf_solver):
    fname = 'co_pbe_sto3g_fchk'
    mdata = load_mdata(fname)
    grid = BeckeMolGrid(mdata['coordinates'], mdata['numbers'], mdata['pseudo_numbers'], 'fine',
                        random_rotate=False)
    olp = load_olp(fname)
    kin = load_kin(fname)
    na = load_na(fname)
    er = load_er(fname)
    external = {'nn': load_nn(fname)}
    terms = [
        RTwoIndexTerm(kin, 'kin'),
        RDirectTerm(er, 'hartree'),
        RGridGroup(get_obasis(fname), grid, [
            RLibXCGGA('x_pbe'),
            RLibXCGGA('c_pbe'),
        ]),
        RTwoIndexTerm(na, 'ne'),
    ]
    ham = REffHam(terms, external)

    # Test energy before scf
    energy, focks = helper_compute(ham, load_orbs_alpha(fname))
    assert abs(energy - -1.116465967841901E+02) < 1e-4

    # The convergence should be reasonable, not perfect because of limited
    # precision in Gaussian fchk file:
    assert convergence_error_eigen(ham, olp, load_orbs_alpha(fname)) < 1e-5

    # Converge from scratch
    occ_model = AufbauOccModel(7)
    check_solve(ham, scf_solver, occ_model, olp, kin, na, load_orbs_alpha(fname))

    # test orbital energies
    expected_energies = np.array([
        -1.86831122E+01, -9.73586915E+00, -1.03946082E+00, -4.09331776E-01,
        -3.48686522E-01, -3.48686522E-01, -2.06049056E-01, 5.23730418E-02,
        5.23730418E-02, 6.61093726E-01
    ])
    assert abs(load_orbs_alpha(fname).energies - expected_energies).max() < 1e-2

    ham.compute_energy()
    # compare with g09
    assert abs(ham.cache['energy_ne'] - -3.072370116827E+02) < 1e-2
    assert abs(ham.cache['energy_kin'] - 1.103410779827E+02) < 1e-2
    assert abs(ham.cache['energy_hartree'] + ham.cache['energy_libxc_gga_x_pbe'] + ham.cache[
        'energy_libxc_gga_c_pbe'] - 6.273115782683E+01) < 1e-2
    assert abs(ham.cache['energy'] - -1.116465967841901E+02) < 1e-4
    assert abs(ham.cache['energy_nn'] - 22.5181790889) < 1e-7


def check_h3_os_pbe(scf_solver):
    fname = 'h3_pbe_321g_fchk'
    mdata = load_mdata(fname)
    grid = BeckeMolGrid(mdata['coordinates'], mdata['numbers'], mdata['pseudo_numbers'], 'veryfine',
                        random_rotate=False)
    olp = load_olp(fname)
    kin = load_kin(fname)
    na = load_na(fname)
    er = load_er(fname)
    external = {'nn': load_nn(fname)}
    terms = [
        UTwoIndexTerm(kin, 'kin'),
        UDirectTerm(er, 'hartree'),
        UGridGroup(get_obasis(fname), grid, [
            ULibXCGGA('x_pbe'),
            ULibXCGGA('c_pbe'),
        ]),
        UTwoIndexTerm(na, 'ne'),
    ]
    ham = UEffHam(terms, external)

    # compute the energy before converging
    dm_alpha = load_orbsa_dms(fname)
    dm_beta = load_orbsb_dms(fname)
    ham.reset(dm_alpha, dm_beta)
    ham.compute_energy()
    assert abs(ham.cache['energy'] - -1.593208400939354E+00) < 1e-5

    # The convergence should be reasonable, not perfect because of limited
    # precision in Gaussian fchk file:
    assert convergence_error_eigen(ham, olp, load_orbs_alpha(fname), load_orbs_beta(fname)) < 2e-6

    # Converge from scratch
    occ_model = AufbauOccModel(2, 1)
    check_solve(ham, scf_solver, occ_model, olp, kin, na, load_orbs_alpha(fname),
                load_orbs_beta(fname))

    # test orbital energies
    expected_energies = np.array([
        -5.41141676E-01, -1.56826691E-01, 2.13089637E-01, 7.13565167E-01,
        7.86810564E-01, 1.40663544E+00
    ])
    assert abs(load_orbs_alpha(fname).energies - expected_energies).max() < 2e-5
    expected_energies = np.array([
        -4.96730336E-01, -5.81411249E-02, 2.73586652E-01, 7.41987185E-01,
        8.76161160E-01, 1.47488421E+00
    ])
    assert abs(load_orbs_beta(fname).energies - expected_energies).max() < 2e-5

    ham.compute_energy()
    # compare with g09
    assert abs(ham.cache['energy_ne'] - -6.934705182067E+00) < 1e-5
    assert abs(ham.cache['energy_kin'] - 1.948808793424E+00) < 1e-5
    assert abs(ham.cache['energy_hartree'] + ham.cache['energy_libxc_gga_x_pbe'] + ham.cache[
        'energy_libxc_gga_c_pbe'] - 1.502769385597E+00) < 1e-5
    assert abs(ham.cache['energy'] - -1.593208400939354E+00) < 1e-5
    assert abs(ham.cache['energy_nn'] - 1.8899186021) < 1e-8


# TODO: Move to higher level test (cached integrals are too big to isolate)
# def check_vanadium_sc_hf(scf_solver):
#     """Try to converge the SCF for the neutral vanadium atom with fixed fractional occupations.
#
#     Parameters
#     ----------
#     scf_solver : one of the SCFSolver types in HORTON
#                  A configured SCF solver that must be tested.
#     """
#     fname = "vanadium_cs_hf"
#
#     # Compute integrals
#     olp = load_olp(fname)
#     kin = load_kin(fname)
#     na = load_na(fname)
#     er = load_er(fname)
#
#     # Setup of restricted HF Hamiltonian
#     terms = [
#         RTwoIndexTerm(kin, 'kin'),
#         RDirectTerm(er, 'hartree'),
#         RExchangeTerm(er, 'x_hf'),
#         RTwoIndexTerm(na, 'ne'),
#     ]
#     ham = REffHam(terms)
#
#     # Define fractional occupations of interest. (Spin-compensated case)
#     occ_model = FixedOccModel(np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
#                                         1.0, 1.0, 0.5]))
#
#     # Allocate orbitals and make the initial guess
#     orb_alpha = Orbitals(olp.shape[0])
#     guess_core_hamiltonian(olp, kin + na, orb_alpha)
#
#     # SCF test
#     check_solve(ham, scf_solver, occ_model, olp, kin, na, orb_alpha)


def check_water_cs_m05(scf_solver):
    """Try to converge the SCF for the water molecule with the M05 functional.

    Parameters
    ----------
    scf_solver : one of the SCFSolver types in HORTON
                 A configured SCF solver that must be tested.
    """
    fname = 'water_m05_321g_fchk'
    mdata = load_mdata(fname)
    grid = BeckeMolGrid(mdata['coordinates'], mdata['numbers'], mdata['pseudo_numbers'], 'fine',
                        random_rotate=False)
    olp = load_olp(fname)
    kin = load_kin(fname)
    na = load_na(fname)
    er = load_er(fname)
    external = {'nn': load_nn(fname)}
    libxc_term = RLibXCHybridMGGA('xc_m05')
    terms = [
        RTwoIndexTerm(kin, 'kin'),
        RDirectTerm(er, 'hartree'),
        RGridGroup(get_obasis(fname), grid, [libxc_term]),
        RExchangeTerm(er, 'x_hf', libxc_term.get_exx_fraction()),
        RTwoIndexTerm(na, 'ne'),
    ]
    ham = REffHam(terms, external)

    # compute the energy before converging
    dm_alpha = load_orbsa_dms(fname)
    ham.reset(dm_alpha)
    ham.compute_energy()
    assert abs(ham.cache['energy'] - -75.9532086800) < 1e-3

    # The convergence should be reasonable, not perfect because of limited
    # precision in the molden file:
    orb_alpha = load_orbs_alpha(fname)
    assert convergence_error_eigen(ham, olp, orb_alpha) < 1e-3

    # keep a copy of the orbital energies
    expected_alpha_energies = orb_alpha.energies.copy()

    # Converge from scratch
    occ_model = AufbauOccModel(5)
    check_solve(ham, scf_solver, occ_model, olp, kin, na, orb_alpha)

    # test orbital energies
    assert abs(orb_alpha.energies - expected_alpha_energies).max() < 2e-3

    ham.compute_energy()
    # compare with
    assert abs(ham.cache['energy_kin'] - 75.54463056278) < 1e-2
    assert abs(ham.cache['energy_ne'] - -198.3003887880) < 1e-2
    assert abs(ham.cache['energy_hartree'] + ham.cache['energy_x_hf'] +
               ham.cache['energy_libxc_hyb_mgga_xc_m05'] - 3.764537450376E+01) < 1e-2
    assert abs(ham.cache['energy'] - -75.9532086800) < 1e-3
    assert abs(ham.cache['energy_nn'] - 9.1571750414) < 1e-5


def check_methyl_os_tpss(scf_solver):
    """Try to converge the SCF for the methyl radical molecule with the TPSS functional.

    Parameters
    ----------
    scf_solver : one of the SCFSolver types in HORTON
                 A configured SCF solver that must be tested.
    """
    fname = 'methyl_tpss_321g_fchk'
    mdata = load_mdata(fname)
    grid = BeckeMolGrid(mdata['coordinates'], mdata['numbers'], mdata['pseudo_numbers'], 'fine',
                        random_rotate=False)
    olp = load_olp(fname)
    kin = load_kin(fname)
    na = load_na(fname)
    er = load_er(fname)
    external = {'nn': load_nn(fname)}
    terms = [
        UTwoIndexTerm(kin, 'kin'),
        UDirectTerm(er, 'hartree'),
        UGridGroup(get_obasis(fname), grid, [
            ULibXCMGGA('x_tpss'),
            ULibXCMGGA('c_tpss'),
        ]),
        UTwoIndexTerm(na, 'ne'),
    ]
    ham = UEffHam(terms, external)

    # compute the energy before converging
    dm_alpha = load_orbsa_dms(fname)
    dm_beta = load_orbsb_dms(fname)
    ham.reset(dm_alpha, dm_beta)
    ham.compute_energy()
    assert abs(ham.cache['energy'] - -39.6216986265) < 1e-3

    # The convergence should be reasonable, not perfect because of limited
    # precision in the molden file:
    assert convergence_error_eigen(ham, olp, load_orbs_alpha(fname), load_orbs_beta(fname)) < 1e-3

    # keep a copy of the orbital energies
    expected_alpha_energies = load_orbs_alpha(fname).energies.copy()
    expected_beta_energies = load_orbs_beta(fname).energies.copy()

    # Converge from scratch
    occ_model = AufbauOccModel(5, 4)
    check_solve(ham, scf_solver, occ_model, olp, kin, na, load_orbs_alpha(fname),
                load_orbs_beta(fname))

    # test orbital energies
    assert abs(load_orbs_alpha(fname).energies - expected_alpha_energies).max() < 2e-3
    assert abs(load_orbs_beta(fname).energies - expected_beta_energies).max() < 2e-3

    ham.compute_energy()
    # compare with
    assert abs(ham.cache['energy_kin'] - 38.98408965928) < 1e-2
    assert abs(ham.cache['energy_ne'] - -109.2368837076) < 1e-2
    assert abs(ham.cache['energy_hartree'] + ham.cache['energy_libxc_mgga_x_tpss'] +
               ham.cache['energy_libxc_mgga_c_tpss'] - 21.55131145126) < 1e-2
    assert abs(ham.cache['energy'] - -39.6216986265) < 1e-3
    assert abs(ham.cache['energy_nn'] - 9.0797839705) < 1e-5


def _compose_fn(subpath, fn, ext=".npy"):
    cur_pth = path.split(__file__)[0]
    pth = cur_pth + "/cached/{}/{}{}".format(fn, subpath, ext)
    return np.load(pth).astype(np.float64)


def load_json(fn):
    return _compose_fn("er", fn)
    # cur_pth = path.split(__file__)[0]
    # pth = cur_pth + "/cached/json/{}".format(fn)
    # with open(pth) as fh:
    #     a = np.array(json.load(fh))
    # return a


def load_quad(fn):
    return _compose_fn("quads", fn)


def load_dipole(fn):
    return _compose_fn("dipoles", fn)


def load_dm(fn):
    return _compose_fn("dm", fn)


def load_olp(fn):
    return _compose_fn("olp", fn)


def load_na(fn):
    return _compose_fn("na", fn)


def load_nn(fn):
    return getattr(mdata, fn)['nucnuc']


def load_kin(fn):
    return _compose_fn("kin", fn)


def load_er(fn):
    return _compose_fn("er", fn)


def load_er_chol(fn):
    return _compose_fn("chol", fn)


def load_orbsa_energies(fn):
    return _compose_fn("orbs_a_energies", fn)


def load_orbsa_coeffs(fn):
    return _compose_fn("orbs_a_coeffs", fn)


def load_orbsa_occs(fn):
    return _compose_fn("orbs_a_occs", fn)


def load_orbsa_dms(fn):
    return _compose_fn("orbs_a_dms", fn)


def load_orbs_alpha(fn):
    orb_coeffs = load_orbsa_coeffs(fn)
    orb_occs = load_orbsa_occs(fn)
    orb_energies = load_orbsa_energies(fn)
    orb = Orbitals(*orb_coeffs.shape)
    orb.coeffs[:] = orb_coeffs
    orb.occupations[:] = orb_occs
    orb.energies[:] = orb_energies
    return orb


def load_orbsb_coeffs(fn):
    return _compose_fn("orbs_b_coeffs", fn)


def load_orbsb_occs(fn):
    return _compose_fn("orbs_b_occs", fn)


def load_orbsb_dms(fn):
    return _compose_fn("orbs_b_dms", fn)


def load_orbsb_energies(fn):
    return _compose_fn("orbs_b_energies", fn)


def load_orbs_beta(fn):
    orb_coeffs = load_orbsb_coeffs(fn)
    orb_occs = load_orbsb_occs(fn)
    orb_energies = load_orbsb_energies(fn)
    orb = Orbitals(*orb_coeffs.shape)
    orb.coeffs[:] = orb_coeffs
    orb.occupations[:] = orb_occs
    orb.energies[:] = orb_energies
    return orb


def load_mdata(fn):
    return getattr(mdata, fn)


def get_obasis(fn):
    params = getattr(gobasis_data, fn)
    return GOBasis(*params)


@contextmanager
def numpy_seed(seed=1):
    """Temporarily set NumPy's random seed to a given number.

    Parameters
    ----------
    seed : int
           The seed for NumPy's random number generator.
    """
    state = np.random.get_state()
    np.random.seed(seed)
    yield None
    np.random.set_state(state)
