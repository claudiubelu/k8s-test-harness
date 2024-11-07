#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import functools
import itertools
import json
import logging
import os
import uuid
from typing import Any, List, NamedTuple

from k8s_test_harness import config, harness
from k8s_test_harness.util import constants, exec_util

LOG = logging.getLogger(__name__)


class HelmImage(NamedTuple):
    uri: str
    prefix: str = None
    subitem: str = None


# Installs and setups the k8s snap on the given instance and connects the interfaces.
def setup_k8s_snap(instance: harness.Instance):
    LOG.info("Install k8s snap")
    if config.K8S_SNAP_PATH:
        instance.exec(
            ["snap", "install", "--classic", "--dangerous", config.K8S_SNAP_PATH]
        )
        return
    instance.exec(
        ["snap", "install", "k8s", "--classic", "--channel", config.SNAP_CHANNEL]
    )


def purge_k8s_snap(instance: harness.Instance):
    LOG.info("Purge k8s snap")
    instance.exec(["sudo", "snap", "remove", "k8s", "--purge"])


def describe_resources_on_error(resource_type: str):
    def _decorator(fun):
        @functools.wraps(fun)
        def _inner(instance: harness.Instance, *args, **kwargs):
            try:
                return fun(instance, *args, **kwargs)
            except Exception:
                proc = instance.exec(
                    ["k8s", "kubectl", "describe", "-A", resource_type],
                    capture_output=True,
                )
                LOG.info(
                    f"### All current '{resource_type}' definitions: "
                    f"{proc.stdout.decode()}"
                )
                raise

        return _inner

    return _decorator


# Validates that the K8s node is in Ready state.
def wait_until_k8s_ready(
    control_node: harness.Instance, instances: List[harness.Instance]
):
    for instance in instances:
        host = hostname(instance)
        result = (
            exec_util.stubbornly(retries=120, delay_s=5)
            .on(control_node)
            .until(lambda p: " Ready" in p.stdout.decode())
            .exec(["k8s", "kubectl", "get", "node", host, "--no-headers"])
        )
    LOG.info("Kubelet registered successfully!")
    LOG.info("%s", result.stdout.decode())


def wait_for_dns(instance: harness.Instance):
    LOG.info("Waiting for DNS to be ready")
    instance.exec(["k8s", "x-wait-for", "dns"])


def wait_for_network(instance: harness.Instance):
    LOG.info("Waiting for network to be ready")
    instance.exec(["k8s", "x-wait-for", "network"])


def hostname(instance: harness.Instance) -> str:
    """Return the hostname for a given instance."""
    resp = instance.exec(["hostname"], capture_output=True)
    return resp.stdout.decode().strip()


def get_local_node_status(instance: harness.Instance) -> str:
    resp = instance.exec(["k8s", "local-node-status"], capture_output=True)
    return resp.stdout.decode().strip()


def get_nodes(control_node: harness.Instance) -> List[Any]:
    """Get a list of existing nodes.

    Args:
        control_node: instance on which to execute check

    Returns:
        list of nodes
    """
    result = control_node.exec(
        ["k8s", "kubectl", "get", "nodes", "-o", "json"], capture_output=True
    )
    assert result.returncode == 0, "Failed to get nodes with kubectl"
    node_list = json.loads(result.stdout.decode())
    assert node_list["kind"] == "List", "Should have found a list of nodes"
    return [node for node in node_list["items"]]


def ready_nodes(control_node: harness.Instance) -> List[Any]:
    """Get a list of the ready nodes.

    Args:
        control_node: instance on which to execute check

    Returns:
        list of nodes
    """
    return [
        node
        for node in get_nodes(control_node)
        if all(
            condition["status"] == "False"
            for condition in node["status"]["conditions"]
            if condition["type"] != "Ready"
        )
    ]


# Create a token to join a node to an existing cluster
def get_join_token(
    initial_node: harness.Instance, joining_cplane_node: harness.Instance, *args: str
) -> str:
    out = initial_node.exec(
        ["k8s", "get-join-token", joining_cplane_node.id, *args],
        capture_output=True,
    )
    return out.stdout.decode().strip()


# Join an existing cluster.
def join_cluster(instance: harness.Instance, join_token: str):
    instance.exec(["k8s", "join-cluster", join_token])


def wait_for_resource(
    instance: harness.Instance,
    resource_type: str,
    name: str,
    namespace: str = constants.K8S_NS_DEFAULT,
    condition: str = constants.K8S_CONDITION_AVAILABLE,
    retry_times: int = 5,
    retry_delay_s: int = 60,
):
    """Waits for the given resource to reach the given condition."""
    exec_util.stubbornly(retries=retry_times, delay_s=retry_delay_s).on(instance).exec(
        [
            "k8s",
            "kubectl",
            "wait",
            "--namespace",
            namespace,
            f"--for=condition={condition}",
            resource_type,
            name,
            "--timeout",
            "1s",
        ]
    )


@describe_resources_on_error("pods")
@describe_resources_on_error("deployment")
def wait_for_deployment(
    instance: harness.Instance,
    name: str,
    namespace: str = constants.K8S_NS_DEFAULT,
    condition: str = constants.K8S_CONDITION_AVAILABLE,
    retry_times: int = 5,
    retry_delay_s: int = 60,
):
    """Waits for the given deployment to reach the given condition."""
    wait_for_resource(
        instance,
        constants.K8S_DEPLOYMENT,
        name,
        namespace=namespace,
        condition=condition,
        retry_times=retry_times,
        retry_delay_s=retry_delay_s,
    )


@describe_resources_on_error("pods")
@describe_resources_on_error("daemonsets")
def wait_for_daemonset(
    instance: harness.Instance,
    name: str,
    namespace: str = constants.K8S_NS_DEFAULT,
    retry_times: int = 5,
    retry_delay_s: int = 60,
):
    """Waits for the given daemonset to become available."""
    exec_util.stubbornly(retries=retry_times, delay_s=retry_delay_s).on(instance).exec(
        [
            "k8s",
            "kubectl",
            "rollout",
            "status",
            "--namespace",
            namespace,
            constants.K8S_DAEMONSET,
            name,
            "--timeout",
            "1s",
        ]
    )


@describe_resources_on_error("pods")
@describe_resources_on_error("statefulsets")
def wait_for_statefulset(
    instance: harness.Instance,
    name: str,
    namespace: str = constants.K8S_NS_DEFAULT,
    retry_times: int = 5,
    retry_delay_s: int = 60,
):
    """Waits for the given daemonset to become available."""
    exec_util.stubbornly(retries=retry_times, delay_s=retry_delay_s).on(instance).exec(
        [
            "k8s",
            "kubectl",
            "rollout",
            "status",
            "--namespace",
            namespace,
            constants.K8S_STATEFULSET,
            name,
            "--timeout",
            "1s",
        ]
    )


def get_helm_install_command(
    name: str,
    chart_name: str,
    namespace: str = constants.K8S_NS_KUBE_SYSTEM,
    repository: str = None,
    images: List[HelmImage] = None,
    runAsUser: int = 584792,
    set_configs: List[str] = None,
    chart_version: str = None,
    split_image_registry: bool = False,
):
    """Creates a helm install command for the given helm chart.

    The chart_name can be a locally-cloned helm chart.

    This function will prepend a "--set" string before each element in
    set_configs in the final helm install command.

    Returns:
        list of strings representing the helm install command.
    """
    images = images or []
    set_configs = set_configs or []

    helm_command = [
        "k8s",
        "helm",
        "install",
        name,
        chart_name,
        "--namespace",
        namespace,
        "--create-namespace",
    ]

    if repository:
        helm_command += [
            "--repo",
            repository,
        ]

    if chart_version:
        helm_command += [
            "--version",
            chart_version,
        ]

    for image in images:
        image_split = image.uri.split(":")
        image_name = image_split[0]

        prefix = ""
        if image.prefix:
            prefix = f"{image.prefix}."

        subitem = ""
        if image.subitem:
            subitem = f"{image.subitem}."

        if split_image_registry:
            # Some helm charts require the registry to be separated from the image.
            registry = "docker.io"
            parts = image_name.split("/")
            if len(parts) > 2:
                registry = parts[0]
                image_name = "/".join(parts[1:])

            helm_command += [
                "--set",
                f"{prefix}image.{subitem}registry={registry}",
            ]

        helm_command += [
            "--set",
            f"{prefix}image.{subitem}repository={image_name}",
            "--set",
            f"{prefix}image.{subitem}tag={image_split[1]}",
            "--set",
            f"{prefix}securityContext.runAsUser={runAsUser}",
        ]

    # Pair each configuration with a "--set".
    pairs = itertools.zip_longest(["--set"] * len(set_configs), set_configs)
    helm_command += list(itertools.chain.from_iterable(pairs))

    return helm_command


def install_mutating_pebble_webhook(instance: harness.Instance):
    # The substrate might not have make installed.
    install_command = [
        "sudo",
        "apt",
        "install",
        "-y",
        "make",
    ]
    instance.exec(install_command)

    clone_path = os.path.join(
        "/tmp", f"mutating-pebble-webhook-rocks-{str(uuid.uuid4())}"
    )

    # We have all the necessary steps in this repository as a make target.
    clone_command = [
        "git",
        "clone",
        "https://github.com/canonical/mutating-pebble-webhook-rocks",
        "--depth",
        "1",
        clone_path,
    ]
    instance.exec(clone_command)

    make_command = [
        "make",
        "-C",
        clone_path,
        "all",
        "KUBECTL=k8s kubectl",
    ]
    instance.exec(make_command)

    wait_for_deployment(instance, "mutating-pebble-webhook", "pebble-webhook")
