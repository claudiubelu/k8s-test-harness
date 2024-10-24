#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

import json
import logging
import os
import stat
import subprocess
from typing import List

LOG = logging.getLogger(__name__)


def ensure_image_contains_paths(
    image: str, paths: List[str], override_entrypoint: str = ""
):
    """Ensures the given container image contains the provided paths
    within it by attempting to run the image and 'ls' all of them.
    """
    base_cmd = ["docker", "run", "--rm", "--entrypoint"]
    entrypoint = "ls"
    args = ["-l"]
    if override_entrypoint:
        entrypoint = override_entrypoint
        args = ["ls", "-l"]
    base_cmd.append(entrypoint)
    base_cmd.append(image)
    base_cmd.extend(args)
    base_cmd.extend(paths)

    LOG.debug(f"Running command: {base_cmd}")
    subprocess.run(base_cmd, check=True)


def _check_path_in_layers(path, layers):
    # Assuming the layers are top to bottom.
    for layer in layers:
        full_path = os.path.join(layer, path.lstrip("/"))
        try:
            file_stat = os.lstat(full_path)
        except FileNotFoundError:
            # Not found in the current folder, check the next.
            continue

        mode = file_stat.st_mode
        st_rdev = file_stat.st_rdev
        if stat.S_ISWHT(mode) or (
            stat.S_ISCHR(mode) and os.major(st_rdev) == 0 and os.minor(st_rdev) == 0
        ):
            # We found a whiteout file. This means that it's deleted.
            # https://docs.docker.com/engine/storage/drivers/overlayfs-driver/#deleting-files-and-directories
            # Character files with device type 0,0 may be added instead.
            return False

        return True

    # Checked all layers and couldn't find it.
    return False


def ensure_image_contains_paths_bare(image: str, paths: List[str]):
    """Ensures the given container image contains the provided paths
    within it by checking its overlay2 fs.

    This is useful for cases in which ensure_image_contains_paths is not an
    option (e.g. bare / scratch based images).

    This assumes that we have sufficient permissions to access the image layers.
    """
    if not paths:
        return

    # Ensure the image exists first.
    pull_cmd = ["docker", "pull", image]
    LOG.debug(f"Running command: {pull_cmd}")
    subprocess.run(pull_cmd, check=True)

    # Get image information.
    inspect_cmd = ["docker", "inspect", image]
    LOG.debug(f"Running command: {inspect_cmd}")
    process = subprocess.run(inspect_cmd, check=True, capture_output=True, text=True)
    image_info = json.loads(process.stdout)

    graph_driver = image_info[0].get("GraphDriver")
    assert (
        graph_driver is not None
    ), "Expected docker inspect result to contain GraphDriver"
    assert (
        graph_driver["Name"] == "overlay2"
    ), f"Unsupported image GraphDriver: {graph_driver['Name']}"

    # We'll be checking the layers from to top to bottom, UpperDir is the top-most layer, followed
    # by LowerDir layers (from top to bottom).
    layers = [graph_driver["Data"]["UpperDir"]]
    layers += graph_driver["Data"]["LowerDir"].split(":")

    for path in paths:
        assert _check_path_in_layers(
            path, layers
        ), f"Expected {path} to exist in {image}."


def list_files_under_container_image_dir(
    image: str,
    root_dir: str = "/",
    override_entrypoint: str = "",
    exclude_hidden_files: bool = True,
) -> List[str]:
    """Lists all regular file paths under the given dir in the given image by
    attempting to run the image and executing `find -type f` within the dir.
    """
    cmd = [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
    ]
    if root_dir != "/":
        root_dir = root_dir.rstrip("/")
    entrypoint = "find"
    args = [root_dir, "-type", "f"]
    if override_entrypoint:
        entrypoint = override_entrypoint
        args = ["find", root_dir, "-type", "f"]
    cmd.append(entrypoint)
    cmd.append(image)
    cmd.extend(args)

    if exclude_hidden_files:
        cmd.extend(["-not", "-path", "'*/\\.*'", "(", "!", "-iname", ".*", ")"])

    LOG.debug(f"Running command: {cmd}")
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
