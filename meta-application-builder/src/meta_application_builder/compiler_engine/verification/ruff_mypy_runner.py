from __future__ import annotations

import asyncio
import pathlib
import tempfile

import structlog

logger = structlog.get_logger(__name__)

class VerificationError(Exception):
    """Raised when ruff or mypy checks fail on emitted code."""
    pass

class RuffMypyRunner:
    @staticmethod
    async def verify_code(code_string: str) -> bool:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = pathlib.Path(tmpdir) / "emitted_module.py"
            file_path.write_text(code_string, encoding="utf-8")

            # Run Ruff check / format
            ruff_proc = await asyncio.create_subprocess_exec(
                "ruff", "check", "--fix", str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await ruff_proc.communicate()

            # Run Mypy strict
            mypy_proc = await asyncio.create_subprocess_exec(
                "mypy", "--strict", str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await mypy_proc.communicate()

            if mypy_proc.returncode != 0:
                err_msg = stderr.decode() or stdout.decode()
                logger.error("mypy_verification_failed", error=err_msg)
                raise VerificationError(f"Mypy verification failed:\n{err_msg}")

        logger.info("code_verification_passed")
        return True