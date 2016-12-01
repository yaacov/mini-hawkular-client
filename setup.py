#!/usr/bin/env python

from distutils.core import setup
from os import path
from setuptools.command.install import install

here = path.abspath(path.dirname(__file__))
    
setup(name='mini-hawkular-client',
      version='0.0.1',
      description='Mini Python client to communicate with Hawkular server over HTTP(S)',
      author='Yaacov Zamir based on work by Michael Burman',
      author_email='yzamir@redhat.com',
      license='Apache License 2.0',
      url='http://github.com/hawkular/mini-hawkular-client',
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Developers',
          'Programming Language :: Python',
          'Programming Language :: Python :: 2',
          'Topic :: System :: Monitoring',
      ],
      packages=['mini-hawkular']
      )
