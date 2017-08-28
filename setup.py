#!/usr/bin/env python

from __future__ import print_function
import os

import numpy as np
from setuptools import setup, Extension
import Cython.Build

from tools.gitversion import get_gitversion

def readme():
    with open('README.rst') as f:
        return f.read()

def get_libxc_path():
    p = os.environ.get("PREFIX")
    if p is not None:
        return os.path.join(p, "include")
    else:
        return ""

setup(
    name='meanfield',
    version=get_gitversion('meanfield', verbose=(__name__=='__main__')),
    description='HORTON module for SCF and HF/DFT methods',
    long_description=readme(),
    author='Toon Verstraelen',
    author_email='Toon.Verstraelen@UGent.be',
    url='https://github.com/theochem/meanfield',
    cmdclass={'build_ext': Cython.Build.build_ext},
    package_dir = {'meanfield': 'meanfield'},
    packages=['meanfield', 'meanfield.test'],
    ext_modules=[Extension(
        'meanfield.cext',
        sources=['meanfield/cext.pyx'],
        include_dirs=[np.get_include(), get_libxc_path()],
    )],
    zip_safe=False,
    setup_requires=['numpy>=1.0', 'cython>=0.24.1'],
    install_requires=['numpy>=1.0', 'nose>=0.11', 'cython>=0.24.1'],
)
