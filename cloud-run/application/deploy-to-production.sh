#!/usr/bin/env bash

PROJECT_ID=
IMAGE="eu.gcr.io/${PROJECT_ID}/cloud-run/application:stable"
if [ "$#" -eq 0 ]; then
  SERVICES=("close-all" "strategy-1" "strategy-2" "summary" "trade-reconciliation")
else
  SERVICES=("$@")
fi

gcloud config set project ${PROJECT_ID}

for service in "${SERVICES[@]}"
do
  gcloud run deploy ${service} --image ${IMAGE} --region europe-west1 --platform managed
done
