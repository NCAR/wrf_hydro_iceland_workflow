#!/bin/bash -l
#PBS -N wrf_hydro.exe
#PBS -l walltime=02:00:00
#PBS -o wrf_hydro_exe.out
#PBS -joe
#PBS -k oed
#PBS -l select=2:ncpus=72:mpiprocs=72

# UNCOMMENT TO USE GFORTRAN BUILD OF WRF-HYDRO
# source /glade/u/apps/ch/modulefiles/default/localinit/localinit.sh
# module swap intel gnu/10
# module load mpt

#module load intel/18.0.5
#module load impi/2018.4.274

export MPI_IB_CONGESTED=0

#time mpiexec $WRF_HYDRO_ROOT/wrf_hydro.exe
time ssh -tt $WRFHYDRO_NODE "cd $WRF_HYDRO_ROOT; mpiexec -np 32 ./wrf_hydro.exe"
#time ssh -tt $WRFHYDRO_NODE "cd $WRF_HYDRO_ROOT; ./wrf_hydro.exe"
