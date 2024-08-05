#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

K8S_NS_DEFAULT = "default"
K8S_NS_KUBE_SYSTEM = "kube-system"

K8S_POD = "pod"
K8S_DAEMONSET = "daemonset.apps"
K8S_DEPLOYMENT = "deployment.apps"
K8S_STATEFULSET = "statefulset.apps"

K8S_CONDITION_AVAILABLE = "Available"
K8S_CONDITION_READY = "Ready"

K8S_PROBE_READINESS = "readinessProbe"
K8S_PROBE_LIVENESS = "livenessProbe"
K8S_PROBE_STARTUP = "startupProbe"

ALL_PROBE_TYPES = [K8S_PROBE_READINESS, K8S_PROBE_LIVENESS, K8S_PROBE_STARTUP]
