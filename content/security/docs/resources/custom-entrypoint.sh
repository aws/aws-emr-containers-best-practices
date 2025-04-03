#!/bin/bash
set -ex

#Set up the chained roled for aws boto3 sdk
generate_aws_config() {

  mkdir -p $HOME/.aws
  # Generate the config file from Spark's env variables
  cat > $HOME/.aws/config << EOF
[profile default]
source_profile=irsa_role
role_arn=${CLIENT_ROLE_ARN}

[profile irsa_role]
web_identity_token_file=/var/run/secrets/eks.amazonaws.com/serviceaccount/token
role_arn=${WEB_IDENTITY_ROLE_ARN}
EOF

  # Set proper permissions
  chmod 600 $HOME/.aws/config
}

generate_aws_config
env

/usr/bin/entrypoint.sh "$@"