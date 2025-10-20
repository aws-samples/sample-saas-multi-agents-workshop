import json
from aws_lambda_powertools import Metrics

metrics = Metrics(namespace="SmartResolve")

def record_metric(tenant_id, metric_name, metric_unit, metric_value):
    """ Record the metric in CloudWatch using EMF format
    Args:
        tenant_id (str): The tenant identifier
        metric_name (str): Name of the metric
        metric_unit (str): Unit of measurement
        metric_value (int/float): Value to record
    """
    metrics.add_dimension(name="tenant_id", value=tenant_id)
    metrics.add_metric(name=metric_name, unit=metric_unit, value=metric_value)
    metrics_object = metrics.serialize_metric_set()
    metrics.clear_metrics()
    print(json.dumps(metrics_object))