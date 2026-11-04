#!/usr/bin/env python3
"""Flywheel Gear: ASLscp-nacc.

This gear:
1. Reads gear inputs and config via GearContext.
2. Runs pipeline_singlePLD.sh (from the kjobson/aslscp base image) with
   flags built from the gear config. The pipeline itself writes the
   Flywheel metadata (via workflows/flywheel_context.py).
3. Checks that the expected CBF output exists.
"""

import logging
import os
from pathlib import Path

from fw_gear.context import GearContext
from fw_gear.utils.wrapper import exec_command

log = logging.getLogger(__name__)

PIPELINE_SCRIPT = "/flywheel/v0/pipeline_singlePLD.sh"


def build_command(context: GearContext, subject_id) -> list[str]:
    """Build the pipeline_singlePLD.sh command from gear inputs and config."""
    config = context.config.opts

    cmd = [
        "/bin/bash",
        PIPELINE_SCRIPT,
        "-a",
        str(context.config.get_input_path("asl")),
        "-m",
        str(context.config.get_input_path("m0")),
    ]

    t1w_path = context.config.get_input_path("t1w")
    if t1w_path is not None:
        cmd.extend(["-t", str(t1w_path)])

    # Optional overrides; if not set, the pipeline scrapes the DICOM header.
    for key, flag in [("ld", "-l"), ("pld", "-p"), ("nbs", "-n"), ("m0_scale", "-k")]:
        value = config.get(key)
        if value is not None:
            cmd.extend([flag, str(value)])

    if subject_id:
        cmd.extend(["-s", subject_id])

    if config.get("skip_extended", False):
        cmd.append("-e")
    if config.get("run_t1w_reg", False):
        cmd.append("-r")
    if config.get("bids_output", False):
        cmd.append("-b")

    return cmd


def check_outputs(context: GearContext) -> None:
    """Raise if the CBF map was not produced."""
    output_dir = Path(context.output_dir)
    if context.config.opts.get("bids_output", False):
        # BIDS mode: derivatives/aslscp/sub-X/[ses-Y/]perf/<prefix>_desc-cbf_asl.nii.gz
        pattern = "derivatives/**/*_desc-cbf_asl.nii.gz"
    else:
        # Standard mode: <subject_id>_cbf.nii.gz, or cbf.nii.gz if no subject ID
        pattern = "*cbf.nii.gz"

    matches = list(output_dir.glob(pattern))
    if not matches:
        raise RuntimeError(f"No CBF map found in {output_dir} matching {pattern}")
    log.info(f"Found CBF output: {matches[0]}")


def main(context: GearContext) -> None:
    """Execute main gear workflow."""
    # Subject ID from gear config; if not set, the pipeline uses the
    # Flywheel subject label from its metadata.
    subject_id = context.config.opts.get("subject_id")

    cmd = build_command(context, subject_id)
    log.info(f"Running pipeline: {cmd}")
    # Put /opt/gear-bin first so the pipeline's `python3` is the system Python
    # (which has its packages), not FSL's.
    env = {"PATH": "/opt/gear-bin:" + os.environ.get("PATH", "")}
    exec_command(cmd, stream=True, environ=env)  # raises RuntimeError on non-zero exit

    check_outputs(context)
    log.info("ASLscp-nacc gear completed successfully.")


if __name__ == "__main__":
    with GearContext() as context:
        context.init_logging()
        context.log_config()
        main(context)
