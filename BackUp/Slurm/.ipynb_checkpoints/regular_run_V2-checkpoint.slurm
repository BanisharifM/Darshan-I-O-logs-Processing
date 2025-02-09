#!/bin/bash
#SBATCH --job-name=my_job_name              # Job name
#SBATCH --output=my_job_output_%j.out       # Output file (%j expands to jobId)
#SBATCH --error=my_job_error_%j.err         # Error file (%j expands to jobId)
#SBATCH --ntasks=1                          # Number of tasks (usually 1 for GPU jobs)
#SBATCH --cpus-per-task=16                  # Number of CPU cores per task (adjust as needed)
#SBATCH --mem=128g                           # Total memory per node (adjust as needed)
#SBATCH --time=24:00:00                     # Maximum time limit hrs:min:sec
#SBATCH --partition=gpuA100x8               # Partition name
#SBATCH --gres=gpu:1                        # Number of GPUs per node
#SBATCH --account=bdau-delta-gpu            # Account name

# Load necessary modules
module load python/3.11.6
module load cuda/11.8                       # Load CUDA 11.8

# Source the virtual environment, instead of executing
source ~/env4/bin/activate

# Verify Python executable
which python

# Print some information about the job
echo "Job started on $(date)"
echo "Running on node $(hostname)"
echo "Using the following GPUs:"
nvidia-smi

# Run your Python script
python /u/mbanisharifdehkordi/Github/GNN_4_IO/gnn_training121.py

# Print job end time
echo "Job ended on $(date)"
