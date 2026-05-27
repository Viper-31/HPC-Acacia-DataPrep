# !/bin/bash
salloc -p copy --nodes=1 --ntasks=3 --cpus-per-task=8 --mem=40G --time=02:00:00 --job-name=data_out_webviz

module load rclone/1.68.1

# dry-run first
rclone copy $MYSCRATCH/kerchunk_webviz jchew:webviz --include "/DPIRD/**" --include "/ECMWF/2024/*" --dry-run -v

# full transfer

rclone copy $MYSCRATCH/kerchunk_webviz jchew:webviz \
         --include "/DPIRD/**" \
         --include "/ECMWF/2024/**" \
         --progress \
         --transfers 24 \
         --checkers 24 \
         -v

# Verify transfer success
rclone ls jchew:webviz | head -n 20

exit