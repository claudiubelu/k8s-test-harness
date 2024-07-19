#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import subprocess
from typing import List


def ensure_image_contains_paths(image, paths):
    """Ensures the given container image contains the provided paths
    within it by attempting to run the image and 'ls' all of them.
    """
    base_cmd = ["docker", "run", "--rm", "--entrypoint", "ls", image, "-l"]
    base_cmd.extend(paths)

    subprocess.run(base_cmd, check=True)


def list_files_under_container_image_dir(
    image: str, root_dir: str = "/", exclude_hidden_files: bool = True
) -> List[str]:
    """Lists all regular file paths under the given dir in the given image by
    attempting to run the image and executing `find -type f` within the dir.
    """
    cmd = [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "find",
        image,
        root_dir.rstrip("/"),
        "-type",
        "f",
    ]

    if exclude_hidden_files:
        cmd.extend(["-not", "-path", "'*/\\.*'", "(", "!", "-iname", ".*", ")"])

    proc = subprocess.run(cmd, check=True, capture_output=True)

    return [line.decode("utf8").strip() for line in proc.stdout.splitlines()]


def run_in_docker(
    image: str,
    command: List[str],
    check_exit_code: bool = True,
    docker_args: List[str] = None,
):
    """Runs the given command in the given container image.

    docker_args is a list of additional docker run arguments to add.
    """
    docker_args = docker_args or []
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            *docker_args,
            "--entrypoint",
            command[0],
            image,
            *command[1:],
        ],
        check=check_exit_code,
        capture_output=True,
        text=True,
    )


def get_image_version(image):
    """Returns the image version from the "org.opencontainers.image.version" label."""
    process = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            '{{index .Config.Labels "org.opencontainers.image.version"}}',
            image,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return process.stdout.strip()
