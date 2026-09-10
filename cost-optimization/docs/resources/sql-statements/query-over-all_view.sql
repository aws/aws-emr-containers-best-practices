SELECT month, namespace, sum(cost) as total_cost
FROM "emr_eks_cost"
GROUP BY namespace, month
