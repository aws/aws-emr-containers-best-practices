CREATE OR REPLACE VIEW emr_eks_cost AS

SELECT month, namespace, total_cost as cost FROM "reinventdemo"."compute_cost_per_namespace_view"

UNION

SELECT month, namespace, cost FROM "reinventdemo"."emr_uplift_per_vc_view"