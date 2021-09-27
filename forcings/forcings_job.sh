#!/bin/bash
#PBS -N WrfHydroForcing
#PBS -l walltime=00:30:00
#PBS -o wrf_hydro_forcing.out
#PBS -joe
#PBS -k oed
#PBS -l select=2:ncpus=36:mpiprocs=36:mem=109GB

# REQUIRED ENVIRONMENT VARIABLE INPUTS:
# $FORCING_ROOT_DIR      -- root directory of Forcing Engine
# $FORCING_CONFIG        -- configuration to use in [analysis, shortrange, mediumrange, longrange]
# $FORCING_CONFIGS_DIR   -- directory containing FE configuration files
# $FORCING_PARAMS_DIR    -- directory containing downscaling parameter files
# $FORCING_INPUT_DIR     -- directory containing meteorological input
# $FORCING_PCP_INPUT_DIR -- directory containing supplemental precipitation input
# $FORCING_SCRATCH_DIR   -- directory to place temporary files
# $FORCING_OUTPUT_DIR    -- directory to place output files
# $GEOGRID_FILE          -- WRF-Hydro hydrofabric geogrid file
# $SPATIAL_METADATA_FILE -- WRF-Hydro hydrofabric spatial metadata template file
# $FORCING_BEGIN_DATE    -- Beginning datetime of forcings (YYYYMMDDHHmm format)
# $FORCING_END_DATE      -- Ending datetime of forcings (YYYYMMDDHHmm format)



# select configuration
case "$FORCING_CONFIG" in 
iceland-analysis)
    echo "==== STARTING ICELAND ANA FORCINGS ===="
    config_tag=AnA
    config_base=$FORCING_CONFIGS_DIR/template_forcing_engine_Analysis.config
    ;;
iceland-shortrange)
    echo "==== STARTING ICELAND SHORT-RANGE FORCINGS ===="
    config_tag=short_range
    config_base=$FORCING_CONFIGS_DIR/template_forcing_engine_Short.config
    ;;
iceland-mediumrange)
    echo "==== STARTING ICELAND MEDIUM-RANGE FORCINGS ===="
    config_tag=medium_range
    config_base=$FORCING_CONFIGS_DIR/template_forcing_engine_Medium.config
    ;;
iceland-longrange)
    echo "==== STARTING ICELAND LONG-RANGE FORCINGS ===="
    config_tag=long_range
    config_base=$FORCING_CONFIGS_DIR/template_forcing_engine_Long.config
    ;;
*)
    echo "=**= ERROR: UNKNOWN FORCING CONFIGURATION! =**="
    exit 1
    ;;
esac

feconfig=$FORCING_SCRATCH_DIR/wrf_hydro_forcing.config
cp $config_base $feconfig

# template the forecast times with SED
sed -i "s|^OutDir .*|OutDir = ${FORCING_OUTPUT_DIR}|;" ${feconfig}
sed -i "s|^ScratchDir .*|ScratchDir = ${FORCING_SCRATCH_DIR}|;" ${feconfig}
sed -i "s|^InputForcingDirectories .*$|InputForcingDirectories = ${FORCING_INPUT_DIR}|;" ${feconfig}
sed -i "s|^SuppPcpDirectories .*$|SuppPcpDirectories = ${FORCING_PCP_INPUT_DIR}|;" ${feconfig}
sed -i "s|^GeogridIn .*|GeogridIn = ${GEOGRID_FILE}|;" ${feconfig}
sed -i "s|^SpatialMetaIn .*|SpatialMetaIn = ${SPATIAL_METADATA_FILE}|;" ${feconfig}
sed -i "s|^DownscalingParamDirs .*$|DownscalingParamDirs = ${FORCING_PARAMS_DIR}|;" ${feconfig}
sed -i "s|^SuppPcpParamDir .*$|SuppPcpParamDir = ${FORCING_PARAMS_DIR}|;" ${feconfig}
sed -i "s|^RefcstBDateProc .*|RefcstBDateProc = ${FORCING_BEGIN_DATE}|;" ${feconfig}
sed -i "s|^RefcstEDateProc .*|RefcstEDateProc = ${FORCING_END_DATE}|;" ${feconfig}
sed -i "s|^BDateProc .*|BDateProc = ${FORCING_BEGIN_DATE}|;" ${feconfig}
sed -i "s|^EDateProc .*|EDateProc = ${FORCING_END_DATE}|;" ${feconfig}

# Temporary fix:
# TODO: handle this better!
sed -i "s|^InputForcingTypes .*|InputForcingTypes = GRIB2, GRIB2|;" ${feconfig}


module purge
module load intel/18.0.5
module load impi/2018.4.274
module load netcdf/4.6.3

source ${FORCING_PYTHON_VENV:-/glade/p/cisl/nwc/rcabell/mfe_venv}/bin/activate
mpiexec python3 -E $FORCING_ROOT_DIR/src/genForcing.py $feconfig ${NWM_VERSION:-3.0} $config_tag 
