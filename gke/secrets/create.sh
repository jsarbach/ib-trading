#!/usr/bin/env bash

gcloud config set project PROJECT_ID

if [[ "$1" == "" ]] || [[ "$2" == "" ]] || [[ "$3" == "" ]]
then
    echo "ERROR: mode, user or password not specified; usage: create.sh MODE USER PASSWORD"
else
    # read the yaml template from a file and replace trading mode, user ID, and password
    template=$(sed "s/{{MODE}}/$1/g;s/{{USER}}/$2/g;s/{{PASSWORD}}/$3/g" < credentials-ib-gateway.template.yaml)

    # apply the yaml with the substituted values
    echo "$template" | kubectl create -f -
fi

kubectl create secret generic firestore-key --from-file key.json=firestore-credentials.json --namespace ib-trading
