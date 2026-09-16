import logging
from pathlib import Path
import re
from meta_telemetry.logging import DateSeqRotatingFileHandler


def test_timestamped_date_seq_cascade(tmp_path: Path):
    app_name = "meta_app_builder"
    max_bytes = 100  # Trigger rotation quickly

    handler = DateSeqRotatingFileHandler(
        base_dir=tmp_path,
        app_name=app_name,
        max_bytes=max_bytes,
    )
    logger = logging.getLogger("test_timestamp_cascade")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    # Write Batch 1
    logger.info("BATCH_1_LOG_DATA_00000_00000_00000_00000_00000")
    logger.info("BATCH_1_LOG_DATA_11111_11111_11111_11111_11111")  # Forces 1st rotation

    # Write Batch 2
    logger.info("BATCH_2_LOG_DATA_22222_22222_22222_22222_22222")
    logger.info("BATCH_2_LOG_DATA_33333_33333_33333_33333_33333")  # Forces 2nd rotation

    # Write Batch 3 (Active log)
    logger.info("BATCH_3_LOG_DATA_44444_44444_44444_44444_44444")

    handler.close()

    # Verify ddmmyy_hhmmss pattern matching
    log_files = sorted(tmp_path.glob("meta_app_builder_*.log"))
    assert len(log_files) >= 3

    pattern = re.compile(r"meta_app_builder_\d{6}_\d{6}(_v\d+)?\.log")
    for file_path in log_files:
        assert pattern.match(file_path.name), f"Filename {file_path.name} does not match ddmmyy_hhmmss standard"

    # Verify log content propagation
    v1_files = list(tmp_path.glob("*_v1.log"))
    assert len(v1_files) > 0
    assert "BATCH_2" in v1_files[0].read_text()