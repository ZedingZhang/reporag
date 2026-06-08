from __future__ import annotations

import json


class TestMCPServerImports:
    def test_server_module_loads(self) -> None:
        from app.mcp.server import (
            create_agent_run_tool,
            get_agent_run_tool,
            resolve_approval_tool,
            search_code_tool,
        )
        assert callable(search_code_tool)
        assert callable(create_agent_run_tool)
        assert callable(get_agent_run_tool)
        assert callable(resolve_approval_tool)

    def test_tool_functions_are_callable(self) -> None:
        from app.mcp.server import (
            create_agent_run_tool,
            get_agent_run_tool,
            resolve_approval_tool,
            search_code_tool,
        )
        for fn in [
            search_code_tool, create_agent_run_tool,
            get_agent_run_tool, resolve_approval_tool,
        ]:
            assert callable(fn)


class TestMCPExampleConfig:
    def test_config_file_exists(self) -> None:
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            ".mcp.example.json",
        )
        assert os.path.exists(path), f"Missing: {path}"

    def test_config_is_valid_json(self) -> None:
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            ".mcp.example.json",
        )
        with open(path) as f:
            data = json.load(f)
        assert "mcpServers" in data
        assert "reporag" in data["mcpServers"]

    def test_config_no_real_keys(self) -> None:
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            ".mcp.example.json",
        )
        with open(path) as f:
            content = f.read()
        assert "sk-" not in content
        assert "ghp_" not in content
        assert "gho_" not in content

    def test_config_has_tools_defined(self) -> None:
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            ".mcp.example.json",
        )
        with open(path) as f:
            content = f.read()
        assert "app.mcp.server" in content
        assert "DATABASE_URL" in content
        assert "DEEPSEEK_API_KEY" in content
