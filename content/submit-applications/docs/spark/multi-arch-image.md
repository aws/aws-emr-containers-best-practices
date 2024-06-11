# Build a Multi-architecture Docker Image Supporting arm64 & amd64

## Pre-requisites
We can complete all the steps either from a local desktop or using [AWS Cloud9](https://aws.amazon.com/cloud9/).  If you’re using AWS Cloud9, follow the instructions in the "Setup AWS Cloud9" to create and configure the environment first, otherwise skip to the next section.

## Setup AWS Cloud9
AWS Cloud9 is a cloud-based IDE that lets you write, run, and debug your code via just a browser. AWS Cloud9 comes preconfigured with some of AWS dependencies we require to build our application, such ash the AWS CLI tool.

### 1. Create a Cloud9 instance

**Instance type** - Create an AWS Cloud9 environment from the [AWS Management Console](https://console.aws.amazon.com/cloud9) with an instance type of `t3.small or larger`. In our example, we used `m5.xlarge` for adequate memory and CPU to compile and build a large docker image. 

**VPC** - Follow the launch wizard and provide the required name. To interact with an existing EKS cluster in the same region later on, recommend to use the same VPC to your EKS cluster in the Cloud9 environment. Leave the remaining default values as they are. 

**Storage size** - You must increase the Cloud9's EBS volume size (pre-attached to your AWS Cloud9 instance) to 30+ GB, because the default disk space ( 10 GB with ~72% used) is not enough for building a container image. Refer to [Resize an Amazon EBS volume used by an environment](https://docs.aws.amazon.com/cloud9/latest/user-guide/move-environment.html#move-environment-resize) document, download the script `resize.sh` to your cloud9 environment.

```bash
touch reaize.sh
# Double click the file name in cloud9
# Copy and paste the content from the official document to your file, save and close it
```
Validate the disk size is 10GB currently:
```
admin:~/environment $ df -h
Filesystem        Size  Used Avail Use% Mounted on
devtmpfs          4.0M     0  4.0M   0% /dev
tmpfs             951M     0  951M   0% /dev/shm
tmpfs             381M  5.3M  376M   2% /run
/dev/nvme0n1p1     10G  7.2G  2.9G  72% /
tmpfs             951M   12K  951M   1% /tmp
/dev/nvme0n1p128   10M  1.3M  8.7M  13% /boot/efi
tmpfs             191M     0  191M   0% /run/user/1000
```
Increase the disk size:
```bash
bash resize.sh 30
```
```
admin:~/environment $ df -h
Filesystem        Size  Used Avail Use% Mounted on
devtmpfs          4.0M     0  4.0M   0% /dev
tmpfs             951M     0  951M   0% /dev/shm
tmpfs             381M  5.3M  376M   2% /run
/dev/nvme0n1p1     30G  7.3G   23G  25% /
tmpfs             951M   12K  951M   1% /tmp
/dev/nvme0n1p128   10M  1.3M  8.7M  13% /boot/efi
tmpfs             191M     0  191M   0% /run/user/1000
```

### 2. Install Docker and Buildx if required

- **Installing Docker** - a Cloud9 EC2 instance comes with a Docker daemon pre-installed. Outside of the Cloud9, your environment may or may not need to install Docker. If needed, follow the instructions in the [Docker Desktop page](https://docs.docker.com/desktop/#download-and-install) to install.


- **Installing Buildx** (pre-installed in Cloud9) - To build a single multi-arch Docker image (x86_64 and arm64), we may or may not need to [install an extra Buildx plugin](https://docs.docker.com/build/architecture/#install-buildx) that extends the Docker CLI to support the multi-architecture feature. Docker Buildx is installed by default with a Docker Engine since **version 23.0+**. For an earlier version, it requires you grab a binary from GitHub repository and install it manually, or get it from a separate package. See [docker/buildx README](https://github.com/docker/buildx#manual-download) for more information. 

Once the buildx CLI is available, we can create a builder instance which gives access to the new multi-architecture features.You only have to perform this task once.
```bash
# create a builder
docker buildx create --name mybuilder --use
# boot up the builder and inspect
docker buildx inspect --bootstrap


# list builder instances
# the asterisk (*) next to a builder name indicates the selected builder.
docker buildx ls
```
If your builder doesn't support [QEMU](https://docs.docker.com/build/building/multi-platform/#qemu), only limited platform types are supported as below. For example, the current builder instance created in Cloud9 doesn't support QEMU, so we can't build the docker image for the arm64 CPU type yet. 
```bash
NAME/NODE       DRIVER/ENDPOINT      STATUS   BUILDKIT PLATFORMS
default        docker
default       default              running  v0.11.6  linux/amd64, linux/amd64/v2, linux/amd64/v3, linux/386
mybuilder *    docker-container
my_builder0   default              running  v0.11.6  linux/amd64, linux/amd64/v2, linux/amd64/v3, linux/386
```

- **Installing QEMU for Cloud9** - Building multi-platform images under emulation with QEMU is the easiest way to get started if your builder already supports it. However, AWS Cloud9 isn't preconfigured with the [binfmt_misc](https://en.wikipedia.org/wiki/Binfmt_misc) support. We must install compiled QEMU binaries.  The installations can be easily done via the docker run CLI:
```bash
 docker run --privileged --rm tonistiigi/binfmt --install all
```
List the builder instance again. Now we see the full list of platforms are supported,including arm-based CPU:
```bash
docker buildx ls

NAME/NODE     DRIVER/ENDPOINT             STATUS   BUILDKIT PLATFORMS
mybuilder *   docker-container                              
  mybuilder20 unix:///var/run/docker.sock running  v0.13.2  linux/amd64, linux/amd64/v2, linux/amd64/v3, linux/amd64/v4, linux/arm64, linux/riscv64, linux/ppc64le, linux/s390x, linux/386, linux/mips64le, linux/mips64, linux/arm/v7, linux/arm/v6     
default       docker                                        
  default     default                     running  v0.12.5  linux/amd64, linux/amd64/v2, linux/amd64/v3, linux/amd64/v4, linux/386, linux/arm64, linux/riscv64, linux/ppc64le, linux/s390x, linux/mips64le, linux/mips64, linux/arm/v7, linux/arm/v6
```

## Build a docker image supporting multi-arch

In this example, we will create a [spark-benchmark-utility](https://github.com/aws-samples/emr-on-eks-benchmark) container image. We are going to reuse the source code from the [EMR on EKS benchmark Github repo](https://github.com/aws-samples/emr-on-eks-benchmark).

### 1. Download the source code from the Github:
```bash
git clone https://github.com/aws-samples/emr-on-eks-benchmark.git
cd emr-on-eks-benchmark
```

### 2. Setup required environment variables

We will build an image to test EMR 6.15's performance. The equivalent versions are Spark 3.4.1 and Hadoop 3.3.4. Change them accordingly if needed.
```bash
export SPARK_VERSION=3.4.1
export HADOOP_VERSION=3.3.6
```

Log in to your own Amazon ECR registry: 
```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR_URL=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URL
```

### 3. Build OSS Spark base image if required
If you want to test open-source Apache Spark's performance, build a base Spark image first. Otherwise skip this step.
```bash
docker buildx build --platform linux/amd64,linux/arm64 \
-t $ECR_URL/spark:$SPARK_VERSION_hadoop_$HADOOP_VERSION \
-f docker/hadoop-aws-3.3.1/Dockerfile \
--build-arg HADOOP_VERSION=$HADOOP_VERSION --build-arg SPARK_VERSION=$SPARK_VERSION --push .
```

### 4. Get EMR Spark base image from AWS
```bash
export SRC_ECR_URL=755674844232.dkr.ecr.us-east-1.amazonaws.com
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $SRC_ECR_URL

docker pull $SRC_ECR_URL/spark/emr-6.15.0:latest
```


### 5. Build the Benchmark Utility image

Build and push the docker image based the OSS Spark engine built before (Step #3):

```bash

docker buildx build --platform linux/amd64,linux/arm64 \
-t $ECR_URL/spark:$SPARK_VERSION_hadoop_$HADOOP_VERSION \
-f docker/benchmark-util/Dockerfile \
--build-arg SPARK_BASE_IMAGE=$ECR_URL/spark:$SPARK_VERSION_hadoop_$HADOOP_VERSION \
--push .
```

Build and push the benchmark docker image based EMR's Spark runtime (Step #4):

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
-t $ECR_URL/eks-spark-benchmark:emr6.15 \
-f docker/benchmark-util/Dockerfile \
--build-arg SPARK_BASE_IMAGE=$SRC_ECR_URL/spark/emr-6.15.0:latest \
--push .

```

## Benchmark application based on the docker images built

Based on the mutli-arch docker images built previously, now you can start to [run benchmark applications](https://github.com/aws-samples/emr-on-eks-benchmark/tree/delta?tab=readme-ov-file#run-benchmark) on both intel and arm-based CPU nodes.

In Cloud9, the following extra steps are required to configure the environment, before you can submit the applications. 

1. Install kkubectl/helm/eksctl CLI tools. refer to this [sample scirpt](https://github.com/aws-samples/stream-emr-on-eks/blob/workshop/deployment/app_code/post-deployment.sh)

2. Modify the IAM role attached to the Cloud9 EC2 instance, allowing it has enough privilege to assume an EKS cluster's admin role or has the permission to submit jobs against the EKS cluster.

3. Upgrade AWS CLI and turn off the AWS managed temporary credentials in Cloud9:
```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install --update
/usr/local/bin/aws cloud9 update-environment  --environment-id $C9_PID --managed-credentials-action DISABLE
rm -vf ${HOME}/.aws/credentials
```

4. Connect to the EKS cluster
```bash
# a sample connection string
aws eks update-kubeconfig --name YOUR_EKS_CLUSTER_NAME --region us-east-1 --role-arn arn:aws:iam::ACCOUNTID:role/SparkOnEKS-iamrolesclusterAdmin-xxxxxx

# validate the connection
kubectl get svc
```
