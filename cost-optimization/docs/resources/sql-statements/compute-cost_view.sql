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