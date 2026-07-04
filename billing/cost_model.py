from typing import Dict, Any

# Rates in USD
WORKER_SECOND_RATE = 0.0001
SANDBOX_SECOND_RATE = 0.0005
API_CALL_RATE = 0.002

def estimate_pipeline_cost(dag: Dict[str, Any]) -> float:
    """
    Estimates the cost of a pipeline run based on DAG layout:
    - 15 seconds of worker compute time per node.
    - 10 seconds of sandbox runtime if validation or repair nodes are present.
    - 5 API calls per node.
    """
    if not dag or not isinstance(dag, dict):
        return 0.0

    nodes = dag.get("nodes", [])
    num_nodes = len(nodes)

    # Compute cost estimation
    est_compute_s = num_nodes * 15.0
    compute_cost = est_compute_s * WORKER_SECOND_RATE

    # Sandbox cost estimation
    has_sandbox = any(n.get("id") in ["validation_node", "repair_node"] for n in nodes)
    est_sandbox_s = 10.0 if has_sandbox else 0.0
    sandbox_cost = est_sandbox_s * SANDBOX_SECOND_RATE

    # API calls cost estimation
    est_api_calls = num_nodes * 5
    api_cost = est_api_calls * API_CALL_RATE

    return round(compute_cost + sandbox_cost + api_cost, 6)

def calculate_run_cost(compute_seconds: float, sandbox_seconds: float, api_calls: int) -> float:
    """
    Calculates the final cost based on actual worker time, sandbox runtime, and API calls.
    """
    compute_cost = max(0.0, compute_seconds) * WORKER_SECOND_RATE
    sandbox_cost = max(0.0, sandbox_seconds) * SANDBOX_SECOND_RATE
    api_cost = max(0, api_calls) * API_CALL_RATE

    return round(compute_cost + sandbox_cost + api_cost, 6)
