#!/bin/bash
#PBS -N WrfHydroForcing
#PBS -l walltime=00:30:00
#PBS -o wrf_hydro_forcing.out
#PBS -joe
#PBS -k oed
#PBS -l select=2:ncpus=36:mpiprocs=36:mem=109GB

#module purge
#module load intel/18.0.5
#module load impi/2018.4.274
#module load netcdf/4.6.3

PROFILE=`conda info --base`/etc/profile.d/conda.sh

#mpiexec -np 4 python3 -E $FORCING_ROOT_DIR/genForcing.py $FORCING_CONFIG 1.0 $FORCING_CYCLE 
#mpiexec python3 -E $FORCING_ROOT_DIR/genForcing.py $FORCING_CONFIG 1.0 $FORCING_CYCLE 
#CMD="cd $FORCING_ROOT_DIR; source $PROFILE; conda activate wrf-hydro-fe; mpiexec python3 -E ./genForcing.py $FORCING_CONFIG 1.0 $FORCING_CYCLE"
CMD="cd $FORCING_ROOT_DIR; source $PROFILE; conda activate wrf-hydro-fe; python3 -E ./genForcing.py $FORCING_CONFIG 1.0 $FORCING_CYCLE"
echo $CMD

time ssh -tt $WRFHYDRO_NODE "$CMD"

if [ $? != 0 ]; then
    exit -1
fi
