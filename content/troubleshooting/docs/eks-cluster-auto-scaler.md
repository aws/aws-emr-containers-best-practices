# **EKS Cluster Auto-Scaler**
Kubernetes provisions nodes using CAS (Cluster Autoscaler). AWS EKS has its own implementation of K8 CAS, and EKS uses Managed-Nodegroups to spuns of Nodes.  

### Logs of EKS Cluster Auto-scaler.

On AWS, Cluster Autoscaler utilizes Amazon EC2 Auto Scaling Groups to provision nodes. This section will help you identify the error message when a AutoScaler fails to provision nodes.   

An example scenario, where the NodeGroup would fail due to non-supported nodes in certain AZs.  
```
Could not launch On-Demand Instances. Unsupported - Your requested instance type (g4dn.xlarge) is not supported in your requested Availability Zone (ca-central-1d). Please retry your request by not specifying an Availability Zone or choosing ca-central-1a, ca-central-1b. Launching EC2 instance failed.
```

The steps to find the logs for AutoScalingGroups are, 

Step 1: Login to AWS Console, and select `Elastic Kubernetes Service`

Step 2: Select `Compute` tab, and select the `NodeGroup` that fails.

Step 3: Select the `Autoscaling group name` from the NodeGroup's section, which will direct you to `EC2 --> AutoScaling Group` page.

Step 4: Click the Tab `Activity` of the `AutoScaling Group`, and the `Activity History` would give provide the details of the error. 
```
- Status
- Description
- Cause
- Start Time
- End Time
```
Alternatively, the activities/logs can be found via CLI as well 
```bash
aws autoscaling describe-scaling-activities \
  --region <region> \
  --auto-scaling-group-name <NodeGroup-AutoScaling-Group>
```

In the above error scenario, the `ca-central-1d` availability zone doesn't support `g4dn.xlarge`.  The solution is

Step 1: Identify the Subnets of the Availability zones that supports the GPU node type. The NodeGroup Section would list all the subnets, and you can click each subnet to see which AZ it is deployed to.

Step 2: Create a NodeGroup only in the Subnets identified in the above step
```bash
aws eks create-nodegroup \
    --region <region> \ 
    --cluster-name <cluster-name> \
    --nodegroup-name <nodegroup-name> \
    --scaling-config minSize=10,maxSize=10,desiredSize=10 \
    --ami-type AL2_x86_64_GPU \
    --node-role <NodeGroupRole> \
    --subnets <subnet-1-that-supports-gpu> <subnet-2-that-supports-gpu> \
    --instance-types g4dn.xlarge \
    --disk-size <disk size>
```