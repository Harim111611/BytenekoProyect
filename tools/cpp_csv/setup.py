"""
Setup for building the cpp_csv C++ extension module with pybind11.
"""

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import sys
import setuptools
import pybind11

class get_pybind_include:
    def __str__(self):
        return pybind11.get_include()

ext_modules = [
    Extension(
        'cpp_csv',  # name of the compiled module
        ['cpp_csv.cpp'],  # source files
        include_dirs=[
            get_pybind_include(),
        ],
        extra_compile_args=['/std:c++17'] if sys.platform == 'win32' else ['-std=c++17'],
        language='c++',
    ),
]

setup(
    name='cpp_csv',
    version='1.0.0',
    author='ByteNeko Team',
    description='Fast CSV reader and validator using C++ and pybind11',
    ext_modules=ext_modules,
    install_requires=['pybind11>=2.6.0'],
    cmdclass={'build_ext': build_ext},
    zip_safe=False,
)
