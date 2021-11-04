import os
import subprocess
from urllib import request
from datetime import datetime, timedelta

INURL = "http://www.betravedur.is/lv_island_2km/v3.9.1_wrfout_d02_%Y-%m-%d_%H_island.nc"

OUTDIR = os.environ['FORCING_INPUTDIR']
SCRATCHDIR = os.environ['FORCING_SCRATCHDIR']
DATE = datetime.strptime(os.environ['FORCING_DATE'], "%Y%m%d%H")
LENGTH_HRS = int(os.environ['LENGTH_HRS'])


def get_ftime(tm):
    while tm.hour not in [0,6,12,18]:
        tm -= timedelta(hours=1)
    return tm


def download_file(ftime):
    url = ftime.strftime(INURL)
    output = "%s/%s" % (SCRATCHDIR, ftime.strftime("WRF_%Y%m%d%H.nc"))
    print("Looking for %s" % url)

    if os.path.isfile(output):
        return output

    try:
        ret = request.urlretrieve(url, output)
        return output
    except:
        return None


def extract_files(start, ftime, fname):
    index = int((start - ftime).total_seconds()/3600) 

    for i in range(1,abs(LENGTH_HRS)+1):
        tm = start + timedelta(hours=i)

        outfile = OUTDIR + "/" + tm.strftime("wrfout_%Y-%m-%d_%H_island.nc")
        cmd = "ncks -O -d Time,%s %s %s" % ((index + i), fname, outfile)
        os.system(cmd)


def run():
    # find the file we need
    start = DATE
    if LENGTH_HRS < 0:
        start = DATE + timedelta(hours=int(LENGTH_HRS))

    ftime = start
    found = False
    count = 0
    while not found:
        ftime = get_ftime(ftime)
        fname = download_file(ftime)
        if not fname:
            ftime -= timedelta(hours=6)
            count += 1
            if count > 4:
                print("Could not find latest WRF file")
                exit(-1)
            continue
        else:
            found = True

    extract_files(start, ftime, fname)

    
if __name__ == "__main__":
    run()
