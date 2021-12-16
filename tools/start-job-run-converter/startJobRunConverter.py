#!/usr/bin/env python
import argparse
import json
import os
import re
import shlex
import sys

OUTPUT_FILE_SUFFIX = "_converted"
AUTO_CONVERT_MSG = "\n# ----- Auto converted by {} -----\n"

SPARK_SUBMIT = "spark-submit"
SPARK_UNARY_ARGUMENTS = {"-v", "--verbose"}
CONVERTER_ARGUMENTS = {"file"}


def add_quote(data, quote="\"", guard=" "):
    if isinstance(data, list):
        data = [quote + d + quote if guard in d and not d.startswith(quote) else d for d in data]
    elif isinstance(data, str):
        data = quote + data + quote if guard in data and not data.startswith(quote) else data
    return data


# In argparse, any internal - characters will be converted to _ characters to make sure the string
# is a valid attribute name e.g. execution_role_arn.
# This function change it back, e.g. execution-role-arn
def normalize_arg_key(arg):
    return arg.replace("_", "-")


# In bash shell, single quote won't expand a variable. Need to close the single quotes,
# insert variable, and then re-enter again.
def convert_matched_var(match_obj):
    if match_obj.group() is not None:
        return "'\"" + match_obj.group() + "\"'"
    return ""

# This function assumes a valid spark-submit command, otherwise it throws exception
def generate_start_job_cmd(spark_cmd_line, start_job_args):
    start_job_cmd = "aws emr-containers start-job-run \\\n"
    start_idx, curr_idx = 0, 0
    while curr_idx < len(spark_cmd_line):
        curr_arg = spark_cmd_line[curr_idx].strip()
        if curr_arg:
            if SPARK_SUBMIT in curr_arg:
                start_idx = curr_idx + 1
            elif curr_arg.startswith("-"):
                if curr_arg not in SPARK_UNARY_ARGUMENTS:
                    curr_idx += 1  # the argument is a pair e.g. --num-executors 50
            else:
                break
        curr_idx += 1
    spark_submit_parameters = add_quote(spark_cmd_line[start_idx: curr_idx])
    entrypoint_location = spark_cmd_line[curr_idx]
    entrypoint_arguments = add_quote(spark_cmd_line[curr_idx + 1:])
    job_driver = {"sparkSubmitJobDriver": {
        "entryPoint": entrypoint_location,
        "entryPointArguments": entrypoint_arguments,
        "sparkSubmitParameters": " ".join(spark_submit_parameters)
    }}

    res_str = add_quote(json.dumps(job_driver, indent=4), quote="'", guard="\n")
    res_str = re.sub(r"\${?[0-9a-zA-Z_]+}?", convert_matched_var, res_str)
    start_job_args["job_driver"] = res_str + "\n"

    for k, v in start_job_args.items():
        if k not in CONVERTER_ARGUMENTS and v:
            start_job_cmd += "--" + normalize_arg_key(k) + " " + add_quote(v, quote="'", guard="\n") + " \\\n"
    return start_job_cmd[:len(start_job_cmd) - 2] + "\n"


def convert_file(input, output, extra_args, banner="\n"):
    with open(input, "r") as input_fp:
        with open(output, "w") as output_fp:
            in_cmd = False
            cmd_line = ""
            for line in input_fp:
                new_line = line.strip()
                if new_line and ((new_line[0] != "#" and SPARK_SUBMIT in new_line) or in_cmd):
                    output_fp.write("#" + line)  # Keep the original lines in comment
                    in_cmd = True
                    cmd_line += new_line
                    if new_line[-1] != "\\":
                        converted_cmd = generate_start_job_cmd(shlex.split(cmd_line), extra_args)
                        output_fp.write(banner)
                        output_fp.writelines(str(converted_cmd) + "\n")
                        in_cmd = False
                        cmd_line = ""
                else:
                    output_fp.write(line)


if __name__ == '__main__':
    # Create the parser
    cmd_parser = argparse.ArgumentParser(description='A tool for converting spark-sumbit command line to EMR on EKS '
                                                     'start-job-run.')

    # Add the arguments
    cmd_parser.add_argument('--file', help='the input spark-submit script file', required=True)
    cmd_parser.add_argument('--name', help='The name of the job run')
    cmd_parser.add_argument('--virtual-cluster-id', help='The virtual cluster ID for which the job run request is submitted', required=True)
    cmd_parser.add_argument('--client-token', help='The client idempotency token of the job run request')
    cmd_parser.add_argument('--execution-role-arn', help='The execution role ARN for the job run', required=True)
    cmd_parser.add_argument('--release-label', help='The Amazon EMR release version to use for the job run', required=True)
    cmd_parser.add_argument('--configuration-overrides', help='The configuration overrides for the job run')
    cmd_parser.add_argument('--tags', help='The tags assigned to job runs')

    args = cmd_parser.parse_args()

    input_file = args.file
    output_file = os.path.basename(input_file) + OUTPUT_FILE_SUFFIX

    if os.path.exists(output_file):
        print("Error: {} already exists.".format(output_file))
        sys.exit(1)

    convert_file(input_file, output_file, vars(args),
                 AUTO_CONVERT_MSG.format(os.path.basename(sys.argv[0])))
