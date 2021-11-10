##############################################################################
# Build the default WRF-Hydro workflow EcFlow definition.
#
##############################################################################

from ecflow import Defs, Suite, Family, Task, Edit, Trigger, Time, Date 
from os.path import join
import os

ICELAND_PARAMS = {'CYCLE_DATE': '20211009', 'CYCLE_TIME': '0000'}

# realtime or archive
RUN_MODE = "realtime"

TOP_DIR = os.environ['HOME'] + '/git/wrf_hydro_iceland_workflow'
FORCING_DIR = os.environ['HOME'] + '/git/WrfHydroForcing'
ECFLOW_DIR = TOP_DIR

WRFHYDRO_JOBDIR = ECFLOW_DIR + '/jobdir'
MODEL_EXE = ECFLOW_DIR + "/wrfhydro/wrf_hydro_NoahMP.exe"

DOMAINS = {
    'iceland': {
        'name': "ICELAND",
        'cycle_length': {
            'analysis': -3,
            'shortrange': 24,
            'mediumrange': 240,
            'longrange': 720
        }
    }
}

HYDROINSPECTOR_HOST = "hydro-c1-content.rap.ucar.edu"
HYDROINSPECTOR_DIR = "/d5/hydroinspector_data/tmp/iceland"


############### Forcing families ##############################

def create_forcings_family(cycle,member=None):
    """
    Create a family of forcing tasks
    Forcing tasks are created for all domains for the requested cycle
    :param cycle: The model cycle (e.g. analysis, shortrange, etc)
    :param member: Ensemble member. Default is None (no ensemble)
    """
    forcings_family = Family("forcings", Edit(WRFHYDRO_CYCLE=cycle, WRFHYDRO_ENSEMBLE_MEM="" if not member else member))
    wrfhydro_cycle = cycle if member is None else f"{cycle}_mem{member}"

    for domain in DOMAINS:
        if wrfhydro_cycle not in DOMAINS[domain]['cycle_length']:
            continue

        cycle_length = DOMAINS[domain]['cycle_length'][wrfhydro_cycle]

        wrfhydro_family = Family(domain,
            Edit(WRFHYDRO_DOMAIN=domain),
            Edit(
                FORCING_DIR=FORCING_DIR,
                LENGTH_HRS=cycle_length,
                WRFHYDRO_JOBDIR=join(WRFHYDRO_JOBDIR, domain)))
        
        if 'params' in DOMAINS[domain]:
            wrfhydro_family += Edit(**DOMAINS[domain]['params'])

        wrfhydro_family += Task("wrfhydro_forcings", Trigger(f"../../data_pull/{domain}/data_pull == complete"))
        forcings_family += wrfhydro_family

    return forcings_family


###################### Model families ##################################


def create_model_family(cycle,useda=True,requiresCycle=None, restartCycle=None,
                        member=None, forcingsCycle=None):
    """
    Create a family of tasks for running WRFHYDRO.
    :param cycle: The model cycle (e.g. analysis, shortrange, etc)
    :param useda: If True, use Data Assimilation. Default is True
    :param requiresCycle: If not None, set up a trigger to wait for the required cycle's WRFHYDRO task to complete.
                          Default is None
    :param restartCycle: The name of the cycle to get RESTART files from. If None, use RESTARTS from the current cycle.
                          Default is None
    :param forcingsCycle: Forcings are used from this cycle instead of the current cycle. Default is None (use forcings
                            from the current cycle)
    :param member: Ensemble member. Default is None (no ensemble)
    """
    if forcingsCycle is None:
        forcingsCycle = cycle + ("" if member is None else f"_mem{member}")
    if restartCycle is None:
        restartCycle = ""

    wrfhydro_cycle = cycle if member is None else f"{cycle}_mem{member}"

    model_family = Family("wrfhydro_model")
    model_family += Edit(WRFHYDRO_CYCLE=cycle, WRFHYDRO_BASE_CYCLE=forcingsCycle, MODEL_EXECUTABLE=MODEL_EXE,
        WRFHYDRO_RESTART_CYCLE=restartCycle)
    model_family += Edit(USE_DA="true" if useda else "false")
    model_family += Edit(WRFHYDRO_ENSEMBLE_MEM="" if not member else member)

    for domain in DOMAINS:
        if wrfhydro_cycle not in DOMAINS[domain]['cycle_length']:
            continue

        cycle_length = DOMAINS[domain]['cycle_length'][wrfhydro_cycle]
        wrfhydro_dir = join(WRFHYDRO_JOBDIR, domain)

        wrfhydro_family = Family(domain,
            Edit(WRFHYDRO_DOMAIN=domain,WRFHYDRO_JOBDIR=wrfhydro_dir,LENGTH_HRS=cycle_length))

        if 'params' in DOMAINS[domain]:
            wrfhydro_family += Edit(**DOMAINS[domain]['params'])

        if requiresCycle:
            wrfhydro_family += Trigger(f"../../{requiresCycle}/wrfhydro_model/{domain}/wrfhydro_model == complete")

        wrfhydro_family += Task("wrfhydro_model", Trigger(f"../../../{forcingsCycle}/forcings/{domain}/wrfhydro_forcings == complete"))

        model_family += wrfhydro_family

    return model_family


###################### Data families ##################################

def create_data_pull_family(cycle):
    """
    """
    data_pull_family = Family("data_pull")
    data_pull_family += Edit(WRFHYDRO_CYCLE=cycle)

    for domain in DOMAINS:
        domain_family = Family(domain,
            Edit(WRFHYDRO_DOMAIN=domain)
        )

        if 'params' in DOMAINS[domain]:
            domain_family += Edit(**DOMAINS[domain]['params'])

        cycle_length = DOMAINS[domain]['cycle_length'][cycle]
        domain_family += Edit(LENGTH_HRS=cycle_length)

        domain_family += Task("data_pull")

        data_pull_family += domain_family

    return data_pull_family
    


def create_data_push_family(cycle, member=None):
    """
    """
    wrfhydro_cycle = cycle if member is None else f"{cycle}_mem{member}"

    data_push_family = Family("data_push")
    data_push_family += Edit(WRFHYDRO_CYCLE=wrfhydro_cycle,HYDROINSPECTOR_HOST=HYDROINSPECTOR_HOST,
        HYDROINSPECTOR_DIR=HYDROINSPECTOR_DIR)

    for domain in DOMAINS:
        if wrfhydro_cycle not in DOMAINS[domain]['cycle_length']:
            continue

        cycle_length = DOMAINS[domain]['cycle_length'][wrfhydro_cycle]
        jobdir = join(WRFHYDRO_JOBDIR, domain)
        domain_family = Family(domain,
            Edit(WRFHYDRO_DOMAIN=domain, WRFHYDRO_JOBDIR=jobdir,LENGTH_HRS=cycle_length),
            Trigger(f"../wrfhydro_model/{domain}/wrfhydro_model == complete")
        )

        if 'params' in DOMAINS[domain]:
            domain_family += Edit(**DOMAINS[domain]['params'])

        domain_family += Task("data_push")

        data_push_family += domain_family

    return data_push_family


###################### Suite definition ################################

def create_suite():
    """
    Create the suite definition for all model cycles
    """

    params = ICELAND_PARAMS

    analysis = Family("analysis", Edit(**params),create_data_pull_family("analysis"), create_forcings_family("analysis"),
            create_model_family("analysis", useda=False), create_data_push_family("analysis"))
    shortrange = Family("shortrange", Edit(**params),create_data_pull_family("shortrange"), create_forcings_family("shortrange"),
                 create_model_family("shortrange", requiresCycle="analysis", restartCycle="analysis", useda=False), 
                 create_data_push_family("shortrange"))
    mediumrange = Family("mediumrange", Edit(**params),create_data_pull_family("mediumrange"), create_forcings_family("mediumrange"),
                 create_model_family("mediumrange", requiresCycle="analysis", restartCycle="analysis", useda=False), 
                 create_data_push_family("mediumrange"))
    longrange = Family("longrange", Edit(**params),create_data_pull_family("longrange"), create_forcings_family("longrange"),
                 create_model_family("longrange", requiresCycle="analysis", restartCycle="analysis", useda=False),
                 create_data_push_family("longrange"))

    if RUN_MODE == "realtime":
        analysis += Time("00:00 23:00 01:00") 
        analysis += Date("*.*.*")
        analysis += Edit(LATENCY=2)
        shortrange += Time("02:00 20:00 06:00")
        shortrange += Date("*.*.*")
        shortrange += Edit(LATENCY=8)
        mediumrange += Time("02:00 20:00 06:00")
        mediumrange += Date("*.*.*")
        mediumrange += Edit(LATENCY=8)
        longrange += Time("02:00 20:00 06:00")
        longrange += Date("*.*.*")
        longrange += Edit(LATENCY=8)

    defs = Defs(
        Suite("wrf_hydro_iceland",
          Edit(ECF_HOME=ECFLOW_DIR,
               ECF_SCRIPT=ECFLOW_DIR + '/ecfs',
               ECF_FILES=ECFLOW_DIR + '/ecfs',
               ECF_INCLUDE=ECFLOW_DIR + '/include',
               PROJ='p48500028',
               QUEUE='regular',
               RUN_MODE=RUN_MODE,
               WRFHYDRO_JOBDIR=WRFHYDRO_JOBDIR),
          analysis,
          shortrange,
          mediumrange,
          longrange
        )
    )

    print(defs)

    print("Checking trigger expression")
    check = defs.check()
    assert len(check) == 0, check

    print("Checking job creation: .ecf -> .job0")
    print(defs.check_job_creation())

    print("Saving definition to file 'defs/iceland.def'")
    defs.save_as_defs("defs/iceland.def")


if __name__ == '__main__':
    create_suite()
