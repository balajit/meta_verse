from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

import pytest
from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.verification.boot import (
    BootVerificationResult,
    BootVerifier,
)
from meta_service_generator.verification.imports import (
    ImportVerificationResult,
    ImportVerifier,
)
from meta_service_generator.verification.package import (
    PackageVerificationResult,
    PackageVerifier,
)
from meta_service_generator.verification.runner import (
    VerificationPipelineResult,
    VerificationRunner,
)
from meta_service_generator.verification.syntax import (
    SyntaxVerificationResult,
    SyntaxVerifier,
)
from meta_service_generator.verification.tests import (
    TestSuiteExecutionResult,
    TestSuiteVerifier,
)
from meta_service_generator.verification.typing import (
    TypeCheckIssue,
    TypeCheckResult,
    TypeVerifier,
)


class MockSubprocess:
    """Mock process for asyncio.subprocess.Process."""

    def __init__(
        self,
        returncode: int | None = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
        raise_on_kill: type[Exception] | None = None,
        raise_on_communicate: type[Exception] | None = None,
    ) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False
        self._raise_on_kill = raise_on_kill
        self._raise_on_communicate = raise_on_communicate

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._raise_on_communicate:
            raise self._raise_on_communicate
        return self._stdout, self._stderr

    def kill(self) -> None:
        if self._raise_on_kill:
            raise self._raise_on_kill
        self.killed = True


def _async_return(val: Any) -> Callable[..., Any]:
    """Helper to return an async callable for monkeypatching coroutine functions."""

    async def _mock(*args: Any, **kwargs: Any) -> Any:
        return val

    return _mock


# ============================================================================
# BootVerifier Tests
# ============================================================================


class TestBootVerifier:
    def test_init_invalid_timeout_raises_value_error(self) -> None:
        with pytest.raises(
            ValueError, match="timeout_seconds must be greater than zero."
        ):
            BootVerifier(timeout_seconds=0)

        with pytest.raises(
            ValueError, match="timeout_seconds must be greater than zero."
        ):
            BootVerifier(timeout_seconds=-5.0)

    @pytest.mark.asyncio
    async def test_validate_project_root_failures(self, tmp_path: Path) -> None:
        verifier = BootVerifier()

        # Relative path
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_application_boot(Path("relative/path"), "pkg")
        assert exc.value.error_code == "ERR_BOOT_PROJECT_ROOT_INVALID"

        # Missing path
        missing_dir = tmp_path / "non_existent"
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_application_boot(missing_dir, "pkg")
        assert exc.value.error_code == "ERR_BOOT_PROJECT_ROOT_MISSING"

        # File instead of directory
        file_path = tmp_path / "file.txt"
        file_path.write_text("hello", encoding="utf-8")
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_application_boot(file_path, "pkg")
        assert exc.value.error_code == "ERR_BOOT_PROJECT_ROOT_NOT_DIRECTORY"

    @pytest.mark.asyncio
    async def test_validate_package_name_failures(self, tmp_path: Path) -> None:
        verifier = BootVerifier()

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_application_boot(tmp_path, "   ")
        assert exc.value.error_code == "ERR_BOOT_PACKAGE_NAME_EMPTY"

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_application_boot(tmp_path, "invalid-pkg-name")
        assert exc.value.error_code == "ERR_BOOT_PACKAGE_NAME_INVALID"

    @pytest.mark.asyncio
    async def test_verify_boot_success(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        mock_proc = MockSubprocess(
            returncode=0,
            stdout=b"BOOT_INITIALIZING\nBOOT_SUCCESSFUL\n",
            stderr=b"",
        )

        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )

        verifier = BootVerifier()
        res = await verifier.verify_application_boot(tmp_path, "my_package")

        assert res.success is True
        assert res.exit_code == 0
        assert "BOOT_SUCCESSFUL" in res.output
        assert res.error_output is None

    @pytest.mark.asyncio
    async def test_verify_boot_failure_exit_code_or_missing_token(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        mock_proc = MockSubprocess(
            returncode=1,
            stdout=b"BOOT_INITIALIZING\n",
            stderr=b"ImportError: cannot import name app",
        )

        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )

        verifier = BootVerifier()
        res = await verifier.verify_application_boot(tmp_path, "my_package")

        assert res.success is False
        assert res.exit_code == 1
        assert res.error_output == "ImportError: cannot import name app"

    @pytest.mark.asyncio
    async def test_verify_boot_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        mock_proc = MockSubprocess(returncode=None)

        async def mock_wait_for(fut: object, timeout: float) -> tuple[bytes, bytes]:
            raise asyncio.TimeoutError()

        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )
        monkeypatch.setattr(asyncio, "wait_for", mock_wait_for)

        verifier = BootVerifier(timeout_seconds=0.1)
        res = await verifier.verify_application_boot(tmp_path, "my_package")

        assert res.success is False
        assert res.timed_out is True
        assert res.exit_code == -1
        assert "timed out" in (res.error_output or "")

    @pytest.mark.asyncio
    async def test_verify_boot_exceptions(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        verifier = BootVerifier()

        # Tool missing
        def mock_fnf(*args: str, **kwargs: object) -> None:
            raise FileNotFoundError("uv")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_fnf)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_application_boot(tmp_path, "my_pkg")
        assert exc.value.error_code == "ERR_BOOT_VERIFICATION_TOOL_MISSING"

        # OS Error
        def mock_oserr(*args: str, **kwargs: object) -> None:
            raise OSError("Permission denied")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_oserr)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_application_boot(tmp_path, "my_pkg")
        assert exc.value.error_code == "ERR_BOOT_VERIFICATION_PROCESS_ERROR"

        # Internal exception
        def mock_generic_err(*args: str, **kwargs: object) -> None:
            raise RuntimeError("Unexpected error")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_generic_err)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_application_boot(tmp_path, "my_pkg")
        assert exc.value.error_code == "ERR_BOOT_VERIFICATION_INTERNAL"

    @pytest.mark.asyncio
    async def test_terminate_process_branches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 1. Process already terminated
        proc_done = MockSubprocess(returncode=0)
        await BootVerifier._terminate_process(proc_done)

        # 2. ProcessLookupError on kill
        proc_lookup_err = MockSubprocess(
            returncode=None, raise_on_kill=ProcessLookupError()
        )
        await BootVerifier._terminate_process(proc_lookup_err)

        # 3. TimeoutError during communicate
        proc_timeout = MockSubprocess(
            returncode=None, raise_on_communicate=asyncio.TimeoutError()
        )
        await BootVerifier._terminate_process(proc_timeout)

    def test_decode_output_truncation(self) -> None:
        large_bytes = b"a" * (2 * 1024 * 1024 + 100)
        out = BootVerifier._decode_output(large_bytes)
        assert len(out) == 2 * 1024 * 1024


# ============================================================================
# ImportVerifier Tests
# ============================================================================


class TestImportVerifier:
    def test_init_invalid_timeout(self) -> None:
        with pytest.raises(
            ValueError, match="timeout_seconds must be greater than zero."
        ):
            ImportVerifier(timeout_seconds=-1)

    @pytest.mark.asyncio
    async def test_validate_inputs(self, tmp_path: Path) -> None:
        verifier = ImportVerifier()

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_module_import(Path("relative"), "mod")
        assert exc.value.error_code == "ERR_IMPORT_PROJECT_ROOT_INVALID"

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_module_import(tmp_path / "missing", "mod")
        assert exc.value.error_code == "ERR_IMPORT_PROJECT_ROOT_MISSING"

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_module_import(tmp_path, "   ")
        assert exc.value.error_code == "ERR_IMPORT_MODULE_NAME_EMPTY"

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_module_import(tmp_path, "invalid-module")
        assert exc.value.error_code == "ERR_IMPORT_MODULE_NAME_INVALID"

    @pytest.mark.asyncio
    async def test_verify_module_import_success_and_failures(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        verifier = ImportVerifier()

        # Success
        mock_proc = MockSubprocess(returncode=0, stdout=b"", stderr=b"")
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )
        res = await verifier.verify_module_import(tmp_path, "valid_mod")
        assert res.is_importable is True

        # Failure
        mock_proc_fail = MockSubprocess(
            returncode=1, stderr=b"ModuleNotFoundError: No module named foo"
        )
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc_fail)
        )
        res_fail = await verifier.verify_module_import(tmp_path, "bad_mod")
        assert res_fail.is_importable is False
        assert "ModuleNotFoundError" in (res_fail.error_output or "")

        # Timeout
        async def mock_wait_timeout(fut: object, timeout: float) -> tuple[bytes, bytes]:
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", mock_wait_timeout)
        res_tout = await verifier.verify_module_import(tmp_path, "slow_mod")
        assert res_tout.timed_out is True

    @pytest.mark.asyncio
    async def test_verify_module_import_tool_and_os_errors(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        verifier = ImportVerifier()

        def mock_fnf(*args: str, **kwargs: object) -> None:
            raise FileNotFoundError("uv")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_fnf)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_module_import(tmp_path, "mod")
        assert exc.value.error_code == "ERR_IMPORT_VERIFICATION_TOOL_MISSING"

        def mock_oserr(*args: str, **kwargs: object) -> None:
            raise OSError("OS error")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_oserr)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_module_import(tmp_path, "mod")
        assert exc.value.error_code == "ERR_IMPORT_VERIFICATION_PROCESS_ERROR"

    @pytest.mark.asyncio
    async def test_verify_all_imports_structure_checks(self, tmp_path: Path) -> None:
        verifier = ImportVerifier()

        # Missing src dir
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_all_imports(tmp_path, "my_pkg")
        assert exc.value.error_code == "ERR_IMPORT_SOURCE_PACKAGE_MISSING"

        # src/my_pkg is a file
        src_pkg = tmp_path / "src" / "my_pkg"
        src_pkg.parent.mkdir(parents=True)
        src_pkg.write_text("file", encoding="utf-8")
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_all_imports(tmp_path, "my_pkg")
        assert exc.value.error_code == "ERR_IMPORT_SOURCE_PACKAGE_INVALID"

        # No python files
        src_pkg.unlink()
        src_pkg.mkdir(parents=True)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_all_imports(tmp_path, "my_pkg")
        assert exc.value.error_code == "ERR_IMPORT_NO_MODULES"

    @pytest.mark.asyncio
    async def test_verify_all_imports_success_and_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        verifier = ImportVerifier()
        pkg_dir = tmp_path / "src" / "my_pkg"
        pkg_dir.mkdir(parents=True)

        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "service.py").write_text("", encoding="utf-8")

        mock_proc = MockSubprocess(returncode=0)
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )

        results = await verifier.verify_all_imports(tmp_path, "my_pkg")
        assert len(results) == 2
        assert set(r.module_name for r in results) == {"my_pkg", "my_pkg.service"}

        # Submodule fails import
        mock_proc_fail = MockSubprocess(returncode=1, stderr=b"Import Error")
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc_fail)
        )
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_all_imports(tmp_path, "my_pkg")
        assert exc.value.error_code == "ERR_IMPORT_VERIFICATION_FAILED"

    def test_module_name_from_path_failures(self, tmp_path: Path) -> None:
        # File outside src root
        outside_file = tmp_path / "outside.py"
        with pytest.raises(CodeGenerationError) as exc:
            ImportVerifier._module_name_from_path(tmp_path, outside_file)
        assert exc.value.error_code == "ERR_IMPORT_PATH_OUTSIDE_SOURCE"

        # Root init file resulting in empty module name
        src_init = tmp_path / "src" / "__init__.py"
        src_init.parent.mkdir(parents=True, exist_ok=True)
        src_init.write_text("", encoding="utf-8")
        with pytest.raises(CodeGenerationError) as exc:
            ImportVerifier._module_name_from_path(tmp_path, src_init)
        assert exc.value.error_code == "ERR_IMPORT_MODULE_NAME_FAILED"


# ============================================================================
# PackageVerifier Tests
# ============================================================================


class TestPackageVerifier:
    def test_init_invalid_timeout(self) -> None:
        with pytest.raises(
            ValueError, match="timeout_seconds must be greater than zero."
        ):
            PackageVerifier(timeout_seconds=0)

    @pytest.mark.asyncio
    async def test_validate_project_root_failures(self, tmp_path: Path) -> None:
        verifier = PackageVerifier()

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_package(Path("relative"))
        assert exc.value.error_code == "ERR_PACKAGE_PROJECT_ROOT_INVALID"

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_package(tmp_path / "non_existent")
        assert exc.value.error_code == "ERR_PACKAGE_PROJECT_ROOT_MISSING"

    @pytest.mark.asyncio
    async def test_pyproject_validation_failures(self, tmp_path: Path) -> None:
        verifier = PackageVerifier()

        # Missing pyproject.toml
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_package(tmp_path)
        assert exc.value.error_code == "ERR_MISSING_PYPROJECT"

        # pyproject.toml is a directory
        pyproject_dir = tmp_path / "pyproject.toml"
        pyproject_dir.mkdir()
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_package(tmp_path)
        assert exc.value.error_code == "ERR_INVALID_PYPROJECT"

        # pyproject.toml cannot be read / invalid encoding
        pyproject_dir.rmdir()
        pyproject_dir.write_bytes(b"\x80abc")
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_package(tmp_path)
        assert exc.value.error_code == "ERR_PYPROJECT_READ_FAILED"

    @pytest.mark.asyncio
    async def test_verify_package_success_and_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nname='test'", encoding="utf-8"
        )
        verifier = PackageVerifier()

        # Success
        mock_proc = MockSubprocess(returncode=0, stdout=b"Built wheel")
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )
        res = await verifier.verify_package(tmp_path)
        assert res.is_valid is True
        assert res.build_output == "Built wheel"

        # Failure
        mock_fail = MockSubprocess(returncode=1, stderr=b"Build failed")
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_fail)
        )
        res_fail = await verifier.verify_package(tmp_path)
        assert res_fail.is_valid is False
        assert res_fail.error_output == "Build failed"

        # Timeout
        async def mock_wait_timeout(fut: object, timeout: float) -> tuple[bytes, bytes]:
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", mock_wait_timeout)
        res_tout = await verifier.verify_package(tmp_path)
        assert res_tout.timed_out is True

    @pytest.mark.asyncio
    async def test_enforce_package_validity(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
        verifier = PackageVerifier()

        # Pass
        mock_proc = MockSubprocess(returncode=0)
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )
        res = await verifier.enforce_package_validity(tmp_path)
        assert res.is_valid is True

        # Fail
        mock_fail = MockSubprocess(returncode=1, stderr=b"Error in pyproject")
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_fail)
        )
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.enforce_package_validity(tmp_path)
        assert exc.value.error_code == "ERR_PACKAGE_BUILD_FAILED"

    @pytest.mark.asyncio
    async def test_package_tool_and_os_errors(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
        verifier = PackageVerifier()

        def mock_fnf(*args: str, **kwargs: object) -> None:
            raise FileNotFoundError("uv missing")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_fnf)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_package(tmp_path)
        assert exc.value.error_code == "ERR_PACKAGE_VERIFICATION_TOOL_MISSING"

        def mock_oserr(*args: str, **kwargs: object) -> None:
            raise OSError("Access error")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_oserr)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_package(tmp_path)
        assert exc.value.error_code == "ERR_PACKAGE_VERIFICATION_PROCESS_ERROR"


# ============================================================================
# SyntaxVerifier Tests
# ============================================================================


class TestSyntaxVerifier:
    def test_verify_file_failures_and_success(self, tmp_path: Path) -> None:
        verifier = SyntaxVerifier()

        # Non-existent file
        with pytest.raises(CodeGenerationError) as exc:
            verifier.verify_file(tmp_path / "non_existent.py")
        assert exc.value.error_code == "ERR_SYNTAX_FILE_MISSING"

        # Path is a directory
        dir_path = tmp_path / "dir.py"
        dir_path.mkdir()
        with pytest.raises(CodeGenerationError) as exc:
            verifier.verify_file(dir_path)
        assert exc.value.error_code == "ERR_SYNTAX_FILE_INVALID"

        # Valid file
        valid_file = tmp_path / "valid.py"
        valid_file.write_text("x: int = 10\n", encoding="utf-8")
        res_valid = verifier.verify_file(valid_file)
        assert res_valid.is_valid is True

        # Syntax error file
        invalid_file = tmp_path / "invalid.py"
        invalid_file.write_text("def func(:\n", encoding="utf-8")
        res_invalid = verifier.verify_file(invalid_file)
        assert res_invalid.is_valid is False
        assert res_invalid.line_number == 1

        # Unicode decode error
        unicode_file = tmp_path / "bad_unicode.py"
        unicode_file.write_bytes(b"\x80\x81\x82")
        res_unicode = verifier.verify_file(unicode_file)
        assert res_unicode.is_valid is False
        assert "not valid UTF-8" in (res_unicode.error_message or "")

    def test_verify_file_oserror(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        verifier = SyntaxVerifier()
        test_file = tmp_path / "file.py"
        test_file.write_text("print('test')", encoding="utf-8")

        def mock_read_text(*args: object, **kwargs: object) -> str:
            raise OSError("Read failed")

        monkeypatch.setattr(Path, "read_text", mock_read_text)

        with pytest.raises(CodeGenerationError) as exc:
            verifier.verify_file(test_file)
        assert exc.value.error_code == "ERR_SYNTAX_FILE_READ_FAILED"

    def test_verify_directory_failures_and_success(self, tmp_path: Path) -> None:
        verifier = SyntaxVerifier()

        # Non-existent directory
        with pytest.raises(CodeGenerationError) as exc:
            verifier.verify_directory(tmp_path / "missing_dir")
        assert exc.value.error_code == "ERR_SYNTAX_DIRECTORY_MISSING"

        # Not a directory
        file_path = tmp_path / "not_a_dir"
        file_path.write_text("", encoding="utf-8")
        with pytest.raises(CodeGenerationError) as exc:
            verifier.verify_directory(file_path)
        assert exc.value.error_code == "ERR_SYNTAX_DIRECTORY_INVALID"

        # No python files
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()
        with pytest.raises(CodeGenerationError) as exc:
            verifier.verify_directory(empty_dir)
        assert exc.value.error_code == "ERR_SYNTAX_NO_PYTHON_FILES"

        # Directory with valid python files
        (empty_dir / "mod1.py").write_text("a = 1", encoding="utf-8")
        (empty_dir / "mod2.py").write_text("b = 2", encoding="utf-8")
        results = verifier.verify_directory(empty_dir)
        assert len(results) == 2

        # Directory containing a syntax error
        (empty_dir / "bad.py").write_text("class", encoding="utf-8")
        with pytest.raises(CodeGenerationError) as exc:
            verifier.verify_directory(empty_dir)
        assert exc.value.error_code == "ERR_SYNTAX_VERIFICATION_FAILED"


# ============================================================================
# TestSuiteVerifier Tests
# ============================================================================


class TestTestSuiteVerifier:
    def test_init_invalid_timeout(self) -> None:
        with pytest.raises(
            ValueError, match="timeout_seconds must be greater than zero."
        ):
            TestSuiteVerifier(timeout_seconds=-1.0)

    @pytest.mark.asyncio
    async def test_validate_project_root(self, tmp_path: Path) -> None:
        verifier = TestSuiteVerifier()

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.run_test_suite(Path("relative"))
        assert exc.value.error_code == "ERR_TEST_PROJECT_ROOT_INVALID"

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.run_test_suite(tmp_path / "missing")
        assert exc.value.error_code == "ERR_TEST_PROJECT_ROOT_MISSING"

    @pytest.mark.asyncio
    async def test_tests_dir_validation_failures(self, tmp_path: Path) -> None:
        verifier = TestSuiteVerifier()

        # Missing tests dir
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.run_test_suite(tmp_path)
        assert exc.value.error_code == "ERR_MISSING_TESTS_DIR"

        # tests is a file
        tests_file = tmp_path / "tests"
        tests_file.write_text("", encoding="utf-8")
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.run_test_suite(tmp_path)
        assert exc.value.error_code == "ERR_INVALID_TESTS_DIR"

        # No test_*.py files
        tests_file.unlink()
        tests_file.mkdir()
        (tests_file / "helper.py").write_text("", encoding="utf-8")
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.run_test_suite(tmp_path)
        assert exc.value.error_code == "ERR_NO_GENERATED_TESTS"

    @pytest.mark.asyncio
    async def test_run_test_suite_success_and_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text(
            "def test_ok(): pass", encoding="utf-8"
        )

        verifier = TestSuiteVerifier()

        # Passed
        mock_proc = MockSubprocess(returncode=0, stdout=b"1 passed")
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )
        res = await verifier.run_test_suite(tmp_path)
        assert res.passed is True
        assert "1 passed" in res.stdout

        # Failed
        mock_fail = MockSubprocess(returncode=1, stderr=b"1 failed")
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_fail)
        )
        res_fail = await verifier.run_test_suite(tmp_path)
        assert res_fail.passed is False

        # Timeout
        async def mock_wait_timeout(fut: object, timeout: float) -> tuple[bytes, bytes]:
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", mock_wait_timeout)
        res_tout = await verifier.run_test_suite(tmp_path)
        assert res_tout.timed_out is True

    @pytest.mark.asyncio
    async def test_enforce_test_suite_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("", encoding="utf-8")

        verifier = TestSuiteVerifier()

        mock_proc = MockSubprocess(returncode=0)
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )
        res = await verifier.enforce_test_suite_pass(tmp_path)
        assert res.passed is True

        mock_fail = MockSubprocess(returncode=1)
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_fail)
        )
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.enforce_test_suite_pass(tmp_path)
        assert exc.value.error_code == "ERR_TEST_SUITE_EXECUTION_FAILED"

    @pytest.mark.asyncio
    async def test_test_suite_exceptions(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.py").write_text("", encoding="utf-8")

        verifier = TestSuiteVerifier()

        def mock_fnf(*args: str, **kwargs: object) -> None:
            raise FileNotFoundError("uv missing")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_fnf)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.run_test_suite(tmp_path)
        assert exc.value.error_code == "ERR_TEST_VERIFICATION_TOOL_MISSING"

        def mock_oserr(*args: str, **kwargs: object) -> None:
            raise OSError("OS error")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_oserr)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.run_test_suite(tmp_path)
        assert exc.value.error_code == "ERR_TEST_VERIFICATION_PROCESS_ERROR"

        def mock_generic(*args: str, **kwargs: object) -> None:
            raise RuntimeError("Unexpected")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_generic)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.run_test_suite(tmp_path)
        assert exc.value.error_code == "ERR_TEST_VERIFICATION_INTERNAL"


# ============================================================================
# TypeVerifier Tests
# ============================================================================


class TestTypeVerifier:
    def test_init_invalid_timeout(self) -> None:
        with pytest.raises(
            ValueError, match="timeout_seconds must be greater than zero."
        ):
            TypeVerifier(timeout_seconds=0)

    @pytest.mark.asyncio
    async def test_validate_project_root(self, tmp_path: Path) -> None:
        verifier = TypeVerifier()

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_types(Path("relative"))
        assert exc.value.error_code == "ERR_TYPE_PROJECT_ROOT_INVALID"

        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_types(tmp_path / "missing")
        assert exc.value.error_code == "ERR_TYPE_PROJECT_ROOT_MISSING"

    @pytest.mark.asyncio
    async def test_src_dir_validation_failures(self, tmp_path: Path) -> None:
        verifier = TypeVerifier()

        # Missing src dir
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_types(tmp_path)
        assert exc.value.error_code == "ERR_TYPE_SOURCE_MISSING"

        # src is a file
        src_file = tmp_path / "src"
        src_file.write_text("", encoding="utf-8")
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_types(tmp_path)
        assert exc.value.error_code == "ERR_TYPE_SOURCE_INVALID"

    @pytest.mark.asyncio
    async def test_verify_types_success_and_parsed_issues(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        verifier = TypeVerifier()

        # Success
        mock_proc = MockSubprocess(returncode=0, stdout=b"Success: no issues found")
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )
        res = await verifier.verify_types(tmp_path)
        assert res.is_valid is True
        assert len(res.issues) == 0

        # Type errors with codes and without codes
        mypy_out = (
            "src/main.py:12: error: Incompatible types [assignment]\n"
            "src/utils.py:4: error: Function is missing return type hint\n"
            "Unparseable line"
        )
        mock_fail = MockSubprocess(returncode=1, stdout=mypy_out.encode("utf-8"))
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_fail)
        )
        res_fail = await verifier.verify_types(tmp_path)
        assert res_fail.is_valid is False
        assert len(res_fail.issues) == 2
        assert res_fail.issues[0].error_code == "assignment"
        assert res_fail.issues[1].error_code == "unknown"

        # Timeout
        async def mock_wait_timeout(fut: object, timeout: float) -> tuple[bytes, bytes]:
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", mock_wait_timeout)
        res_tout = await verifier.verify_types(tmp_path)
        assert res_tout.timed_out is True

    @pytest.mark.asyncio
    async def test_enforce_type_safety(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        verifier = TypeVerifier()

        # Pass
        mock_proc = MockSubprocess(returncode=0)
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_proc)
        )
        res = await verifier.enforce_type_safety(tmp_path)
        assert res.is_valid is True

        # Fail with issues
        mypy_out = "src/a.py:1: error: Bad type [arg-type]"
        mock_fail = MockSubprocess(returncode=1, stdout=mypy_out.encode("utf-8"))
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_fail)
        )
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.enforce_type_safety(tmp_path)
        assert exc.value.error_code == "ERR_TYPE_CHECK_FAILED"
        assert "[src/a.py:1]" in exc.value.message

        # Fail without parseable issues (raw output fallback)
        mock_raw_fail = MockSubprocess(
            returncode=1, stderr=b"Fatal internal mypy crash"
        )
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", _async_return(mock_raw_fail)
        )
        with pytest.raises(CodeGenerationError) as exc2:
            await verifier.enforce_type_safety(tmp_path)
        assert "Fatal internal mypy crash" in exc2.value.message

    @pytest.mark.asyncio
    async def test_type_tool_and_os_errors(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "src").mkdir()
        verifier = TypeVerifier()

        def mock_fnf(*args: str, **kwargs: object) -> None:
            raise FileNotFoundError("uv")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_fnf)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_types(tmp_path)
        assert exc.value.error_code == "ERR_TYPE_VERIFICATION_TOOL_MISSING"

        def mock_oserr(*args: str, **kwargs: object) -> None:
            raise OSError("OS error")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_oserr)
        with pytest.raises(CodeGenerationError) as exc:
            await verifier.verify_types(tmp_path)
        assert exc.value.error_code == "ERR_TYPE_VERIFICATION_PROCESS_ERROR"


# ============================================================================
# VerificationRunner Tests
# ============================================================================


class TestVerificationRunner:
    @pytest.mark.asyncio
    async def test_input_validation_failures(self, tmp_path: Path) -> None:
        runner = VerificationRunner()

        with pytest.raises(CodeGenerationError) as exc:
            await runner.run_pipeline(Path("relative"), "my_pkg")
        assert exc.value.error_code == "ERR_VERIFICATION_PROJECT_ROOT_INVALID"

        with pytest.raises(CodeGenerationError) as exc:
            await runner.run_pipeline(tmp_path / "missing", "my_pkg")
        assert exc.value.error_code == "ERR_VERIFICATION_PROJECT_ROOT_MISSING"

        file_root = tmp_path / "file.txt"
        file_root.write_text("", encoding="utf-8")
        with pytest.raises(CodeGenerationError) as exc:
            await runner.run_pipeline(file_root, "my_pkg")
        assert exc.value.error_code == "ERR_VERIFICATION_PROJECT_ROOT_INVALID"

        with pytest.raises(CodeGenerationError) as exc:
            await runner.run_pipeline(tmp_path, "   ")
        assert exc.value.error_code == "ERR_VERIFICATION_PACKAGE_NAME_EMPTY"

        with pytest.raises(CodeGenerationError) as exc:
            await runner.run_pipeline(tmp_path, "invalid-package")
        assert exc.value.error_code == "ERR_VERIFICATION_PACKAGE_NAME_INVALID"

    @pytest.mark.asyncio
    async def test_run_pipeline_full_success(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src" / "my_pkg"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("", encoding="utf-8")

        mock_syntax = SyntaxVerifier()
        mock_package = PackageVerifier()
        mock_import = ImportVerifier()
        mock_type = TypeVerifier()
        mock_boot = BootVerifier()
        mock_test = TestSuiteVerifier()

        # Wire dummy results
        mock_syntax.verify_directory = lambda d: (  # type: ignore[assignment]
            SyntaxVerificationResult(
                file_path="src/my_pkg/__init__.py", is_valid=True
            ),
        )

        async def mock_pkg_verify(p: Path) -> PackageVerificationResult:
            return PackageVerificationResult(is_valid=True)

        mock_package.verify_package = mock_pkg_verify  # type: ignore[assignment]

        async def mock_imp_verify(
            p: Path, pkg: str
        ) -> tuple[ImportVerificationResult, ...]:
            return (
                ImportVerificationResult(module_name="my_pkg", is_importable=True),
            )

        mock_import.verify_all_imports = mock_imp_verify  # type: ignore[assignment]

        async def mock_type_verify(p: Path) -> TypeCheckResult:
            return TypeCheckResult(is_valid=True)

        mock_type.verify_types = mock_type_verify  # type: ignore[assignment]

        async def mock_boot_verify(p: Path, pkg: str) -> BootVerificationResult:
            return BootVerificationResult(success=True)

        mock_boot.verify_application_boot = mock_boot_verify  # type: ignore[assignment]

        async def mock_test_verify(p: Path) -> TestSuiteExecutionResult:
            return TestSuiteExecutionResult(passed=True, exit_code=0)

        mock_test.run_test_suite = mock_test_verify  # type: ignore[assignment]

        runner = VerificationRunner(
            syntax_verifier=mock_syntax,
            package_verifier=mock_package,
            import_verifier=mock_import,
            type_verifier=mock_type,
            boot_verifier=mock_boot,
            test_verifier=mock_test,
        )

        res = await runner.run_pipeline(tmp_path, "my_pkg")

        assert isinstance(res, VerificationPipelineResult)
        assert res.syntax_passed is True
        assert res.package_passed is True
        assert res.imports_passed is True
        assert res.typing_passed is True
        assert res.boot_passed is True
        assert res.tests_passed is True

    @pytest.mark.asyncio
    async def test_run_pipeline_gate_failures(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src" / "my_pkg"
        src_dir.mkdir(parents=True)

        mock_syntax = SyntaxVerifier()
        mock_syntax.verify_directory = lambda d: ()  # type: ignore[assignment]

        # Gate 2 Failure: Package Check
        mock_pkg_fail = PackageVerifier()

        async def mock_pkg_invalid(p: Path) -> PackageVerificationResult:
            return PackageVerificationResult(is_valid=False, error_output="Build error")

        mock_pkg_fail.verify_package = mock_pkg_invalid  # type: ignore[assignment]

        runner = VerificationRunner(
            syntax_verifier=mock_syntax, package_verifier=mock_pkg_fail
        )
        with pytest.raises(CodeGenerationError) as exc:
            await runner.run_pipeline(tmp_path, "my_pkg")
        assert exc.value.error_code == "ERR_PACKAGE_BUILD_FAILED"

        # Reusable valid async mocks for subsequent gate tests
        mock_ok_pkg = PackageVerifier()

        async def mock_pkg_ok(p: Path) -> PackageVerificationResult:
            return PackageVerificationResult(is_valid=True)

        mock_ok_pkg.verify_package = mock_pkg_ok  # type: ignore[assignment]

        mock_ok_imp = ImportVerifier()

        async def mock_imp_ok(p: Path, pkg: str) -> tuple[ImportVerificationResult, ...]:
            return ()

        mock_ok_imp.verify_all_imports = mock_imp_ok  # type: ignore[assignment]

        # Gate 4 Failure: Type Check with issues
        mock_type_fail = TypeVerifier()

        async def mock_type_invalid(p: Path) -> TypeCheckResult:
            return TypeCheckResult(
                is_valid=False,
                issues=(
                    TypeCheckIssue(
                        file_path="src/a.py",
                        line_number=1,
                        error_code="attr-defined",
                        message="Missing attribute",
                    ),
                ),
            )

        mock_type_fail.verify_types = mock_type_invalid  # type: ignore[assignment]

        runner_type = VerificationRunner(
            syntax_verifier=mock_syntax,
            package_verifier=mock_ok_pkg,
            import_verifier=mock_ok_imp,
            type_verifier=mock_type_fail,
        )

        with pytest.raises(CodeGenerationError) as exc_type:
            await runner_type.run_pipeline(tmp_path, "my_pkg")
        assert exc_type.value.error_code == "ERR_TYPE_CHECK_FAILED"
        assert "[src/a.py:1]" in exc_type.value.message

        # Gate 5 Failure: Boot Verification
        mock_type_ok = TypeVerifier()

        async def mock_type_valid(p: Path) -> TypeCheckResult:
            return TypeCheckResult(is_valid=True)

        mock_type_ok.verify_types = mock_type_valid  # type: ignore[assignment]

        mock_boot_fail = BootVerifier()

        async def mock_boot_invalid(p: Path, pkg: str) -> BootVerificationResult:
            return BootVerificationResult(success=False, error_output="Lifespan error")

        mock_boot_fail.verify_application_boot = mock_boot_invalid  # type: ignore[assignment]

        runner_boot = VerificationRunner(
            syntax_verifier=mock_syntax,
            package_verifier=mock_ok_pkg,
            import_verifier=mock_ok_imp,
            type_verifier=mock_type_ok,
            boot_verifier=mock_boot_fail,
        )
        with pytest.raises(CodeGenerationError) as exc_boot:
            await runner_boot.run_pipeline(tmp_path, "my_pkg")
        assert exc_boot.value.error_code == "ERR_BOOT_VERIFICATION_FAILED"

        # Gate 6 Failure: Test Suite
        mock_boot_ok = BootVerifier()

        async def mock_boot_valid(p: Path, pkg: str) -> BootVerificationResult:
            return BootVerificationResult(success=True)

        mock_boot_ok.verify_application_boot = mock_boot_valid  # type: ignore[assignment]

        mock_test_fail = TestSuiteVerifier()

        async def mock_test_invalid(p: Path) -> TestSuiteExecutionResult:
            return TestSuiteExecutionResult(passed=False, exit_code=1)

        mock_test_fail.run_test_suite = mock_test_invalid  # type: ignore[assignment]

        runner_test = VerificationRunner(
            syntax_verifier=mock_syntax,
            package_verifier=mock_ok_pkg,
            import_verifier=mock_ok_imp,
            type_verifier=mock_type_ok,
            boot_verifier=mock_boot_ok,
            test_verifier=mock_test_fail,
        )
        with pytest.raises(CodeGenerationError) as exc_test:
            await runner_test.run_pipeline(tmp_path, "my_pkg")
        assert exc_test.value.error_code == "ERR_TEST_SUITE_FAILED"