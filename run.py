#!/usr/bin/env python3
"""Flywheel Gear: ASLscp-nacc.

This gear:
1. Reads gear inputs and config via GearContext.
2. Looks up Flywheel metadata (project/subject/session/acquisition labels,
   scan date) and writes metadata.txt where the pipeline's PDF step reads it.
3. Runs pipeline_singlePLD.sh (from the kjobson/aslscp base image) with
   flags built from the gear config.
4. Checks that the expected CBF output exists.
"""

import logging
from datetime import datetime
from pathlib import Path

from fw_gear.context import GearContext
from fw_gear.utils.wrapper import exec_command

log = logging.getLogger(__name__)

PIPELINE_SCRIPT = "/flywheel/v0/pipeline_singlePLD.sh"
# Must match work_dir in pipeline_singlePLD.sh; pdf.py / not1_pdf.py read
# metadata.txt from this directory.
PIPELINE_WORK_DIR = Path("/flywheel/v0/work")


def write_metadata(context: GearContext) -> str:
    """Write Flywheel metadata to metadata.txt and return the subject label.

    Ported from workflows/flywheel_context.py. The only change is where the
    file is written (PIPELINE_WORK_DIR instead of <output>_work), the
    acquisition label (taken from the ASL input's acquisition), and the JSON
    copy of the metadata is no longer written (pdf.py prints every line).
    """
    fw = context.client
    analysis_id = context.config.destination["id"]
    analysis_container = fw.get(analysis_id)
    project_container = fw.get(analysis_container.parents["project"])
    session_container = fw.get(analysis_container.parent["id"])
    subject_container = fw.get(session_container.parents["subject"])

    session_label = session_container.label
    subject_label = subject_container.label
    project_label = project_container.label

    gear_run_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Expected format: ${subject label}x${scan date}x3Tx${studyname}
    scan_date = "Unknown"
    try:
        session_parts = session_label.split("x")
        if len(session_parts) >= 3:
            scan_date = session_parts[1]
            log.info(
                f"Extracted scan date: {scan_date} from session label: {session_label}"
            )
        else:
            log.warning(f"Session label format unexpected: {session_label}")
            log.warning("Expected format: subjectxScanDatex3TxStudyName")
    except Exception as e:
        log.warning(
            f"Could not parse scan date from session label '{session_label}': {e}"
        )
        scan_date = "Unknown"

    # Acquisition label: the acquisition the ASL input file belongs to.
    acquisition_label = "Unknown"
    try:
        asl_parent = context.config.get_input("asl").get("hierarchy", {})
        if asl_parent.get("type") == "acquisition":
            acquisition_label = fw.get(asl_parent["id"]).label
            log.info(f"ASL acquisition: {acquisition_label}")
        else:
            log.warning(
                f"ASL input is not attached to an acquisition (parent: {asl_parent})"
            )
    except Exception as e:
        log.warning(f"Could not determine acquisition label: {e}")
        acquisition_label = "Unknown"

    PIPELINE_WORK_DIR.mkdir(parents=True, exist_ok=True)
    info_out = PIPELINE_WORK_DIR / "metadata.txt"
    try:
        with open(info_out, "w") as f:
            f.write("=== Flywheel Metadata ===\n")
            f.write(f"Project: {project_label}\n")
            f.write(f"Subject: {subject_label}\n")
            f.write(f"Session: {session_label}\n")
            f.write(f"Acquisition: {acquisition_label}\n")
            f.write(f"Analysis ID: {analysis_id}\n")
            f.write(f"Scan Date: {scan_date}\n")
            f.write(f"Gear Run Date/Time: {gear_run_datetime}\n")
            f.write("========================\n")
        log.info(f"Metadata written to: {info_out}")
    except Exception as e:
        log.error(f"Failed to write metadata file: {e}")
        raise

    return subject_label


def build_command(context: GearContext, subject_id: str) -> list[str]:
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
        # Standard mode: <subject_id>_cbf.nii.gz
        pattern = "*_cbf.nii.gz"

    matches = list(output_dir.glob(pattern))
    if not matches:
        raise RuntimeError(f"No CBF map found in {output_dir} matching {pattern}")
    log.info(f"Found CBF output: {matches[0]}")


def main(context: GearContext) -> None:
    """Execute main gear workflow."""
    subject_label = write_metadata(context)

    # Subject ID: gear config if set, otherwise the Flywheel subject label.
    subject_id = context.config.opts.get("subject_id") or subject_label

    cmd = build_command(context, subject_id)
    log.info(f"Running pipeline: {cmd}")
    exec_command(cmd, stream=True)  # raises RuntimeError on non-zero exit

    check_outputs(context)
    log.info("ASLscp-nacc gear completed successfully.")


if __name__ == "__main__":
    with GearContext() as context:
        context.init_logging()
        context.log_config()
        main(context)
