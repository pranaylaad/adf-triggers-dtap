# Helper script that cleans up the mapping json files by
# removing unnecessary fields and formatting the json string
import glob
import json
import os
import re
from copy import copy


def clean_source_and_sink(mapping_object) -> dict:
    """Keep only the name or path field in the source and name field in the sink."""
    new_mapping = copy(mapping_object)
    for col in new_mapping["mappings"]:
        # Source will contain only name or path
        new_source = {}
        for k, v in col["source"].items():
            if k in ("name", "path"):
                new_source[k] = v
        col["source"] = new_source
        # Sink will contain only the name

        sink_name = col["source"].get("name", col["source"].get("path"))
        print(sink_name)
        # We replace spaces with underscores and remove unwated charachters for parquet column names like ',;{}()='
        sink_name = re.sub("[,;{}()=\s]+", "_", sink_name)
        col["sink"] = {"name": sink_name}
    return new_mapping


def trim_json_string(json_string: str) -> str:
    """Make JSON string more readable by putting name and path item on one line."""
    _json_string = re.sub(
        r'\s*\{\s*"name":\s*"([^"]*)"\s*\}', r' {"name": "\1"}', json_string
    )
    return (
        re.sub(r'\s*\{\s*"path":\s*"([^"]*)"\s*\}', r' {"path": "\1"}', _json_string)
        + "\n"
    )


if __name__ == "__main__":
    # get list of all json files in all mappings directories inside the env directory
    glob_string = os.path.join(os.path.dirname(__file__), "env/**/mappings/*.json")
    mapping_json_paths = glob.glob(glob_string, recursive=True)
    for mapping_json_path in mapping_json_paths:
        # load json file
        with open(mapping_json_path) as f:
            mapping = json.load(f)
        # clean json file
        clean_mapping = clean_source_and_sink(mapping)
        # get json string
        mapping_json_string = json.dumps(clean_mapping, indent=2)
        # trim json string
        mapping_json_string = trim_json_string(mapping_json_string)
        # write json string to file
        with open(mapping_json_path, "w") as f:
            f.write(mapping_json_string)
