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