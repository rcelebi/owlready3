#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Owlready3
# Copyright (C) 2013-2019 Jean-Baptiste LAMY

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Project metadata lives in pyproject.toml. This script only builds the
# optional Cython extension (owlready3_optimized); without Cython, Owlready3
# falls back to its slower pure-Python parser.

from setuptools import setup, Extension

try:
  from Cython.Build import cythonize
  ext_modules = cythonize(
    [Extension("owlready3_optimized", ["owlready3_optimized.pyx"])],
    compiler_directives = { "language_level" : 3 },
  )
except Exception:
  ext_modules = []

setup(ext_modules = ext_modules)
