#!/usr/bin/env python
################################################################################
#    GIPS: Geospatial Image Processing System
#
#    AUTHOR: Matthew Hanson
#    EMAIL:  matt.a.hanson@gmail.com
#
#    Copyright (C) 2014 Applied Geosolutions
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
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

"""
Atmospheric module consists of a class for each available atmospheric model.

Class is initialized with band information (an id, bounding wavelengths,
date/time, and location).

Any info passed in beyond this should be via keywords
"""

import os
import sys
import datetime
import commands
import tempfile
import shutil
import numpy

from gips.utils import List2File, VerboseOut
from gips import utils
from gips.data.merra import merraData
from gips.data.aod import aodData
from gips.inventory import orm

# since Py6S pulls in matplotlib, we need to shut down all that gui business
import matplotlib as mpl
mpl.use('Agg')

from Py6S import SixS, Geometry, AeroProfile, Altitudes, Wavelength, \
    GroundReflectance, AtmosCorr, SixSHelpers


def atmospheric_model(doy, lat):
    """ Determine atmospheric model (used by both 6S and MODTRAN)
    1 - Tropical
    2 - Mid-Latitude Summer
    3 - Mid-Latitude Winter
    4 - Sub-Arctic Summer
    5 - Sub-Arctic Winter
    6 - US Standard Atmosphere
    """
    # Determine season
    if doy < 121 or doy > 274:
        if lat < 0:
            summer = True
        else:
            summer = False
    else:
        if lat < 0:
            summer = False
        else:
            summer = True
    # Determine model
    if abs(lat) <= 15:
        model = 1
    elif abs(lat) >= 60:
        if summer:
            model = 4
        else:
            model = 5
    else:
        if summer:
            model = 2
        else:
            model = 3
    return model


"""
class Acolite():
        ACOLITEPATHS = {
            'ACO_DIR': settings().REPOS['landsat']['ACOLITE_DIR'],
            # N.B.: only seems to work when run from the ACO_DIR
            'IDLPATH': './idl84/bin/idl',
            'ACOLITE_BINARY': 'acolite.sav',
            # TODO: template may be the only piece that needs
            #       to be moved for driver-independence.
            'SETTINGS_TEMPLATE': None
            # used to point here in landsat driver...where too now...
            # os.path.join(os.path.dirname(__file__), 'acolite.cfg')
        }
        ACOLITE_NDV = 1.875 * 2 ** 122
    def process(cls, asset, aco_proc_dir, products):
        '''
        TODO: Ensure this is genericized to work for S2 or Landsat.
        '''

        # EXTRACT ASSET
        asset.extract(dest_dir=aco_proc_dir)

        # PROCESS SETTINGS TEMPLATE FOR SPECIFIED PRODUCTS
        settings_path = os.path.join(aco_proc_dir, 'settings.cfg')
        template_path = ACOLITEPATHS.pop('SETTINGS_TEMPLATE')
        acolite_products = ','.join(
            [
                products[k]['acolite-product']
                for k in products
                if k != 'meta'
            ]
        )
        with open(template_path, 'r') as aco_template:
            with open(settings_path, 'w') as aco_settings:
                for line in aco_template:
                    aco_settings.write(
                        re.sub(
                            r'GIPS_LANDSAT_PRODUCTS',
                            acolite_products,
                            line
                        )
                    )
        ACOLITEPATHS['ACOLITE_SETTINGS'] = settings_path

        # PROCESS VIA ACOLITE IDL CALL
        cmd = (
            ('cd {ACO_DIR} ; '
             '{IDLPATH} -IDL_CPU_TPOOL_NTHREADS 1 '
             '-rt={ACOLITE_BINARY} '
             '-args settings={ACOLITE_SETTINGS} '
             'output={OUTPUT} image={IMAGES}')
            .format(
                OUTPUT=aco_proc_dir,
                IMAGES=aco_proc_dir,
                **ACOLITEPATHS
            )
        )
        utils.verbose_out('Running: {}'.format(cmd), 2)
        status, output = commands.getstatusoutput(cmd)
        if status != 0:
            raise Exception(cmd, output)


        # COMBINE MULTI-IMAGE PRODUCTS INTO
        # A MULTI-BAND TIF, ADD METADATA, and MOVE INTO TILES
        allfiles = glob.glob(os.path.join(aco_proc_dir, '*'))
        prodout = dict()
        for key in products:
            pat = re.compile(products[key]['acolite-pattern'])
            files = filter(pat.match, allfiles)
            ofname = products[key]['fname']

            if not ((len(files) == 1) ^ (key == 'rhow')):
                raise Exception(
                    'Found {length} files for product "{prod}"'
                    .format(length=len(files), prod=key)
                )
            elif key == 'rhow':
                wl_fn = sorted(
                    [
                        (int(re.sub(r'.*RHOW_(\d+).tif', '\g<1>', fn)), fn)
                        for fn in files
                    ]
                )
                imgs = map(lambda x: gippy.GeoImage(x[1]), wl_fn)
                imgout = gippy.GeoImage(
                    ofname, imgs[0], gippy.GDT_Float32, len(files)
                )
                imgout.SetNoData(ACOLITE_NDV)
                pmeta = {
                    mdi: products[key][mdi]
                    for mdi in ['acolite-product', 'description']
                }
                pmeta['source_asset'] = os.path.basename(asset.filename)
                imgout.SetMeta(pmeta)
                for i, img in enumerate(imgs):
                    wl = re.sub(r'.*RHOW_(\d+).tif', '\g<1>', img.Filename())
                    imgout.SetBandName(wl, i + 1)
            else:
                assert len(files) == 1, (
                    '{} expected 1 file and found {}'.format(key, len(files))
                )
                imgout = gippy.GeoImage(ofname, gippy.GeoImage(files[0]))
                imgout.SetBandName(products[key]['acolite-product'], 1)
                imgout.SetNoData(ACOLITE_NDV)
            prodout[key] = imgout.Filename()
            imgout = None
        return prodout
"""



class SIXS():
    """ Class for running 6S atmospheric model """
    # TODO - genericize to move away from landsat specific

    def __init__(self, bandnums, wavelengths, geometry, date_time, sensor=None):
        """ Run SixS atmospheric model using Py6S """
        start = datetime.datetime.now()
        VerboseOut('Running atmospheric model (6S)', 2)

        s = SixS()
        # Geometry
        s.geometry = Geometry.User()
        s.geometry.from_time_and_location(geometry['lat'], geometry['lon'], str(date_time),
                                          geometry['zenith'], geometry['azimuth'])
        s.altitudes = Altitudes()
        s.altitudes.set_target_sea_level()
        s.altitudes.set_sensor_satellite_level()

        doy = (date_time - datetime.datetime(date_time.year, 1, 1)).days + 1
        # Atmospheric profile
        s.atmos_profile = atmospheric_model(doy, geometry['lat'])

        # Aerosols
        # TODO - dynamically adjust AeroProfile?
        s.aero_profile = AeroProfile.PredefinedType(AeroProfile.Continental)

        self.aod = aodData.get_aod(geometry['lat'], geometry['lon'], date_time.date())

        # sixs throws IEEE_UNDERFLOW_FLAG IEEE_DENORMAL for small aod.
        # and if using a predefined AeroProfile, visible or aot550 must be
        # specified.   Small here was determined emprically on my laptop, and
        # visible = 1000 km is essentially setting the visibility to infinite.
        if self.aod[1] < 0.0103:
            s.visible = 1000
        else:
            s.aot550 = self.aod[1]

        # Other settings
        s.ground_reflectance = GroundReflectance.HomogeneousLambertian(GroundReflectance.GreenVegetation)
        s.atmos_corr = AtmosCorr.AtmosCorrLambertianFromRadiance(1.0)

        # Used for testing
        funcs = {
            'LT5': SixSHelpers.Wavelengths.run_landsat_tm,
            'LT7': SixSHelpers.Wavelengths.run_landsat_etm,
            # LC8 doesn't seem to work
            #'LC8': SixSHelpers.Wavelengths.run_landsat_oli
        }
        if sensor in funcs.keys():
            saved_stdout = sys.stdout
            try:
                sys.stdout = open(os.devnull, 'w')
                wvlens, outputs = funcs[sensor](s)
            finally:
                sys.stdout = saved_stdout
        else:
            # Use wavelengths
            outputs = []
            for wv in wavelengths:
                s.wavelength = Wavelength(wv[0], wv[1])
                s.run()
                outputs.append(s.outputs)

        self.results = {}
        VerboseOut("{:>6} {:>8}{:>8}{:>8}".format('Band', 'T', 'Lu', 'Ld'), 4)
        for b, out in enumerate(outputs):
            t = out.trans['global_gas'].upward
            Lu = out.atmospheric_intrinsic_radiance
            Ld = (out.direct_solar_irradiance + out.diffuse_solar_irradiance + out.environmental_irradiance) / numpy.pi
            self.results[bandnums[b]] = [t, Lu, Ld]
            VerboseOut("{:>6}: {:>8.3f}{:>8.2f}{:>8.2f}".format(bandnums[b], t, Lu, Ld), 4)

        VerboseOut('Ran atmospheric model in %s' % str(datetime.datetime.now() - start), 2)


class MODTRAN():
    """ Class for running MODTRAN atmospheric model """
    # TODO - allow for multiple bands
    # TODO - channel integration to move away from using .chn files (tied to landsat bands)

    # hard-coded options
    filterfile = True
    _datadir = '/usr/local/modtran/DATA'

    def __init__(self, bandnum, wvlen1, wvlen2, dtime, lat, lon, profile=False):
        self.lat = lat
        self.lon = lon
        self.datetime = dtime
        seconds = (dtime.second + dtime.microsecond / 1000000.) / 3600.
        self.dtime = self.datetime.hour + self.datetime.minute / 60.0 + seconds
        self.julianday = (dtime - datetime.datetime(dtime.year, 1, 1)).days + 1

        self.model = atmospheric_model(self.julianday, lat)

        #fout = open('atm.txt','w')
        #fout.write('{:>5}{:>20}{:>20}\n'.format('Band','%T','Radiance'))

        tmpdir = tempfile.mkdtemp()
        pwd = os.getcwd()
        os.chdir(tmpdir)

        # Create link to MODTRAN data dir
        if not os.path.lexists('DATA'):
            os.symlink(self._datadir, 'DATA')

        if profile:
            mprofile = merraData.profile(lon, lat, dtime)
            pressure = mprofile['pressure']
            temp = mprofile['temp']
            humidity = mprofile['humidity']
            ozone = mprofile['ozone']
            self.atmprofile = []
            for i in range(0, len(pressure)):
                c2c1 = self.card2c1(P=pressure[i], T=temp[i], H2O=humidity[i], O3=ozone[i])
                self.atmprofile.append(c2c1)
        else:
            self.atmprofile = None

        # Generate MODTRAN input files

        # Determine if radiance or transmittance mode
        rootnames = self.addband(bandnum, wvlen1, wvlen2)
        List2File(rootnames, 'mod5root.in')

        try:
            # run output and get results
            modout = commands.getstatusoutput('modtran')
            #VerboseOut("MODTRAN Output:", 4)
            #[VerboseOut(m, 4) for m in modout]
            self.output = self.readoutput(bandnum)
            VerboseOut('MODTRAN Output: %s' % ' '.join([str(s) for s in self.output]), 4)
        except:
            utils.verbose_out(modout, 4)
            raise

        # Change back to original directory
        os.chdir(pwd)

        #print 'MODTRAN dir: ', tmpdir
        # Remove directory
        shutil.rmtree(tmpdir)

    def readoutput(self, bandnum):
        with open('band' + str(bandnum) + '.chn') as f:
            lines = f.readlines()
        data = lines[4 + bandnum]
        # Get nominal band width in microns
        bandwidth = float(data[85:94]) / 1000
        # Convert from W/sr-cm2 to W/sr-m2-um
        Lu = (float(data[59:72]) * 10000) / bandwidth
        trans = float(data[239:248])
        Ld = 0.0
        with utils.error_handler('Error calculating Ld, falling back to default (0.0)',
                                 continuable=True):
            with open('band' + str(bandnum) + 'Ld.chn') as f:
                lines = f.readlines()
            data = lines[4 + bandnum]
            # Convert channel radiance to spectral radiance
            Ld = (float(data[59:72]) * 10000) / bandwidth
        return [trans, Lu, Ld]

    def addband(self, bandnum, wvlen1, wvlen2):
        rootname1 = 'band' + str(bandnum)
        if ((wvlen1 + wvlen2) / 2.0) < 3:
            """ Run in transmittance mode for visible bands """
            mode = 4
            fwhm = 0.001
        else:
            """ Run in radiance mode for MWIR and LWIR bands """
            mode = 2
            fwhm = 0.1
        # Write tape5 file
        self.tape5(rootname1, mode, wvlen1, wvlen2, fwhm)
        if mode == 2:
            rootname2 = rootname1 + 'Ld'
            self.tape5(rootname2, mode, wvlen1, wvlen2, fwhm, surref=1, h1=0.001)
            return (rootname1, rootname2)
        else:
            return (rootname1,)

    def tape5(self, fname, mode, wvlen1, wvlen2, fwhm, surref=0, h1=100):
        f = open(fname + '.tp5', 'w')
        f.write(self.card1(mode=mode, surref=surref) + '\n')
        f.write(self.card1a() + '\n')
        if self.filterfile:
            f.write(self.card1a3() + '\n')
        f.write(self.card2() + '\n')
        if self.atmprofile is not None:
            f.write(self.card2c(len(self.atmprofile)) + '\n')
            for i in self.atmprofile:
                f.write(i + '\n')
        f.write(self.card3(h1=h1) + '\n')
        f.write(self.card3a1() + '\n')
        f.write(self.card3a2() + '\n')
        f.write(self.card4(wvlen1, wvlen2, fwhm) + '\n')
        f.write(self.card5() + '\n')
        f.close()

    def card1(self, mode, surref):
        MODTRN = 'M'  # 'C' for correlated k
        card = ('{MODTRN:1}{SPEED:1}{BINARY:1}{LYMOLC:1}{MODEL:1d}{T_BEST:1}{ITYPE:4d}{IEMSCT:5d}{IMULT:5d}'
                '{M1:5d}{M2:5d}{M3:5d}{M4:5d}{M5:5d}{M6:5d}{MDEF:5d}{I_RD2C:5d} {NOPRNT:4d}{TPTEMP:8.4f}{SURREF:>7}')
        sm = self.model
        if self.atmprofile is not None:
            model = 8   # Pressure-based
            #model = 7  # Altitude-based
            rd2c = 1
        else:
            model = sm
            rd2c = 0
        return card.format(MODTRN=MODTRN, SPEED='', BINARY='', LYMOLC='', MODEL=model, T_BEST='',
                           ITYPE=3, IEMSCT=mode, IMULT=-1, M1=sm, M2=sm, M3=sm, M4=sm, M5=sm, M6=sm, MDEF=0,
                           I_RD2C=rd2c, NOPRNT=-1, TPTEMP=0.001, SURREF=surref)

    def card1a(self):
        if self.filterfile:
            LFLTNM = 'T'
        else:
            LFLTNM = 'F'
        c = ('{DIS:1}{DISAZM:1}{DISALB:1}{NSTR:>3}{SFWHM:4.1f}{CO2MX:10.3f}{H2OSTR:>10}{O3STR:>10}'
             '{C_PROF:1}{LSUNFL:1} {LBMNAM:1} {LFLTNM:1} {H2OAER:1} {CDTDIR:1}{SOLCON:10.3f}')
                #'{CDASTM:1}{ASTMC:9.2f}{ASTMX:10.3f}{ASTMO:10.3f}{AERRH:10.3f}{NSSALB:10d}')
        return c.format(DIS='T', DISAZM='', DISALB='T', NSTR=8, SFWHM=0, CO2MX=380.0, H2OSTR='1.00', O3STR='1.00',
                        C_PROF='', LSUNFL=1, LBMNAM='f', LFLTNM=LFLTNM, H2OAER='f', CDTDIR='f', SOLCON=0.0)
                           #CDASTM='',ASTMC='',ASTMX='',ASTMO='',AERRH='',NSSALB=0)

    def card1a3(self):
        #card = ('{FILTNM:256} !CARD1A3')
        c = ('{FILTNM:56}')
        return c.format(FILTNM='DATA/landsat7.flt')

    def card2(self):
        c = ('{APLUS:>2}{IHAZE:3d}{CNOVAM:1}{ISEASN:4d}{ARUSS:>3}{IVULCN:2d}{ICSTL:5d}{ICLD:5d}'
             '{IVSA:5d}{VIS:10.5f}{WSS:10.5f}{WHH:10.5f}{RAINRT:10.5f}{GNDALT:10.5f}')
        return c.format(APLUS='', IHAZE=1, CNOVAM='', ISEASN=0, ARUSS='', IVULCN=0, ICSTL=3, ICLD=0,
                        IVSA=0, VIS=0, WSS=0, WHH=0, RAINRT=0, GNDALT=0)

    def card2c(self, numalt):
        c = ('{ML:5d}{IRD1:5d}{IRD2:5d}{HMODEL:>20}{REE:10.0f}{NMOLYC:5d}{E_MASS:10.0f}{AIRMWT:10.0f}')
        return c.format(ML=numalt, IRD1=0, IRD2=0, HMODEL='custom', REE=0, NMOLYC=0, E_MASS=0, AIRMWT=0)

    def card2c1(self, h=0, P=0, T=0.0, H2O=0, CO2=0, O3=0):
        """ Custom atmospheric layers """
        c = ('{ZM:10.3f}{P:10.3f}{T:10.3f}{WMOL1:10.3f}{WMOL2:10.3f}{WMOL3:10.3f}{JCHAR:>14}{JCHARX:1}{JCHARY:1}')
        return c.format(ZM=h, P=P, T=T, WMOL1=H2O, WMOL2=CO2, WMOL3=O3, JCHAR='ABC C         ', JCHARX=' ', JCHARY=' ')

    def card3(self, h1=100, alt=0, angle=180):
        c = ('{H1:10.3f}{H2:10.3f}{ANGLE:10.3f}{RANGE:10.3f}{BETA:10.3f}{RO:10.3f}     {LENN:>5}{PHI:10.3f}')
        return c.format(H1=h1, H2=alt, ANGLE=angle, RANGE=0, BETA=0, RO=0, LENN=0, PHI=0)

    def card3a1(self):
        c = ('{IPARM:>5}{IPH:>5}{IDAY:>5}{ISOURC:>5}')
        return c.format(IPARM=1, IPH=2, IDAY=self.julianday, ISOURC=1)

    def card3a2(self):
        c = ('{PARM1:10.3f}{PARM2:10.3f}{PARM3:10.3f}{PARM4:10.3f}{TIME:10.3f}{PSIPO:10.3f}{ANGLEM:10.3f}{G:10.3f}')
        return c.format(PARM1=self.lat, PARM2=self.lon, PARM3=0, PARM4=0, TIME=self.dtime, PSIPO=0, ANGLEM=0, G=0)

    def card4(self, v1=0.4, v2=1.0, fwhm=0.002):
        """ Spectral parameters """
        dv = fwhm / 2
        c = ('{V1:10.3f}{V2:10.3f}{DV:10.3f}{FWHM:10.3f}{YFLAG:1}{XFLAG:1}{DLIMIT:>8}{FLAGS:8}{MLFLX:3}{VRFRAC:10.3f}')
        return c.format(V1=v1, V2=v2, DV=dv, FWHM=fwhm, YFLAG='', XFLAG='', DLIMIT='',
                        FLAGS="M       ", MLFLX='', VRFRAC=0)

    def card5(self):
        c = ('{IRPT:>5}')
        return c.format(IRPT=0)

    """ old plotting code
    if plot:
        #fig = plt.figure()
        #plt.title('Atmospheric Transmittance vs Wavelength (um)')

        results = table.Table()
        results.read_csv('tape7.scn',skip=11, delim=' ', ignorebad=True, hasheader=False)
        #pdb.set_trace()

        wvlens = results.as_numpy_col(0)
        T = results.as_numpy_col(1)
        rad = results.as_numpy_col(2)
        fout.write('{:5d}{:20.10f}{:20.10f}\n'.format(bandnum,np.mean(T),np.mean(rad)))

        if plot:
            fig.add_subplot(4,2,bandnum)
            plt.title("Band %s" % bandnum)
            plt.plot(wvlens,T)
            plt.ylim([0.0,1.0])

        bandnum = bandnum+1
    if plot:
        plt.tight_layout()
        plt.show()
    fout.close()
    """
