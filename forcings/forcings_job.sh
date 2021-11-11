#!/bin/bash
#PBS -N WrfHydroForcing
#PBS -l walltime=00:30:00
#PBS -o wrf_hydro_forcing.out
#PBS -joe
#PBS -k oed
#PBS -l select=2:ncpus=36:mpiprocs=36:mem=109GB

module purge
module load intel/18.0.5
module load impi/2018.4.274
module load netcdf/4.6.3

source ${FORCING_PYTHON_VENV:-/glade/p/cisl/nwc/rcabell/mfe_venv}/bin/activate
mpiexec python3 -E $FORCING_ROOT_DIR/genForcing.py $FORCING_CONFIG 1.0 $FORCING_CYCLE 

if [ $? != 0 ]; then
    exit -1
fi
