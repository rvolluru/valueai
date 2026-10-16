"""Run the new image's migrations inside the existing service network, before rollout."""
from __future__ import annotations

import argparse
import json
import subprocess
import time


def aws(*args, payload=None):
    command = ["aws", "ecs", *args, "--output", "json"]
    if payload is not None:
        command += ["--cli-input-json", "file:///dev/stdin"]
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, check=False, timeout=60)
    if result.returncode:
        # Never echo task definitions: legacy environment variables can contain secrets.
        raise RuntimeError(f"AWS ECS {args[0]} failed (exit {result.returncode}); rollout must not proceed")
    return json.loads(result.stdout)


def migration_definition(definition, image):
    allowed = {"family", "taskRoleArn", "executionRoleArn", "networkMode", "containerDefinitions",
               "volumes", "placementConstraints", "requiresCompatibilities", "cpu", "memory",
               "pidMode", "ipcMode", "proxyConfiguration", "inferenceAccelerators", "ephemeralStorage",
               "runtimePlatform", "enableFaultInjection"}
    result = {key: value for key, value in definition.items() if key in allowed}
    result = json.loads(json.dumps(result))
    result["family"] = result["family"] + "-migrations"
    containers = [container for container in result["containerDefinitions"] if container["name"] == "api"]
    if len(containers) != 1:
        raise RuntimeError("Expected exactly one api container for migrations")
    containers[0]["image"] = image
    containers[0]["essential"] = True
    containers[0].pop("healthCheck", None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    services = aws("describe-services", "--cluster", args.cluster, "--services", args.service).get("services") or []
    if not services or services[0].get("status") != "ACTIVE":
        raise RuntimeError("An existing service/network is required. Provision infrastructure before deploying application changes.")
    service = services[0]
    definition = aws("describe-task-definition", "--task-definition", service["taskDefinition"])["taskDefinition"]
    registered = aws("register-task-definition", payload=migration_definition(definition, args.image))
    task_definition = registered["taskDefinition"]["taskDefinitionArn"]
    result = aws("run-task", payload={
        "cluster": args.cluster, "taskDefinition": task_definition, "launchType": "FARGATE",
        "networkConfiguration": service["networkConfiguration"], "startedBy": "pre-rollout-migrations",
        "overrides": {"containerOverrides": [{"name": "api", "command": ["python", "-m", "app.migrations"]}]},
    })
    if result.get("failures") or len(result.get("tasks") or []) != 1:
        raise RuntimeError("Could not start migration task; rollout must not proceed")
    task_arn = result["tasks"][0]["taskArn"]
    print(f"Migration task: {task_arn}", flush=True)
    stopped = False
    try:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            tasks = aws("describe-tasks", "--cluster", args.cluster, "--tasks", task_arn).get("tasks") or []
            if not tasks:
                raise RuntimeError("Migration task disappeared; rollout must not proceed")
            task = tasks[0]
            if task["lastStatus"] == "STOPPED":
                stopped = True
                container = next((entry for entry in task.get("containers", []) if entry["name"] == "api"), {})
                if container.get("exitCode") != 0:
                    raise RuntimeError(f"Migration task failed (exit {container.get('exitCode')}); inspect task logs. Rollout blocked.")
                print("Database migrations succeeded; application rollout may proceed.", flush=True)
                return
            time.sleep(5)
        raise TimeoutError("Migration task timed out; rollout blocked")
    finally:
        if not stopped:
            aws("stop-task", "--cluster", args.cluster, "--task", task_arn,
                "--reason", "Pre-rollout migration runner interrupted or timed out")


if __name__ == "__main__":
    main()
