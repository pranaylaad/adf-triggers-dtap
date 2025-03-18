# Helper script that cleans up the mapping json files by
# removing unnecessary fields and formatting the json string
import glob
import json
import os
import re
import sys

def clean_source_and_sink(mapping_json_path) -> bool:
    write_updated_json = False
    source_sink_column_name_diff = False

    with open(mapping_json_path) as fp:
        mapping_object = json.load(fp)

    for mapping in mapping_object["mappings"]:
        # fix sink name if not parquet safe
        current_sink_name = mapping["sink"]["name"]
        parquet_safe_sink_name = re.sub("[,;{}()=\s]+", "_", current_sink_name)
        if current_sink_name != parquet_safe_sink_name:
            mapping["sink"]["name"] = parquet_safe_sink_name
            write_updated_json = True

        # alert on sink and source name being the same
        current_source_name = mapping["source"].get("name")
        current_sink_name = mapping["sink"]["name"]
        if current_source_name != current_sink_name:
            source_sink_column_name_diff = True
    
    validation_error = False
    if write_updated_json:
        print(f"{mapping_json_path} was modified by the script")
        with open(mapping_json_path, "w") as fp:
            json.dump(mapping_object, fp, indent=2)
            fp.write('\n')
        
        validation_error = True

    if not source_sink_column_name_diff:
        print(f"WARN: {mapping_json_path} contains exactly the same source/sink columnnames, mapping might not needed")

    return validation_error

if __name__ == "__main__":
    # get list of all json files in all mappings directories inside the env directory
    glob_string = "env/**/mappings/*.json"
    mapping_json_paths = glob.glob(glob_string, recursive=True)

    had_validation_error = False
    for mapping_json_path in mapping_json_paths:
        if clean_source_and_sink(mapping_json_path):
            had_validation_error = True
    
    if had_validation_error:
        sys.exit(1)