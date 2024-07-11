# **Connect to SparkUI without Port Fowarding**

This is an example of connecting to SparkUI running on Spark's driver pod via a reserve proxy solution, without an access to the kubectl tool or AWS console. We demostrate how to set it up via three EMR on EKS deployment methods: Spark Operator, JobRun API, and spark-submit.

## Launch EMR on EKS jobs via Spark Operator

There are 3 Steps to set up in EKS:

1. Create a SparkUI reverse proxy and an ALB first. 

The sample yaml file is in the [Appendix](#deployment.yaml). Make sure the EMR on EKS namespace at line #25 is updated by your namespace:
```bash
kubectl apply -f deployment.yaml
```
<div style="border: 1px solid red; padding: 10px; background-color: #f8d7da;">
  <strong>NOTE:</strong> The example file is not production ready. The listen port 80 is not recommended. Make sure to stronger your Application Load Balance's security posture before deploy it to your production environment.
</div>

2. Submit 2 test jobs using EMR on EKS's Spark Operator. Check out the sample job file [emr-eks-spark-example-01.yaml](#emr-eks-spark-example-01yaml) and [emr-eks-spark-example-02.yaml](#emr-eks-spark-example-02yaml) in the Appendix section.

Remember to specify the Spark configuration at line #16 **spark.ui.proxyBase: /sparkui/YOUR_SPARK_APP_NAME**, eg. `spark.ui.proxyBase: /sparkui/test-02`.
```bash
kubectl apply -f emr-eks-spark-example-01.yaml
kubectl apply -f emr-eks-spark-example-02.yaml
```
3. Go to a web browser, then access their Spark Web UI while jobs are still running:

```
http://k8s-default-sparkui-2d325c0434-124141735.us-west-2.elb.amazonaws.com:80/sparkui/spark-example-01
http://k8s-default-sparkui-2d325c0434-124141735.us-west-2.elb.amazonaws.com:80/sparkui/test-02
```

EKS Admin can provide the ALB endpoint address to users. It can be found via the command: 
```bash
kubectl get ingress
```
 
## Launch EMR on EKS jobs via Job Run API

1. Update the the environment variables in the sample job script:

```bash
export EMR_VIRTUAL_CLUSTER_NAME=emr-on-eks-rss
export AWS_REGION=us-west-2
export app_name=job-run-api

export ACCOUNTID=$(aws sts get-caller-identity --query Account --output text)
export VIRTUAL_CLUSTER_ID=$(aws emr-containers list-virtual-clusters --query "virtualClusters[?name == '$EMR_VIRTUAL_CLUSTER_NAME' && state == 'RUNNING'].id" --output text)
export EMR_ROLE_ARN=arn:aws:iam::$ACCOUNTID:role/$EMR_VIRTUAL_CLUSTER_NAME-execution-role
export S3BUCKET=$EMR_VIRTUAL_CLUSTER_NAME-$ACCOUNTID-$AWS_REGION

aws emr-containers start-job-run \
--virtual-cluster-id $VIRTUAL_CLUSTER_ID \
--name $app_name \
--execution-role-arn $EMR_ROLE_ARN \
--release-label emr-7.1.0-latest \
--job-driver '{
"sparkSubmitJobDriver": {
    "entryPoint": "local:///usr/lib/spark/examples/jars/spark-examples.jar", 
    "entryPointArguments": ["100000"],
    "sparkSubmitParameters": "--class org.apache.spark.examples.SparkPi --conf spark.executor.instances=1" }}' \
--configuration-overrides '{
"applicationConfiguration": [
    {
    "classification": "spark-defaults", 
    "properties": {
        "spark.ui.proxyBase": "/sparkui/`$app_name`",
        "spark.ui.proxyRedirectUri": "/"
    }}]}'
```

2. Once the job's driver pod is running, create a kubernetes service based on the driver pod name. Ensure its name contains the suffix **ui-svc**:
```bash
# query the driver pod name
job_id=$(aws emr-containers list-job-runs --virtual-cluster-id $VIRTUAL_CLUSTER_ID --query "jobRuns[?name=='$app_name' && state=='RUNNING'].id" --output text)
driver_pod_name=$(kubectl get po -n emr | grep $job_id-driver | awk '{print $1}')
# create a k8s service
kubectl expose po -n emr \
--port=4040 \
--target-port 4040 \
--name=$app_name-ui-svc \
$driver_pod_name
```
The SparkUI service looks like this:
```bash
kubectl get svc -n emr

NAME                  TYPE      CLUSTER-IP  EXTERNAL-IP   PORT(S)  AGE
job-run-api-ui-svc ClusterIP 10.100.233.186  <none>      4040/TCP   9s
```

3. Finally, we access the sparkUI in this format:
```
http://<YOUR_INGRESS_ADDRESS>/sparkui/<app_name>
```
Admin can get the ingress address by the CLI:
```bash
kubectl get ingress
```
## Launch EMR on EKS jobs by Spark Submit:

1. Create an EMR on EKS pod with a service account that has the IRSA associated
```bash
kubectl run -it emrekspod \
--image=public.ecr.aws/emr-on-eks/spark/emr-7.1.0:latest \
--overrides='{ "spec": {"serviceAccount": "emr-containers-sa-spark"}}' \
--command -n spark-operator /bin/bash
```
2. After login into the “emrekspod” pod, submit the job:
```bash
export app_name=sparksubmittest

spark-submit \
--master k8s://$KUBERNETES_SERVICE_HOST:443 \
--deploy-mode cluster \
--name $app_name \
--class org.apache.spark.examples.SparkPi \
--conf spark.ui.proxyBase=/sparkui/$app_name \
--conf spark.ui.proxyRedirectUri="/" \
--conf spark.kubernetes.container.image=public.ecr.aws/emr-on-eks/spark/emr-7.1.0:latest \
--conf spark.kubernetes.authenticate.driver.serviceAccountName=emr-containers-sa-spark \
--conf spark.kubernetes.namespace=spark-operator \
local:///usr/lib/spark/examples/jars/spark-examples.jar 100000
```
3. As soon as the driver pod is running, create a kubernetes service for Spark UI and ensure its name has the suffix of **ui-svc**:
```bash
export app_name=sparksubmittest
# get the running driver pod name
driver_pod_name=$(kubectl get po -n spark-operator | grep -E 'sparksubmittest-.*-driver' | grep 'Running' | awk '{print $1}')

# OPTIONAL - remove existing service if needed
kubectl delete svc $app_name-ui-svc -n spark-operator

# create k8s service
kubectl expose po -n spark-operator \
--port=4040 \
--target-port 4040 \
--name=$app_name-ui-svc \
$driver_pod_name
```

## Appendix

### deployment.yaml
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spark-ui-reverse-proxy
  labels:
    app: spark-ui-reverse-proxy
spec:
  replicas: 1
  selector:
    matchLabels:
      app: spark-ui-reverse-proxy
  template:
    metadata:
      labels:
        app: spark-ui-reverse-proxy
    spec:
      containers:
      - name: spark-ui-reverse-proxy
        image: ghcr.io/datapunchorg/spark-ui-reverse-proxy:main-1652762636
        imagePullPolicy: IfNotPresent
        command:
          - '/usr/bin/spark-ui-reverse-proxy'
        args:
          # EMR on EKS's namespace
          - -namespace=spark-operator
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: spark-ui-reverse-proxy
  labels:
    app: spark-ui-reverse-proxy
spec:
  type: ClusterIP
  ports:
    - name: http
      protocol: TCP
      port: 8080
      targetPort: 8080
  selector:
    app: spark-ui-reverse-proxy

---
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: alb-ingress-class
spec:
  controller: ingress.k8s.aws/alb

--- 
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: spark-ui
  annotations:
    # kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/success-codes: 200,301,302
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}]'
    alb.ingress.kubernetes.io/manage-backend-security-group-rules: "true"
    # alb.ingress.kubernetes.io/security-groups: {{INBOUND_SG}}
  # labels:
  #   app: spark-ui-reverse-proxy
spec:
  ingressClassName: "alb-ingress-class"
  rules:
  - host: ""
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
              name: spark-ui-reverse-proxy
              port:
                number: 8080
```


### emr-eks-spark-example-01.yaml
```yaml
apiVersion: "sparkoperator.k8s.io/v1beta2"
kind: SparkApplication
metadata:
  name: spark-example-01
  namespace: spark-operator
spec:
  type: Scala
  image: public.ecr.aws/emr-on-eks/spark/emr-7.1.0:latest
  mainClass: org.apache.spark.examples.SparkPi
  mainApplicationFile: "local:///usr/lib/spark/examples/jars/spark-examples.jar"
  arguments: ["100000"]
  sparkVersion: 3.5.0
  restartPolicy:
    type: Never
  sparkConf:
    spark.ui.proxyBase: /sparkui/spark-example-01
    spark.ui.proxyRedirectUri: /
  driver:
    cores: 1
    coreLimit: "1200m"
    memory: "1g"
    serviceAccount: emr-containers-sa-spark
  executor:
    cores: 2
    instances: 2
    memory: "5120m"
```

### emr-eks-spark-example-02.yaml
```yaml
apiVersion: "sparkoperator.k8s.io/v1beta2"
kind: SparkApplication
metadata:
  name: spark-example-02
  namespace: spark-operator
spec:
  type: Scala
  image: public.ecr.aws/emr-on-eks/spark/emr-7.1.0:latest
  mainClass: org.apache.spark.examples.SparkPi
  mainApplicationFile: "local:///usr/lib/spark/examples/jars/spark-examples.jar"
  arguments: ["1000000"]
  sparkVersion: 3.5.0
  restartPolicy:
    type: Never
  sparkConf:
    spark.ui.proxyBase: /sparkui/test-02
    spark.ui.proxyRedirectUri: /
  driver:
    cores: 1
    coreLimit: "1200m"
    memory: "1g"
    serviceAccount: emr-containers-sa-spark
  executor:
    cores: 1
    instances: 1
    memory: "2120m"
```
