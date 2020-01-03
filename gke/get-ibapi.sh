#!/usr/bin/env bash

# download and extract IB Python API (see http://interactivebrokers.github.io/)
wget -O ./ibapi.zip http://interactivebrokers.github.io/downloads/twsapi_macunix.976.01.zip
unzip ./ibapi.zip -d ./tmp
mv -f ./tmp/IBJts/source/pythonclient/ibapi ./

# copy into subdirectories so that Docker build can use it
cp -r ./ibapi ./allocator/
cp -r ./ibapi ./ib-gateway/healthcheck/
cp -r ./ibapi ./strategy-api/

# clean up
rm -rf ./tmp ./ibapi.zip
