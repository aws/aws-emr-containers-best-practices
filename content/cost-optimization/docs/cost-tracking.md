# Cost Tracking

In AWS users can gain a detailed insight about the cost of their usage by leveraging (Data Exports)[https://docs.aws.amazon.com/cur/latest/userguide/what-is-data-exports.html]. It allows organizations to create customized exports of the AWS Cost and Usage Report (CUR) 2.0, offering daily or hourly usage insights along with rates, costs, and usage attributes across all chargeable AWS services. The standard data export option delivers customized cost data to Amazon S3 on a recurring basis. With Data Exports users can also track the cost incurred by their pods running in their EKS cluster. In this section we will show you how you can use the Data Exports data to track data at the Virtual Cluster level, for both the compute and the Amazon EMR on EKS uplift, allowing to have a comprehensive view on the cost incured by your jobs.


## Create Data Exports

To create a Data Exports you can execute the following shell script, or you can create by following the [AWS documentation](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-create-standard.html).


```
sh create-bucket-data-export.sh NAME-OF-S3-BUCKET-TO-CREATE ACCOUNT-ID REPORT-NAME 
```

::::
NOTE: if you create it following the AWS documentation, make sure to select the `split cost allocation` and `resource-id` to be included in the Data export.
::::