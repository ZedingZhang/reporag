from __future__ import annotations

from app.security.policy import ApprovalPolicy, RiskLevel, classify_risk


class TestClassifyRisk:
    def test_apply_patch_is_high(self) -> None:
        assert classify_risk("apply_patch") == RiskLevel.HIGH

    def test_create_pr_is_high(self) -> None:
        assert classify_risk("create_pr") == RiskLevel.HIGH

    def test_read_only_is_low(self) -> None:
        assert classify_risk("read_only") == RiskLevel.LOW

    def test_run_pytest_is_medium(self) -> None:
        assert classify_risk("run_command", ["pytest"]) == RiskLevel.MEDIUM

    def test_run_rm_is_high(self) -> None:
        assert classify_risk("run_command", ["rm", "-rf"]) == RiskLevel.HIGH

    def test_run_curl_is_high(self) -> None:
        assert classify_risk("run_command", ["curl", "http://example.com"]) == RiskLevel.HIGH


class TestApprovalPolicy:
    def setup_method(self) -> None:
        self.policy = ApprovalPolicy()

    def test_requires_approval_for_high_risk(self) -> None:
        assert self.policy.requires_approval("apply_patch")

    def test_requires_approval_for_run_command(self) -> None:
        assert self.policy.requires_approval("run_command", ["pytest"])

    def test_no_approval_for_low_risk(self) -> None:
        assert not self.policy.requires_approval("read_only")

    def test_auto_allowed_for_low_risk_in_any_mode(self) -> None:
        assert self.policy.is_auto_allowed("read_only", "plan_only")
        assert self.policy.is_auto_allowed("read_only", "execute_after_approval")

    def test_not_auto_allowed_for_medium_in_execute_mode(self) -> None:
        assert not self.policy.is_auto_allowed(
            "run_command", "execute_after_approval", ["pytest"],
        )


class TestPathGuard:
    def test_allows_normal_path(self) -> None:
        import os

        from app.security.path_guard import PathGuard
        guard = PathGuard(os.getcwd())
        result = guard.check_write("tests/test_citations.py")
        assert result.allowed, result.reason

    def test_blocks_parent_traversal(self) -> None:
        from app.security.path_guard import PathGuard
        guard = PathGuard("/tmp/workspace")
        result = guard.check_write("../etc/passwd")
        assert not result.allowed

    def test_blocks_env_file(self) -> None:
        import os

        from app.security.path_guard import PathGuard
        guard = PathGuard(os.getcwd())
        result = guard.check_write(".env")
        assert not result.allowed

    def test_blocks_git_dir(self) -> None:
        import os

        from app.security.path_guard import PathGuard
        guard = PathGuard(os.getcwd())
        result = guard.check_write(".git/config")
        assert not result.allowed

    def test_blocks_prefix_sibling_escape(self) -> None:
        from app.security.path_guard import PathGuard
        guard = PathGuard("/tmp/work")
        assert not guard.check_write("/tmp/work_evil/file.py").allowed

    def test_relative_path_resolves_under_root(self) -> None:
        from app.security.path_guard import PathGuard
        guard = PathGuard("/tmp/work")
        assert guard.check_write("tests/test_x.py").allowed

    def test_read_blocks_outside_workspace(self) -> None:
        from app.security.path_guard import PathGuard
        guard = PathGuard("/tmp/work")
        assert not guard.check_read("/etc/passwd").allowed

    def test_blocks_env_suffix(self) -> None:
        import os

        from app.security.path_guard import PathGuard
        guard = PathGuard(os.getcwd())
        result = guard.check_write(".env.production")
        assert not result.allowed

    def test_blocks_credentials_filename(self) -> None:
        import os

        from app.security.path_guard import PathGuard
        guard = PathGuard(os.getcwd())
        result = guard.check_write("config/credentials.json")
        assert not result.allowed
