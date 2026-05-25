# !/bin/bash
salloc -p copy --nodes=1 --ntasks=3 --cpus-per-task=8 --mem=20G --time=02:00:00 --job-name=data_out_webviz

module load rclone/1.68.1

rclone copy $MYSCRATCH/vz_kerchunk jchew:webviz \
         --progress \
         --transfers 24 \
         --checkers 24

# Verify transfer success
rclone ls jchew:webviz | head -n 20