#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

"""Module containing utilities for extracting env options used in testing.

This module is intended to be used with pre-built ROCK meta information
produced by the canonical/k8s-workflows/build_rocks.yaml workflow:

https://github.com/canonical/k8s-workflows/blob/main/.github/workflows/build_rocks.yaml#L125-L133
"""

import json
import os
from dataclasses import dataclass
from typing import Dict, List

DEFAULT_BUILT_ROCKS_METADATA_ENV_VAR = "BUILT_ROCKS_METADATA"


def must_get_env_var(var_name: str) -> str:
    """Reads the environment variable with the given name.

    :raises EnvironmentError: when the variable isn't set or is empty.
    """
    val = os.getenv(var_name, default="")
    if not val:
        raise EnvironmentError(
            f"Environment variable '{var_name}' is not defined. "
            f"Current environment contains: {dict(os.environ)}"
        )
    return val


@dataclass
class RockMetaInfo:
    """Class representing metadata for a built ROCK as produced by the
    canonical/k8s-workflows/build_rocks.yaml workflow:

    https://github.com/canonical/k8s-workflows/blob/main/.github/workflows/build_rocks.yaml#L125-L133
    """

    name: str
    version: str
    rock_dir: str
    arch: str
    image: str
    runs_on: List[str]
    rockcraft_revision: str

    @classmethod
    def from_dict(cls, dict_val: Dict[str, str]) -> "RockMetaInfo":
        """Loads fields from the given dict of the form:
        {
            "name": rockName,
            "version": rockVersion,
            "path": rockPath,
            "arch": arch,
            "image": image,
            "rockcraft-revision": rockcraftRevisions[arch] || '',
            "runs-on-labels": platformLabels[arch] || [inputs["runs-on"]]
        }

        :raises ValueError: on missing or null-valued fields.
        """
        kwarg_to_key_map = {
            "name": "name",
            "version": "version",
            "rock_dir": "path",
            "arch": "arch",
            "image": "image",
            "rockcraft_revision": "rockcraft-revision",
            "runs_on": "runs-on-labels",
        }
        init_kwargs = {
            kwarg: dict_val.get(dict_key, None)
            for kwarg, dict_key in kwarg_to_key_map.items()
        }
        unset_keys = [
            dict_key
            for kwarg, dict_key in kwarg_to_key_map.items()
            if init_kwargs[kwarg] is None
        ]
        if unset_keys:
            raise ValueError(
                f"Missing ROCK build meta info fields {unset_keys} from "
                f"the provided dict: {dict_val}"
            )

        return cls(**init_kwargs)  # pyright: ignore

    @classmethod
    def from_json_string(cls, json_str: str) -> "RockMetaInfo":
        """Loads fields from JSON string with object of the form:
        {
            name: rockName,
            version: rockVersion,
            path: rockPath,
            arch: arch,
            image: image,
            "rockcraft-revision": rockcraftRevisions[arch] || '',
            "runs-on-labels": platformLabels[arch] || [inputs["runs-on"]]
        }

        :raises json.decoder.JSONDecodeError: on invalid JSON input.
        :raises ValueError: on missing or null-valued fields.
        """
        return cls.from_dict(json.loads(json_str))

    @property
    def rockcraft_yaml_file_path(self) -> str:
        """Returns the path to the rockcraft.yaml file for this image
        based on the `path` property (RockMetaInfo.rock_dir) of the
        ROCK's meta info.

        Note that this can be a relative path with respect to the root
        of the repository the `build_rocks.yaml` workflow had run on.
        """
        return os.path.join(self.rock_dir, "rockcraft.yaml")


def get_rocks_meta_info_from_env(
    rock_metadata_env_var: str = DEFAULT_BUILT_ROCKS_METADATA_ENV_VAR,
) -> List[RockMetaInfo]:
    """Attempts to parse the `RockMetaInfo`s from the JSON string
    from the env var with the given name as produced by the
    canonical/k8s-workflows/build_rocks.yaml workflow:

    https://github.com/canonical/k8s-workflows/blob/main/.github/workflows/build_rocks.yaml#L125-L133

    :raises EnvironmentError: when the env variable isn't set or is empty.
    :raises json.decoder.JSONDecodeError: on invalid JSON input.
    :raises ValueError: on missing, null-valued, or malformed values.
    """
    rock_metas = must_get_env_var(rock_metadata_env_var)

    rock_metas_list = json.loads(rock_metas)

    return [RockMetaInfo.from_dict(d) for d in rock_metas_list]


def get_builds_meta_info_for_rock(
    rock_name: str, rock_metadata_env_var: str = DEFAULT_BUILT_ROCKS_METADATA_ENV_VAR
) -> List[RockMetaInfo]:
    """Returns a list of all build meta info sets for the ROCK with
    the given name (should be one entry per version and architecture
    the ROCK was built for) from the environment variable produced
    by the canonical/k8s-workflows/build_rocks.yaml workflow:

    https://github.com/canonical/k8s-workflows/blob/main/.github/workflows/build_rocks.yaml#L125-L133

    :raises EnvironmentError: when the env variable isn't set or is empty.
    :raises json.decoder.JSONDecodeError: on invalid JSON input.
    :raises ValueError: on missing, null-valued, or malformed values.
    """
    all_metas = get_rocks_meta_info_from_env(rock_metadata_env_var)

    return [r for r in all_metas if r.name == rock_name]


def get_build_meta_info_for_rock_version(
    rock_name: str,
    rock_version: str,
    rock_arch: str,
    rock_metadata_env_var: str = DEFAULT_BUILT_ROCKS_METADATA_ENV_VAR,
) -> RockMetaInfo:
    """Returns the build meta info for the ROCK with the given name,
    version, and architecture from the environment variable produced
    by the canonical/k8s-workflows/build_rocks.yaml workflow:

    https://github.com/canonical/k8s-workflows/blob/main/.github/workflows/build_rocks.yaml#L125-L133

    :raises EnvironmentError: when the env variable isn't set or is empty.
    :raises json.decoder.JSONDecodeError: on invalid JSON input.
    :raises ValueError: on missing, null-valued, or malformed values.
    """
    all_metas = get_rocks_meta_info_from_env(
        rock_metadata_env_var=rock_metadata_env_var
    )

    matches = [
        r
        for r in all_metas
        if r.name == rock_name and (r.version == rock_version) and r.arch == rock_arch
    ]

    if not matches:
        raise ValueError(
            f"Failed to find build metadata for ROCK '{rock_name}' "
            f"with version '{rock_version}' on architecture '{rock_arch}' "
            f"from environment variable '{rock_metadata_env_var}'. The list "
            f"of ROCK build metas extracted from said environment "
            f"variable was: {all_metas}"
        )

    if len(matches) != 1:
        raise ValueError(
            f"Found multiple build metadata sets for ROCK '{rock_name}' "
            f"with version '{rock_version}' on architecture '{rock_arch}' "
            f"from environment variable '{rock_metadata_env_var}'. The list "
            f"of ROCK build metas extracted from said environment "
            f"variable was: {all_metas}"
        )

    return matches[0]
