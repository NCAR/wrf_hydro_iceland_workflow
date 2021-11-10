import os
import subprocess
from urllib import request
from datetime import datetime, timedelta
import time
import signal
import logging

logging.basicConfig(format="%(levelname)s, %(asctime)s %(message)s", level=logging.DEBUG)

###########################
#
# This script downloads WRF data needed for the WRF-HYDRO short range forecast.
# It will loop indefinitely until data for the desired short range cycle is available
#
# Script configuration is pulled from the environment:
#
#   SCRATCHDIR  : where to write downloaded files
#   OUTDIR      : where to write extracted files
#   LENGTH_HRS  : the length of the short range forecast
#   DATE        : The date and cycle time to run YYYYMMDDHH
#
###########################

INURL = "http://www.betravedur.is/lv_island_2km"
INFILE = "v3.9.1_wrfout_d02_%Y-%m-%d_%H_island.nc"

OUTDIR = os.environ['FORCING_INPUTDIR']
SCRATCHDIR = os.environ['FORCING_SCRATCHDIR']
LENGTH = 12 

# look for closest 6hr file from the *last* model run
DATE = datetime.strptime(os.environ['FORCING_DATE'], "%Y%m%d%H") - timedelta(hours=6)
while DATE.hour not in [0,6,12,18]:
    DATE -= timedelta(hours=1)

def exit_on_sigterm(a,b):
    logging.info("SIGTERM received. Exiting")
    exit(1)

# capture SIGTERM so we can log it
signal.signal(signal.SIGTERM, exit_on_sigterm)


def download_file(ftime):
    """
    Download the file for the requested time and write to SCRATCHDIR
    :param ftime: The requested time as a datetime object
    :return: The name of the requested file, or None
    """
    fname = ftime.strftime(INFILE)
    url = "%s/%s" % (INURL, fname)

    output = "%s/%s" % (SCRATCHDIR, fname)
    logging.debug("Looking for %s" % url)

    if os.path.isfile(output):
        return output

    try:
        logging.debug("Downloading %s" % url)
        ret = request.urlretrieve(url, output)
        return output
    except:
        logging.debug("Unable to download %s" % url)
        return None


def extract_files(fname):
    """
    Use NCO to extract times from the provided file. Writes extracted files
    to OUTDIR 
    """

    for i in range(0,LENGTH + 1):
        outfile = "%s/%s_f%02d.nc" % (OUTDIR, os.path.basename(fname)[:-3], i)
        if os.path.isfile(outfile):
            continue
        cmd = "ncks -O -d Time,%s %s %s" % ((i), fname, outfile)
        os.system(cmd)


def run():
    logging.debug("Processing files for %s" % DATE.strftime("%Y-%m-%d %H"))

    while True:
        logging.debug("Looking for file")
        fname = download_file(DATE)
        if not fname:
            logging.debug("Not found. Sleeping 5 minutes")
            time.sleep(300)
            continue
        break

    logging.debug("Extracting files")
    extract_files(fname)

    
if __name__ == "__main__":
    run()
