#!/usr/bin/env python

import os
import subprocess
import shutil
import sys

from setuptools import setup, find_packages

parent_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

INSTALL_REQUIRES = []
INSTALL_REQUIRES.append('urllib3')  # This is a 3rd party connections lib for 2.6+
assert sys.version_info >= (2, 6), "We only support Python 2.6+"

extra = {}
if sys.version_info >= (3,):
    extra['use_2to3'] = True

    # convert the test code to Python 3
    # because distribute won't do that for us
    # first copy over the tests
    tests_dir = os.path.join(parent_dir, "tests")
    tests3_dir = os.path.join(parent_dir, "3tests")
    if 'test' in sys.argv and os.path.exists(tests_dir):
        shutil.rmtree(tests3_dir, ignore_errors=True)
        shutil.copytree(tests_dir, tests3_dir)
        subprocess.call(["2to3", "-w", "--no-diffs", tests3_dir])
    TEST_SUITE = '3tests'
else:
    TEST_SUITE = 'tests'

with open('LICENSE') as f:
  license = f.read()

with open('README.rst') as f:
  readme = f.read()

setup(name='dropbox',
      version='2.2.0',
      description='Official Dropbox REST API Client',
      long_description=readme,
      author='Dropbox, Inc.',
      author_email='support-api@dropbox.com',
      url='http://www.dropbox.com/',
      packages=['dropbox', 'tests'],
      install_requires=INSTALL_REQUIRES,
      license=license,
      package_data={'dropbox': ['trusted-certs.crt'],
                    'tests' : ['server.crt', 'server.key']},
      test_suite=TEST_SUITE,
      tests_require=['mock'],
      **extra
     )
