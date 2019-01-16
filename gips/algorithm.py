#!/usr/bin/env python
################################################################################
#    GIPS: Geospatial Image Processing System
#
#    AUTHOR: Matthew Hanson
#    EMAIL:  matt.a.hanson@gmail.com
#
#    Copyright (C) 2014-2018 Applied Geosolutions
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program. If not, see <http://www.gnu.org/licenses/>
################################################################################

import argparse
#from datetime import datetime
import traceback

import gippy
import gips
from gips.utils import VerboseOut, Colors
from gips import utils
from gips.inventory import ProjectInventory


class Algorithm(object):
    name = 'Algorithm Name'
    __version__ = '0.0.0'

    def __init__(self, **kwargs):
        if 'projdir' in kwargs:
            self.inv = ProjectInventory(kwargs['projdir'], kwargs.get('products'))
        if 'nproc' in kwargs:
            self.nproc = kwargs['nproc']

    def run_command(self, **kwargs):
        """Calls "run" function, or "command" if algorithm uses subparser """
        command = kwargs.get('command', 'run')
        cmd_func = getattr(self, command)
        utils.verbose_out('Running %s' % command, 2)
        cmd_func(**kwargs)

    def run(self, **kwargs):
        pass

    @classmethod
    def info(cls):
        """ Name and versions of algorithm and GIPS library """
        return Colors.BOLD + 'GIPS (v%s): %s (v%s)' % (gips.__version__, cls.name, cls.__version__) + Colors.OFF

    @classmethod
    def parser(cls, parser0):
        """ Parser for algorithm specific options (defined by children) """
        return parser0

    @classmethod
    def subparser(cls, parser0, project=False):
        """ Add subparser to parser and return keywords user to include """
        subparser = parser0.add_subparsers(dest='command')
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('-v', '--verbose', help='Verbosity - 0: quiet, 1: normal, 2+: debug', default=1, type=int)
        if project:
            parser = cls.add_project_parser(parser)
        kwargs = {
            'formatter_class': argparse.ArgumentDefaultsHelpFormatter,
            'parents': [parser],
        }
        return (subparser, kwargs)

    @classmethod
    def add_project_parser(cls, parser):
        group = parser.add_argument_group('project options')
        group.add_argument('projdir', help='GIPS Project directory')
        group.add_argument('-p', '--products', help='Products to operate on', nargs='*')
        return parser

    @classmethod
    def main(cls):
        """ Main for algorithm classes """
        dhf = argparse.ArgumentDefaultsHelpFormatter

        # Top level parser
        parser = argparse.ArgumentParser(formatter_class=dhf, description=cls.info())
        parser.add_argument('-v', '--verbose', help='Verbosity - 0: quiet, 1: normal, 2+: debug', default=1, type=int)
        parser = cls.parser(parser)

        args = parser.parse_args()
        gippy.Options.SetVerbose(args.verbose)
        VerboseOut(cls.info())

        utils.gips_script_setup(driver_string=None, setup_orm=False)

        with utils.error_handler('Error in {}'.format(cls.name)):
            alg = cls(**vars(args))
            alg.run_command(**vars(args))

        utils.gips_exit()
