# **Connect to SparkUI without Port Fowarding**

This is an example of connecting to SparkUI running on Spark's driver pod via a reserve proxy solution, without an access to the kubectl tool or AWS console. 

<div style="border: 1px solid red; padding: 10px; background-color: #f8d7da;">
  <strong>NOTE:</strong> We don't maintain the reverse proxy solution's docker image. 
</div>  

A reverse proxy sits between a single Ingress ALB and multiple driver pods. The ALB forwards all incoming traffic to the reverse proxy, which then directs requests to the appropriate driver pods based on the URI path in each request. This routing occurs via Kubernetes service objects, with one service object required for each driver pod. These service objects should be named using the format `<last-segment-of-URI-path>-ui-svc`. To complete this setup, the following properties must be configured in the Spark configuration:


|Configuratin|Example|Description|
|---|---|---|
|spark.ui.proxyBase|/sparkui/my-spark-app|The URI path on which to access the particular job's spark UI. This is divided into two parts, first is base URI (i.e. /sparkui) and second is the name used to redirect the traffic to corresponding kubernetes service. e.g. if URI path is "/sparkui/my-spark-app" then reverse proxy redirects the traffic to Kubernetes service named "my-spark-app-ui-svc".  Note: Don't change the /sparkui/ base URI as its a default base URI used by Spark revserve proxy|
|spark.ui.proxyRedirectUri|/|Redirect URI. Keep it "/".

The URL to access Spark UI is,  
`http://YOUR_INGRESS_ADDRESS:PORT/<spark.ui.proxyBase>`  
e.g. http://k8s-default-sparkui-2d325c0434-124141735.us-west-2.elb.amazonaws.com:80/sparkui/my-spark-app

Where,  
* YOUR_INGRESS_ADDRESS:PORT* :- Ingress ALB's DNS name and port. 

We demostrate how to set up Ingress and Reverse Proxy. Then launch the jobs via three EMR on EKS deployment methods: Spark Operator, JobRun API, and spark-submit. The spark operator creates the Kubernetes service object with target as driver pod for each job. However, JobRun API and spark-submit do not create Kubernetes service object so we use driver pod's "postStart" lifecycle hook to create the service object in driver pod's template.


## Deploy SparkUI reserve proxy and an Ingress in a default namespace

Create a SparkUI reverse proxy and an Ingress (ALB) in a default namespace, which is a different namespace from your EMR on EKS virtual cluster environment. It can be configured to the EMR's namespace if neccessary.

The [sample yaml file](#deploymentyaml) is in the Appendix section. Make sure the EMR on EKS's namespace at the line #25 in `deployment.yaml` is updated if needed:
```bash
kubectl apply -f deployment.yaml
```
<div style="border: 1px solid red; padding: 10px; background-color: #f8d7da;">
  <strong>NOTE:</strong> The example file is not production ready. This solution doesn't have authenticate on spark UI in place. Also, the listen port 80 is not recommended. Make sure to strengthen your Application Load Balance's security posture before deploying it to your production environment.
</div>  

  
EKS Admin can provide the ALB endpoint address to users via the command: 
```bash
kubectl get ingress

NAME       CLASS               HOSTS   ADDRESS                                                                PORTS   AGE
spark-ui   alb-ingress-class   *       k8s-default-sparkui-627e515973-123456789.us-west-2.elb.amazonaws.com   80      14d
```

## Grant permissions to Driver pod's Service Account
<div style="border: 1px solid red; padding: 10px; background-color: #f8d7da;">
  <strong>NOTE:</strong> This step is required for JobRun API or spark-submit. It is NOT required for spark operator.
</div>  
If you are going to use JobRun API or spark-submit to launch the jobs then grant permissions to Kubernetes role bound to Driver pod's Service Account to be able to manage Kubernetes Service Object.

The client & driver roles and corresponding service accounts are can be queried via command:
```
export EMR_CONTAINERS_NAMESPACE=emr-on-eks

kubectl get role -n $EMR_CONTAINERS_NAMESPACE                                                                                                                     
NAME                               CREATED AT
emr-containers                     2024-10-19T08:56:15Z
emr-containers-role-spark-client   2024-10-19T09:57:37Z
emr-containers-role-spark-driver   2024-10-19T09:57:37Z

kubectl get serviceaccount -n $EMR_CONTAINERS_NAMESPACE 
NAME                                                                           SECRETS   AGE
default                                                                        0         62m
emr-containers-sa-spark-client-1234567890-abcdefgh123456ijklmno7890prrst       0         28s
emr-containers-sa-spark-driver-1234567890-abcdefgh123456ijklmno7890prrst       0         28s
emr-containers-sa-spark-executor-1234567890-abcdefgh123456ijklmno7890prrst     0         28s

kubectl get rolebindings.rbac.authorization.k8s.io -n $EMR_CONTAINERS_NAMESPACE 
NAME                                                                       ROLE                                    AGE
emr-containers                                                             Role/emr-containers                     62m
emr-containers-rb-spark-client-1234567890-abcdefgh123456ijklmno7890prrst   Role/emr-containers-role-spark-client   46s
emr-containers-rb-spark-driver-1234567890-abcdefgh123456ijklmno7890prrst   Role/emr-containers-role-spark-driver   46s
```

EKS Admin can grant the list, create, update, delete and patch for Kubernetes Service Object to spark driver role via the command:  

Ensure to set `EMR_CONTAINERS_ROLE_SPARK_DRIVER` to Kubernetes role binded to driver pod's service account and `EMR_CONTAINERS_NAMESPACE` to Kubernetes namespace in which EMR on EKS is running.

```bash
export EMR_CONTAINERS_ROLE_SPARK_DRIVER=emr-containers-role-spark-driver
export EMR_CONTAINERS_NAMESPACE=emr-on-eks
kubectl patch role $EMR_CONTAINERS_ROLE_SPARK_DRIVER -n $EMR_CONTAINERS_NAMESPACE --type='json' -p='[{"op": "add", "path": "/rules/-", "value": {"apiGroups": [""], "resources": ["services"], "verbs": ["list", "create", "update", "delete", "patch"]}}]'
```

EKS Admin can varify the access to Driver Pod's Service Account via the command:  

Ensure to set `EMR_CONTAINERS_SA_SPARK_DRIVER` to service account binded to above role. The output of each command should be "yes"

```bash
export EMR_CONTAINERS_SA_SPARK_DRIVER=emr-containers-sa-spark-driver-1234567890-abcdefgh123456ijklmno7890prrst
kubectl auth can-i list   service -n $EMR_CONTAINERS_NAMESPACE --as=system:serviceaccount:$EMR_CONTAINERS_NAMESPACE:$EMR_CONTAINERS_SA_SPARK_DRIVER
kubectl auth can-i create service -n $EMR_CONTAINERS_NAMESPACE --as=system:serviceaccount:$EMR_CONTAINERS_NAMESPACE:$EMR_CONTAINERS_SA_SPARK_DRIVER
kubectl auth can-i update service -n $EMR_CONTAINERS_NAMESPACE --as=system:serviceaccount:$EMR_CONTAINERS_NAMESPACE:$EMR_CONTAINERS_SA_SPARK_DRIVER
kubectl auth can-i delete service -n $EMR_CONTAINERS_NAMESPACE --as=system:serviceaccount:$EMR_CONTAINERS_NAMESPACE:$EMR_CONTAINERS_SA_SPARK_DRIVER
kubectl auth can-i patch  service -n $EMR_CONTAINERS_NAMESPACE --as=system:serviceaccount:$EMR_CONTAINERS_NAMESPACE:$EMR_CONTAINERS_SA_SPARK_DRIVER
```

## Launch EMR on EKS jobs via Spark Operator

1.Submit two test jobs using EMR on EKS's Spark Operator. The sample job scripts [spark-operator-example-01.yaml](#spark-operator-example-01yaml) and [spark-operator-example-02.yaml](#spark-operator-example-02yaml) can be found in the Appendix section. 

* The `spec.driver.Serviceaccount` attribute should be updated based on your own [IAM Role for Service Account (IRSA)](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/setting-up-enable-IAM.html) setup in EMR on EKS.
* The `namespace` attribute should be updated to namespace where EMR on EKS is running
* Remember to specify the Spark configuration at line #16 `spark.ui.proxyBase: /sparkui/YOUR_SPARK_APP_NAME`, eg. `spark.ui.proxyBase: /sparkui/spark-example-01`.
```bash
kubectl apply -f spark-operator-example-01.yaml
kubectl apply -f spark-operator-example-02.yaml
```

2.Go to a web browser, then access their Spark Web UI while jobs are still running.

The Web UI address is in the format of `http://YOUR_INGRESS_ADDRESS:PORT/sparkui/YOUR_SPARK_APP_NAME`. For example:

```
http://k8s-default-sparkui-2d325c0434-124141735.us-west-2.elb.amazonaws.com:80/sparkui/spark-example-01
http://k8s-default-sparkui-2d325c0434-124141735.us-west-2.elb.amazonaws.com:80/sparkui/spark-example-02
```

## Launch EMR on EKS jobs via Job Run API

1.Upload the driver pod template to S3 bucket. It is assumed that template is copied under prefix (folder) `/templates` inside bucket.

```bash
aws s3 cp driver-pod-template.yaml YOUR_S3_BUCKET/templates
```

2.Ensure that Job execution role has access to above S3 bucket.


3.Set the values for `YOUR_APP_NAME`, `YOUR_S3_BUCKET`, `YOUR_EMR_VIRTUAL_CLUSTER_NAME`, `YOUR_EMR_JOB_EXECUTION_ROLE` and run the sample job submission script below:


```bash
export YOUR_APP_NAME=start-job-run-pi
export S3BUCKET=YOUR_S3_BUCKET

export EMR_VIRTUAL_CLUSTER_NAME=YOUR_EMR_VIRTUAL_CLUSTER_NAME
export VIRTUAL_CLUSTER_ID=$(aws emr-containers list-virtual-clusters --query "virtualClusters[?name == '$EMR_VIRTUAL_CLUSTER_NAME' && state == 'RUNNING'].id" --output text)

export ACCOUNTID=$(aws sts get-caller-identity --query Account --output text)
export EMR_ROLE_ARN=arn:aws:iam::$ACCOUNTID:role/YOUR_EMR_JOB_EXECUTION_ROLE

aws emr-containers start-job-run \
--virtual-cluster-id $VIRTUAL_CLUSTER_ID \
--name $YOUR_APP_NAME \
--execution-role-arn $EMR_ROLE_ARN \
--release-label emr-7.1.0-latest \
--job-driver '{
"sparkSubmitJobDriver": {
    "entryPoint": "local:///usr/lib/spark/examples/jars/spark-examples.jar", 
    "entryPointArguments": ["100000"],
    "sparkSubmitParameters": "--class org.apache.spark.examples.SparkPi --conf spark.executor.instances=1 --conf spark.kubernetes.driver.podTemplateFile=s3://'${S3BUCKET}'/templates/driver-pod-template.yaml" }}' \
--configuration-overrides '{
"applicationConfiguration": [
    {
    "classification": "spark-defaults", 
    "properties": {
        "spark.ui.proxyBase": "/sparkui/'${YOUR_APP_NAME}'",
        "spark.ui.proxyRedirectUri": "/"
    }}]}'
```


2.Go to a web browser, then access their Spark Web UI while jobs are still running.
```
http://<YOUR_INGRESS_ADDRESS>/sparkui/<YOUR_APP_NAME>
```
Admin can get the ingress address by the CLI:
```bash
kubectl get ingress
```
The SparkUI service is created on postStart event of driver container and looks like this:
```bash
kubectl get service -n $EMR_CONTAINERS_NAMESPACE

NAME                  TYPE      CLUSTER-IP  EXTERNAL-IP   PORT(S)  AGE
YOUR_APP_NAME-ui-svc ClusterIP 10.100.233.186  <none>      4040/TCP   9s
```

## Launch EMR on EKS jobs by Spark Submit:

1.Create an EMR on EKS pod with a service account that has the [IRSA](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/setting-up-enable-IAM.html) associated and have permission to access the S3 bucket which has pod template.
```bash
export EMR_CONTAINERS_NAMESPACE=emr-on-eks
export EMR_CONTAINERS_SA_SPARK_CLIENT=emr-containers-sa-spark-client-1234567890-abcdefgh123456ijklmno7890prrst

kubectl run -it emrekspod \
--image=public.ecr.aws/emr-on-eks/spark/emr-7.1.0:latest \
--overrides='{ "spec": {"serviceAccount": "'${EMR_CONTAINERS_SA_SPARK_CLIENT}'"}}' \
--command -n $EMR_CONTAINERS_NAMESPACE /bin/bash
```
2.After login into the "emrekspod" pod, submit the job:
```bash
export YOUR_APP_NAME=spark-submit-pi
export S3BUCKET=YOUR_S3_BUCKET
export EMR_CONTAINERS_NAMESPACE=emr-on-eks
export EMR_CONTAINERS_SA_SPARK_DRIVER=emr-containers-sa-spark-driver-1234567890-abcdefgh123456ijklmno7890prrst

spark-submit \
--master k8s://$KUBERNETES_SERVICE_HOST:443 \
--deploy-mode cluster \
--name $YOUR_APP_NAME \
--class org.apache.spark.examples.SparkPi \
--conf spark.kubernetes.driver.podTemplateFile=s3://$S3BUCKET/templates/driver-pod-template.yaml \
--conf spark.kubernetes.driver.podTemplateContainerName=spark-kubernetes-driver \
--conf spark.ui.proxyBase=/sparkui/$YOUR_APP_NAME \
--conf spark.ui.proxyRedirectUri="/" \
--conf spark.kubernetes.container.image=public.ecr.aws/emr-on-eks/spark/emr-7.1.0:latest \
--conf spark.kubernetes.authenticate.driver.serviceAccountName=$EMR_CONTAINERS_SA_SPARK_DRIVER \
--conf spark.kubernetes.namespace=$EMR_CONTAINERS_NAMESPACE \
local:///usr/lib/spark/examples/jars/spark-examples.jar 100000
```

3.Go to a web browser, then access their Spark Web UI while jobs are still running.
```
http://<YOUR_INGRESS_ADDRESS>/sparkui/<YOUR_APP_NAME>
```
Admin can get the ingress address by the CLI:
```bash
kubectl get ingress
```
The SparkUI service looks like this:
```bash
kubectl get svc -n emr

NAME                  TYPE      CLUSTER-IP  EXTERNAL-IP   PORT(S)  AGE
job-run-api-ui-svc ClusterIP 10.100.233.186  <none>      4040/TCP   9s
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
          - -namespace=emr-on-eks
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


### spark-operator-example-01.yaml
```yaml
apiVersion: "sparkoperator.k8s.io/v1beta2"
kind: SparkApplication
metadata:
  name: spark-example-01
  namespace: emr-on-eks
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
    cores: 1
    instances: 2
    memory: "2g"
```

### spark-operator-example-02.yaml
```yaml
apiVersion: "sparkoperator.k8s.io/v1beta2"
kind: SparkApplication
metadata:
  name: spark-example-02
  namespace: emr-on-eks
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
    spark.ui.proxyBase: /sparkui/spark-example-02
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

### driver-pod-template.yaml
```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: spark-kubernetes-driver # This will be interpreted as driver Spark main container
    lifecycle:
      postStart:
        exec:
          command: 
            - /bin/bash
            - -c
            - |
              # Set Variables
              export K8S_NAMESPACE=`cat  /run/secrets/kubernetes.io/serviceaccount/namespace`
              export SPARK_UI_PROXYBASE=`grep spark.ui.proxyBase ${SPARK_CONF_DIR}/spark.properties | rev |  cut -d/ -f1 | rev`
              export SPARK_UI_SERVICE_NAME=${SPARK_UI_PROXYBASE}-ui-svc
              
              cat > /tmp/service.yaml << EOF
              apiVersion: v1
              kind: Service
              metadata:
                name: ${SPARK_UI_SERVICE_NAME}
                namespace: $K8S_NAMESPACE
                labels:
                  spark-app-selector: ${SPARK_APPLICATION_ID}
                  spark-role: driver
              spec:
                ports:
                - port: 4040
                  targetPort: 4040
                  protocol: TCP
                selector:
                  spark-app-selector: ${SPARK_APPLICATION_ID}
                  spark-role: driver
                type: ClusterIP
              EOF

              if [ -n "${SPARK_UI_PROXYBASE:-}" ]; then
                # Create or replace the service 
                curl -X PUT https://${KUBERNETES_SERVICE_HOST}/api/v1/namespaces/${K8S_NAMESPACE}/services/${SPARK_UI_SERVICE_NAME} -H "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" -H "Content-Type: application/yaml" --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt --data-binary @/tmp/service.yaml > /tmp/service.out
              else
                echo spark.ui.proxyBase is NOT set in ${SPARK_CONF_DIR}/spark.properties > /tmp/service.out
              fi
```
