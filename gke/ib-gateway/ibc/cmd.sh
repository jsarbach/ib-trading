#!/bin/bash -e

# parse complete Java path and TWS version number
JAVA_PATH=${JAVA_PATH_ROOT}/$(ls "${JAVA_PATH_ROOT}")/bin
export JAVA_PATH
TWS_MAJOR_VRSN=$(grep -Eo "IB Gateway [0-9]{3}" < "${TWS_INSTALL_LOG}" | head -n 1 | cut -d" " -f3)
export TWS_MAJOR_VRSN

echo "Starting Xvfb..."
Xvfb "$DISPLAY" -ac -screen 0 1024x768x16 +extension RANDR &
sleep 1

echo "Starting IB gateway..."
${IBC_PATH}/scripts/displaybannerandlaunch.sh &
# Give enough time to start up
sleep 30

echo "Forking :::4001 onto 0.0.0.0:4003..."
socat TCP-LISTEN:4003,reuseaddr,fork TCP:127.0.0.1:4001
