import os, sys
from datetime import datetime, timedelta
import re

# get environment vars and command-line args

ECF_HOME = os.environ['ECF_HOME']
JOBDIR = os.environ['WRFHYDRO_JOBDIR']
CYCLE = os.environ['WRFHYDRO_CYCLE']
DOMAIN = os.environ['WRFHYDRO_DOMAIN']

type = sys.argv[1] # hydro hrldas
cycle_date = sys.argv[2] # 20211105
cycle_time = sys.argv[3] # 0000
restart_cycle = sys.argv[4] if len(sys.argv) == 5 else CYCLE

tm = datetime.strptime("%s%s" % (cycle_date, cycle_time), "%Y%m%d%H%M")

indir = "%s/%s/wrfhydro" % (JOBDIR, restart_cycle)

default_restart_dir = "%s/wrfhydro/%s/restarts" % (ECF_HOME, DOMAIN)

if type == "hydro":
    default = "%s/HYDRO_RESTART.default" % default_restart_dir
    pattern = "HYDRO_RST.%Y-%m-%d_%H:%M_DOMAIN"
    regex = "^(HYDRO_RST.\d+\-\d+\-\d+_\d+:\d+_DOMAIN)"
elif type == "hrldas":
    default = "%s/HRLDAS_RESTART.default" % default_restart_dir
    pattern = "RESTART.%Y%m%d%H_DOMAIN"
    regex = "^(RESTART\.\d+_DOMAIN)"

bestfile = None
besttime = None
for file in os.listdir(indir):
    match = re.search(regex, file)
    if not match:
        continue
    try:
        filetime = datetime.strptime(match.groups()[0], pattern)
    except:
        continue
    if filetime > tm:
        continue

    if besttime is None or besttime < filetime:
        besttime = filetime
        bestfile = file


if bestfile is None:
    print(default)
else:
    print("%s/%s" % (indir, bestfile))
