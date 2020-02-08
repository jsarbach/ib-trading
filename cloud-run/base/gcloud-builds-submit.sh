#!/usr/bin/env bash

PROJECT_ID=

gcloud config set project ${PROJECT_ID}

gcr="eu.gcr.io/${PROJECT_ID}/cloud-run/base"

gcloud builds submit --gcs-source-staging-dir gs://${PROJECT_ID}-cloudbuild/source --tag "$gcr":latest .

for arg
do
  yes | gcloud container images add-tag "$gcr":latest "$gcr":"$arg"
done
