#!/bin/bash
set -e

zip -r assets/assets.zip . -x "zip_assets.sh" "tmp_local_cfn_deploy.sh" "cdk/cdk.out/*" "cdk/node_modules/*" ".git/*" "assets/"

echo "Assets zipped"