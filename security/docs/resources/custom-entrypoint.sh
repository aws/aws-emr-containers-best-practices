#!/bin/bash

set -ex

#Set up the chained roled for aws boto3 sdk
generate_aws_config() {
  # Create a .aws directory in the user's home directory
    mkdir -p $HOME/.aws

  # Generate the config file from environment variables
  cat > $HOME/.aws/config << EOF
[default]
region=${REGION}
role_arn=${ROLE_2_ARN}
role_session_name=client_role
source_profile=irsa-role

[profile irsa-role]
region=${REGION}
web_identity_token_file=/var/run/secrets/eks.amazonaws.com/serviceaccount/token
role_arn=${ROLE_1_ARN}
EOF

  # Set proper permissions
  chmod 600 $HOME/.aws/config
}

# Function to generate credentials
generate_aws_credentials() {
    echo "Generating AWS credentials at $(date)"
    
    # Get credentials using web identity token
    credentials=$(aws sts assume-role-with-web-identity \
        --role-arn ${ROLE_1_ARN} \
        --role-session-name webidentity-session \
        --web-identity-token "$(cat /var/run/secrets/eks.amazonaws.com/serviceaccount/token)" \
        --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken,Expiration]' \
        --output text)

    # Create .aws directory
    mkdir -p $HOME/.aws

    # Generate the credentials file
    cat > $HOME/.aws/credentials << EOF
[default]
source_profile=irsa-role
role_arn=${ROLE_2_ARN}
role_session_name=client_role

[irsa-role]
aws_access_key_id=$(echo $credentials | awk '{print $1}')
aws_secret_access_key=$(echo $credentials | awk '{print $2}')
aws_session_token=$(echo $credentials | awk '{print $3}')
EOF

    chmod 600 $HOME/.aws/credentials
    
    # Extract expiration time for next refresh
    expiration=$(echo $credentials | awk '{print $4}')
    echo "Credentials will expire at: $expiration"
}

# Function to start credential refresh daemon
start_credential_refresh_daemon() {
    while true; do
        generate_aws_credentials
        
        # Sleep for 80% of the default 1-hour credential duration (refresh the token every 48 minutes)
        sleep 2880
        # # test 10mins for testing
        # sleep 600

        # Check if the token file still exists and is readable
        if [ ! -r "/var/run/secrets/eks.amazonaws.com/serviceaccount/token" ]; then
            echo "Token file not accessible. Stopping refresh daemon."
            exit 1
        fi
    done
}

generate_aws_config
# NOTE: the IRSA env variable "AWS_ROLE_ARN" must be reset 
# To trigger the access deny 403 while evaluating WebIdentity credential
# As a result of the RESET, it forces SDK applications to use the next Profile provider () in the AWS DefaultCredentialChain 
export AWS_ROLE_ARN=$ROLE_2_ARN
export AWS_WEB_IDENTITY_TOKEN_FILE=/var/run/secrets/eks.amazonaws.com/serviceaccount/token

# Start the refresh daemon in the background
start_credential_refresh_daemon &
DAEMON_PID=$!
echo $DAEMON_PID > /tmp/credential-refresh.pid
# Set up trap to clean up the daemon on script exit
trap "kill $DAEMON_PID 2>/dev/null" EXIT

/usr/bin/entrypoint.sh "$@"