# Cost Tracking

In AWS users can gain a detailed insight about the cost of their usage by leveraging [Data Exports](https://docs.aws.amazon.com/cur/latest/userguide/what-is-data-exports.html). It allows organizations to create customized exports of the AWS Cost and Usage Report (CUR) 2.0, offering daily or hourly usage insights along with rates, costs, and usage attributes across all chargeable AWS services. The standard data export option delivers customized cost data to Amazon S3 on a recurring basis. With Data Exports users can also track the cost incurred by their pods running in their EKS cluster. 

In this section we will show you how you can use the Data Exports data to track cost at the Virtual Cluster level, for both the compute and the Amazon EMR on EKS uplift, this would allow you to have a comprehensive view on the cost incured by your jobs.


## Create Data Exports

To create a Data Export report you can execute the following [shell script](), or you can create by following the [AWS documentation](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-create-standard.html).


```sh
sh create-bucket-data-export.sh NAME-OF-S3-BUCKET-TO-CREATE ACCOUNT-ID REPORT-NAME 
```

> ***NOTE***: if you create it following the AWS documentation, make sure to select the `split cost allocation` and `resource-id` to be included in the Data export.

## Create the cost views

To get the total cost we will use Amazon Athena to query the cost data from the Data Export report. Using Athena we will first create a table for data exported by Data Export report, then we will create a mapping table that will contain the mapping an Amazon EMR on EKS Virtual Cluster to a namespace. Afterward we will create two views one that will represent the compute cost and a second that will contain the EMR on EKS uplift. Last we will create a view that will combine both the cost of the EMR on EKS uplift as well as the compute, this view will be a union of the two views we created earlier.   


### Create the data exports report table

You can use the following [query](https://github.com/aws/aws-emr-containers-best-practices/tree/main/content/cost-optimization/resources/sql-statements/data-export-table.sql) to create the data export table, if you used the script provided you can just replace the S3 bucket name. If you have created the export report not using the provided shell script then you need to update the S3 location to match the one of where the data is exported by data export report you created.

### Create the Virtual cluster and namespace lookup table

To create the look up table you can you the following sql statement.

```sql
    CREATE EXTERNAL TABLE `virtual_cluster_lookup`(
    `virtual_cluster_id` string, 
    `namespace` string)
    ROW FORMAT DELIMITED 
    FIELDS TERMINATED BY ',' 
    STORED AS INPUTFORMAT 
    'org.apache.hadoop.mapred.TextInputFormat' 
    OUTPUTFORMAT 
    'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
    LOCATION
    's3://BUCKET-NAME/data/virtual_cluster_definition'
```
Make sure to insert the look up data, you can use the query below as an example.

```sql
INSERT INTO virtual_cluster_lookup 
VALUES ('96nxs46332423542abnbd2iuv6049', 'myvc')
```

### Create the EMR on EKS uplift view

To create EMR on EKS uplift view  ou can use the following sql statement.

> ***NOTE***: You may need to change the source data table if you created the data export yourself. The query below has the source data table called `data` 

```sql
    CREATE OR REPLACE VIEW "emr_uplift_per_vc_view" AS 
    WITH
    emr_uplift_per_vc AS (
    SELECT
        DATE_FORMAT(DATE_TRUNC('month', "line_item_usage_start_date"), '%Y-%m') "month",
        split_part(line_item_resource_id, '/', 3) vc_id,
        sum(line_item_blended_cost) cost
    FROM
        data
    WHERE ((line_item_product_code = 'ElasticMapReduce') AND (line_item_operation = 'StartJobRun'))
    GROUP BY line_item_resource_id, 1
    ) 
    SELECT
    month,
    namespace,
    SUM(cost) cost
    FROM
    (emr_uplift_per_vc uplift
    INNER JOIN virtual_cluster_lookup lookup ON (uplift.vc_id = lookup.virtual_cluster_id))
    GROUP BY month, namespace
```
### Create the Compute cost view

To create Compute cost view  ou can use the following sql statement.

> ***NOTE***: You may need to change the source data table if you created the data export yourself. The query below has the source data table called `data` 

```sql

CREATE OR REPLACE VIEW "compute_cost_per_namespace_view" AS
SELECT
  DATE_FORMAT(DATE_TRUNC('month', "line_item_usage_start_date"), '%Y-%m') "month"
, CONCAT(REPLACE(SPLIT_PART("line_item_resource_id", '/', 1), 'pod', 'cluster'), '/', SPLIT_PART("line_item_resource_id", '/', 2)) "cluster_arn"
, SPLIT_PART("line_item_resource_id", '/', 3) "namespace"
, SUM((CASE WHEN ("line_item_usage_type" LIKE '%EKS-EC2-vCPU-Hours') THEN ("split_line_item_split_cost" + "split_line_item_unused_cost") ELSE 0E0 END)) "cpu_cost"
, SUM((CASE WHEN ("line_item_usage_type" LIKE '%EKS-EC2-GB-Hours') THEN ("split_line_item_split_cost" + "split_line_item_unused_cost") ELSE 0E0 END)) "ram_cost"
, SUM(("split_line_item_split_cost" + "split_line_item_unused_cost")) "total_cost"
FROM
  (data
INNER JOIN virtual_cluster_lookup lookup ON (SPLIT_PART("line_item_resource_id", '/', 3) = lookup.namespace))
WHERE ("line_item_operation" = 'EKSPod-EC2')
GROUP BY 1, 2, 3
ORDER BY "month" DESC, "cluster_arn" ASC, "namespace" ASC, "total_cost" DESC

```

### Create the over all cost view

To create over all cost view view  ou can use the following sql statement.

```sql
CREATE OR REPLACE VIEW emr_eks_cost AS

SELECT month, namespace, total_cost as cost FROM "reinventdemo"."compute_cost_per_namespace_view"

UNION

SELECT month, namespace, cost FROM "reinventdemo"."emr_uplift_per_vc_view"
```

## Query the data

After creating the views you can now get insights on the total cost of runing your EMR on EKS job at the virtual cluster level. The query below shows how you van get the over all cost.

```
SELECT month, namespace, sum(cost) as total_cost
FROM "emr_eks_cost"
GROUP BY namespace, month
```
> ***NOTE***: In these views the granularity is at the month level, you can also run it at the day level, you can achieve it by changing the date in the SQL queries to include also the day, 



