#!/usr/bin/env python
import os
from glob import glob

import Cython.Build
import numpy as np
from setuptools import setup, Extension


def get_version():
    """Get the version string set by Travis, else default to version 0.0.0"""
    return os.environ.get("PROJECT_VERSION", "0.0.0")


def get_readme():
    with open('README.rst') as f:
        return f.read()


dir_names = [os.path.basename(p) for p in glob("meanfield/test/data/*")
             if os.path.basename(p) != "__init__.py"
             and os.path.basename(p) != "__pycache__"]
pack_names = [f"meanfield.test.data.{fn}" for fn in dir_names]
pack_dict = {pn : ["*"] for pn in pack_names}

setup(
    name='meanfield',
    version=get_version(),
    description='HORTON module for SCF and HF/DFT methods',
    long_description=get_readme(),
    author='Toon Verstraelen',
    author_email='Toon.Verstraelen@UGent.be',
    url='https://github.com/theochem/meanfield',
    cmdclass={'build_ext': Cython.Build.build_ext},
    package_data=pack_dict,
    packages=['meanfield', 'meanfield.test'] + pack_names,
    ext_modules=[Extension(
        'meanfield.cext',
        sources=['meanfield/cext.pyx'],
        libraries=['xc'],
        include_dirs=[np.get_include()],
    )],
    zip_safe=False,
    setup_requires=['numpy>=1.0', 'cython>=0.24.1'],
    install_requires=['matplotlib', 'scipy', 'nose', 'gbasis'],

)
