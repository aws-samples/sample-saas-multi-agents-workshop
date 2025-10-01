#!/bin/bash -e

shopt -s expand_aliases
source ~/.bashrc

# Silent function to check if modules are installed
check_modules_installed() {
    python3 -c "
import boto3, bedrock_agentcore_starter_toolkit, bedrock_agentcore, rich, jwt, requests
" 2>/dev/null
    return $?
}

# Only install if modules are not already available
if ! check_modules_installed; then
    pip3 install -r agentcore-provisioning/requirements.txt
fi

python3 agent-repl.py
