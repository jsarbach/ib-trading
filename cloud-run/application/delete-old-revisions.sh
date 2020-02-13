#!/usr/bin/env bash

PROJECT_ID=
# number of inactive revisions to keep
KEEP=1

gcloud config set project ${PROJECT_ID}

SERVICES=($(gcloud run services list --format json | jq -r '.[].metadata.name'))
for service in "${SERVICES[@]}"
do
  REVISIONS=($(gcloud run revisions list --service ${service} --filter 'status.conditions.status=False AND status.conditions.type=Active' --sort-by ~metadata.name --format json | jq -r '.[].metadata.name'))
  for revision in "${REVISIONS[@]:$KEEP}"
  do
    yes | gcloud run revisions delete "${revision}" --region europe-west1 --platform managed
  done
done
