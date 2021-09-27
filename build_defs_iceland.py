##############################################################################
# Build the default WRF-Hydro workflow EcFlow definition.
#
##############################################################################

from ecflow import Defs, Suite, Family, Task, Edit, Trigger
from os.path import join
import os

ICELAND_PARAMS = {'CYCLE_DATE': '20210901', 'CYCLE_TIME': '0600'}

FORCING_CONFIGS_DIR = "/glade/work/rcabell/ecflow/hydro-workflow/forcings/src/Config/WCOSS/v2.1"

DOMAINS = {
    'iceland': {
        'name': "ICELAND",
        'params': ICELAND_PARAMS,
        'forcing_configs_dir': FORCING_CONFIGS_DIR,
        'forcing_params_dir': {
            'analysis': "/glade/p/cisl/nwc/nwm_forcings/NWM_v21_Params/AnA",
            'analysis_extended': "/glade/p/cisl/nwc/nwm_forcings/NWM_v21_Params/AnA",
            'analysis_lr': "/glade/p/cisl/nwc/nwm_forcings/NWM_v21_Params/AnA",
            'shortrange': "/glade/p/cisl/nwc/nwm_forcings/NWM_v21_Params/Short_Range",
            'mediumrange': "/glade/p/cisl/nwc/nwm_forcings/NWM_v21_Params/Medium_Range",
            'longrange': "/glade/p/cisl/nwc/nwm_forcings/NWM_v21_Params/Long_Range"
        },
        'forcing_input_dir': "/glade/p/ral/allral/zhangyx/RAP_Conus, /glade/p/ral/allral/zhangyx/HRRR_Conus/",
        'geogrid_file': "/glade/p/cisl/nwc/nwmv20_finals/CONUS/DOMAIN/geo_em.d01.conus_1km_NWMv2.0.nc",
        'spatial_metadata_file': "/glade/p/cisl/nwc/nwmv20_finals/CONUS/DOMAIN/GEOGRID_LDASOUT_Spatial_Metadata_1km_NWMv2.0.nc",
        'cycle_length': {
            'analysis': -3,
            'analysis_noda': -3,
            'analysis_extended': -28,
            'analysis_extended_noda': -28,
            'analysis_lr': -16,
            'analysis_lr_noda': -16,
            'shortrange': 18,
            'shortrange_noda': 18,
            'mediumrange_mem1': 240,
            'mediumrange_mem2': 208,
            'mediumrange_mem3': 208,
            'mediumrange_mem4': 208,
            'mediumrange_mem5': 208,
            'mediumrange_mem6': 208,
            'mediumrange_mem7': 208,
            'mediumrange_noda': 240,
            'longrange_mem1': 720,
            'longrange_mem2': 720,
            'longrange_mem3': 720,
            'longrange_mem4': 720
        }
    }
}

TOP_DIR = os.environ['HOME'] + '/git/wrf_hydro_iceland_workflow'
ECFLOW_DIR = TOP_DIR

WRFHYDRO_JOBDIR = ECFLOW_DIR + '/jobdir'
MODEL_EXE = ECFLOW_DIR + "/wrfhydro/src/trunk/NDHMS/Run/wrf_hydro.exe"

############### Forcing families ##############################

def create_forcings_family(cycle,member=None):
    """
    Create a family of forcing tasks, including coastal forcings if desired.
    Forcing tasks are created for all domains for the requested cycle
    :param cycle: The model cycle (e.g. analysis, shortrange, etc)
    :param member: Ensemble member. Default is None (no ensemble)
    """
    forcings_family = Family("forcings", Edit(WRFHYDRO_CYCLE=cycle, WRFHYDRO_ENSEMBLE_MEM="" if not member else member))
    wrfhydro_cycle = cycle if member is None else f"{cycle}_mem{member}"

    for domain in DOMAINS:
        if wrfhydro_cycle not in DOMAINS[domain]['cycle_length']:
            continue

        params = DOMAINS[domain]['params']
        cycle_length = DOMAINS[domain]['cycle_length'][wrfhydro_cycle]
        configs_dir = DOMAINS[domain]['forcing_configs_dir']
        params_dir = DOMAINS[domain]['forcing_params_dir'][cycle]
        input_dir = DOMAINS[domain]['forcing_input_dir']
        geogrid_file = DOMAINS[domain]['geogrid_file']
        spatial_metadata_file = DOMAINS[domain]['spatial_metadata_file']

        wrfhydro_family = Family(domain,
            Edit(WRFHYDRO_DOMAIN=domain),
            Edit(**params),
            Edit(
                FORCING_CONFIGS_DIR=configs_dir,
                FORCING_PARAMS_DIR=params_dir,
                FORCING_INPUT_DIR=input_dir,
                GEOGRID_FILE=geogrid_file,
                SPATIAL_METADATA_FILE=spatial_metadata_file,
                LENGTH_HRS=cycle_length,
                WRFHYDRO_JOBDIR=join(WRFHYDRO_JOBDIR, domain)))

        wrfhydro_family += Task("wrfhydro_forcings")
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
        params = DOMAINS[domain]['params']

        wrfhydro_family = Family(domain,
            Edit(**params),
            Edit(WRFHYDRO_DOMAIN=domain,WRFHYDRO_JOBDIR=wrfhydro_dir,LENGTH_HRS=cycle_length))

        if requiresCycle:
            wrfhydro_family += Trigger(f"../../{requiresCycle}/wrfhydro_model/{domain}/wrfhydro_model == complete")

        wrfhydro_family += Task("wrfhydro_model", Trigger(f"../../../{forcingsCycle}/forcings/{domain}/wrfhydro_forcings == complete"))

        model_family += wrfhydro_family

    return model_family


###################################### Suite definition ###################

def create_suite():
    """
    Create the suite definition for all model cycles
    """

    defs = Defs(
            Suite("wrf_hydro_iceland",
                  Edit(ECF_HOME=ECFLOW_DIR,
                       ECF_SCRIPT=ECFLOW_DIR + '/ecfs',
                       ECF_FILES=ECFLOW_DIR + '/ecfs',
                       ECF_INCLUDE=ECFLOW_DIR + '/include',
                       PROJ='NRAL0017',
                       QUEUE='regular',
                       WRFHYDRO_JOBDIR=WRFHYDRO_JOBDIR),
                  Family("analysis", create_forcings_family("analysis"), create_model_family("analysis")),
                  Family("analysis_noda", create_model_family("analysis_noda",useda=False,forcingsCycle="analysis")),
                  Family("analysis_extended", create_forcings_family("analysis_extended"),
                         create_model_family("analysis_extended")),
                  Family("analysis_extended_noda",
                         create_model_family("analysis_extended_noda", useda=False, forcingsCycle="analysis_extended")),
                  Family("analysis_lr", create_forcings_family("analysis_lr"),
                         create_model_family("analysis_lr")),
                  Family("analysis_lr_noda",
                         create_model_family("analysis_lr_noda", useda=False, forcingsCycle="analysis_lr")),
                  Family("shortrange", create_forcings_family("shortrange"),
                         create_model_family("shortrange",requiresCycle="analysis", restartCycle="analysis")),
                  Family("shortrange_noda",
                         create_model_family("shortrange_noda",useda=False,requiresCycle="analysis_noda",
                                             restartCycle="analysis_noda", forcingsCycle="shortrange")),
                  Family("mediumrange_mem1", create_forcings_family("mediumrange",member=1),
                         create_model_family("mediumrange",requiresCycle="analysis", restartCycle="analysis", member=1)),
                  Family("mediumrange_mem2", create_forcings_family("mediumrange",member=2),
                         create_model_family("mediumrange", requiresCycle="analysis", restartCycle="analysis", member=2)),
                  Family("mediumrange_mem3", create_forcings_family("mediumrange",member=3),
                         create_model_family("mediumrange", requiresCycle="analysis", restartCycle="analysis", member=3)),
                  Family("mediumrange_mem4", create_forcings_family("mediumrange",member=4),
                         create_model_family("mediumrange", requiresCycle="analysis", restartCycle="analysis", member=4)),
                  Family("mediumrange_mem5", create_forcings_family("mediumrange",member=5),
                         create_model_family("mediumrange", requiresCycle="analysis", restartCycle="analysis", member=5)),
                  Family("mediumrange_mem6", create_forcings_family("mediumrange",member=6),
                         create_model_family("mediumrange", requiresCycle="analysis", restartCycle="analysis", member=6)),
                  Family("mediumrange_mem7", create_forcings_family("mediumrange",member=7),
                         create_model_family("mediumrange", requiresCycle="analysis", restartCycle="analysis", member=7)),
                  Family("mediumrange_noda",
                         create_model_family("mediumrange_noda",useda=False,requiresCycle="analysis_noda",
                                             restartCycle="analysis_noda", forcingsCycle="mediumrange_mem1")),
                  Family("longrange_mem1", create_forcings_family("longrange", member=1),
                         create_model_family("longrange",requiresCycle="analysis_lr", restartCycle="analysis_lr", member=1)),
                  Family("longrange_mem2", create_forcings_family("longrange", member=2),
                         create_model_family("longrange", requiresCycle="analysis_lr", restartCycle="analysis_lr", member=2)),
                  Family("longrange_mem3", create_forcings_family("longrange", member=3),
                         create_model_family("longrange", requiresCycle="analysis_lr", restartCycle="analysis_lr", member=3)),
                  Family("longrange_mem4", create_forcings_family("longrange", member=4),
                         create_model_family("longrange", requiresCycle="analysis_lr", restartCycle="analysis_lr", member=4))
            ))
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
