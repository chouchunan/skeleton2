#!/bin/sh
export FAI_SDK_ROOT_PATH=$PWD/..
# python setup.py build_ext --inplace
pip${1} install .
