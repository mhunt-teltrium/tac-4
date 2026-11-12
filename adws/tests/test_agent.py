import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent
import health_check
from data_types import AgentPromptRequest, AgentPromptResponse, AgentTemplateRequest


class CopilotAgentTests(unittest.TestCase):
    def test_command_and_last_assistant_message(self):
        events = [
            {"type": "session.start", "sessionID": "session-123"},
            {"type": "assistant.message", "data": {"content": "first"}},
            {"type": "assistant.message", "data": {"content": "final"}},
            {"type": "session.idle"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "raw_output.jsonl")
            request = AgentPromptRequest(
                prompt="test", adw_id="test", model="opus",
                dangerously_skip_permissions=True, output_file=output,
            )

            def run(cmd, **kwargs):
                if "--version" in cmd:
                    return CompletedProcess(cmd, 0, stdout="", stderr="")
                self.assertEqual(cmd, [
                    agent.COPILOT_PATH, "-p", "test", "--model", "claude-opus-4.6",
                    "--output-format", "json", "--stream", "on",
                    "--log-level", "info", "--trust-folder", "--allow-all",
                ])
                for event in events:
                    kwargs["stdout"].write(json.dumps(event) + "\n")
                return CompletedProcess(cmd, 0, stderr="")

            with patch.object(agent.subprocess, "run", side_effect=run):
                response = agent.prompt_copilot(request)
            self.assertTrue(response.success)
            self.assertEqual(response.output, "final")
            self.assertEqual(response.session_id, "session-123")
            with open(os.path.join(directory, "raw_output.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f), events)

    def test_bad_output_is_failure(self):
        for output in ('not json\n', '{"type":"session.idle"}\n',
                       '{"type":"assistant.message","data":{}}\n'):
            with self.subTest(output=output), tempfile.TemporaryDirectory() as directory:
                request = AgentPromptRequest(
                    prompt="test", adw_id="test",
                    output_file=os.path.join(directory, "raw_output.jsonl"),
                )

                def run(cmd, **kwargs):
                    if "--version" not in cmd:
                        self.assertNotIn("--allow-all", cmd)
                        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-opus-4.6")
                        kwargs["stdout"].write(output)
                    return CompletedProcess(cmd, 0, stderr="")

                with patch.object(agent.subprocess, "run", side_effect=run):
                    response = agent.prompt_copilot(request)
                self.assertFalse(response.success)

    def test_cli_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            request = AgentPromptRequest(
                prompt="test", adw_id="test", model="sonnet",
                output_file=os.path.join(directory, "raw_output.jsonl"),
            )

            def run(cmd, **kwargs):
                if "--version" in cmd:
                    return CompletedProcess(cmd, 0, stderr="")
                self.assertEqual(cmd[cmd.index("--model") + 1], "claude-sonnet-4.5")
                return CompletedProcess(cmd, 1, stderr="authentication required")

            with patch.object(agent.subprocess, "run", side_effect=run):
                response = agent.prompt_copilot(request)
            self.assertFalse(response.success)
            self.assertIn("authentication required", response.output)

    def test_template_preserves_argument_boundaries(self):
        request = AgentTemplateRequest(
            agent_name="planner", slash_command="/commit",
            args=["planner", "feature", '{"title": "with spaces"}'], adw_id="test",
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(agent.os.path, "abspath", return_value=os.path.join(directory, "adws", "agent.py")):
                with patch.object(agent, "prompt_copilot", return_value=AgentPromptResponse(output="ok", success=True)) as run:
                    agent.execute_template(request)
        prompt_request = run.call_args.args[0]
        self.assertEqual(
            prompt_request.prompt,
            'Use the skill /commit with these arguments ["planner", "feature", "{\\"title\\": \\"with spaces\\"}"]',
        )
        self.assertEqual(prompt_request.model, "sonnet")
        self.assertTrue(prompt_request.dangerously_skip_permissions)

    def test_health_check_uses_copilot_without_anthropic_key(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(health_check.check_env_vars().success)
        with patch.object(
            health_check, "prompt_copilot",
            return_value=AgentPromptResponse(output="4", success=True),
        ) as run:
            result = health_check.check_copilot()
        self.assertTrue(result.success)
        self.assertEqual(run.call_args.kwargs["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
