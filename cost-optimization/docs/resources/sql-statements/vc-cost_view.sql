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