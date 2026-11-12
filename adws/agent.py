"""Copilot CLI agent module for executing prompts programmatically."""

import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from data_types import AgentPromptRequest, AgentPromptResponse, AgentTemplateRequest

load_dotenv()

COPILOT_PATH = os.getenv("COPILOT_CODE_PATH", "copilot")
MODEL_NAMES = {"sonnet": "claude-sonnet-5.5", "opus": "claude-opus-5.5"}


def check_copilot_installed() -> Optional[str]:
    """Check whether the Copilot CLI is available."""
    try:
        result = subprocess.run([COPILOT_PATH, "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        return f"Error: Copilot CLI is not installed. Expected at: {COPILOT_PATH}"
    except OSError as e:
        return f"Error starting Copilot CLI at {COPILOT_PATH}: {e}"
    if result.returncode != 0:
        return f"Error: Copilot CLI is not functional at: {COPILOT_PATH}: {result.stderr}"
    return None


def parse_jsonl_output(output_file: str) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Return all Copilot events and the last assistant message."""
    with open(output_file, "r", encoding="utf-8") as f:
        messages = [json.loads(line) for line in f if line.strip()]
    if any(not isinstance(message, dict) for message in messages):
        raise ValueError("Copilot output contains a non-object event")
    assistant_message = next(
        (message for message in reversed(messages) if message.get("type") == "assistant.message"),
        None,
    )
    return messages, assistant_message


def convert_jsonl_to_json(jsonl_file: str, messages: List[Dict[str, Any]]) -> str:
    """Save parsed events as a JSON array beside the JSONL file."""
    json_file = os.path.splitext(jsonl_file)[0] + ".json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2)
    print(f"Created JSON file: {json_file}")
    return json_file


def get_copilot_env() -> Dict[str, str]:
    """Preserve the environment needed by Copilot and its authentication."""
    env = os.environ.copy()
    if env.get("GITHUB_PAT"):
        env["GH_TOKEN"] = env["GITHUB_PAT"]
    return env


def save_prompt(prompt: str, adw_id: str, agent_name: str = "ops") -> None:
    """Save a skill prompt to the appropriate logging directory."""
    match = re.match(r"^Use the skill /(\w+) with these arguments", prompt)
    if not match:
        return
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prompt_dir = os.path.join(project_root, "agents", adw_id, agent_name, "prompts")
    os.makedirs(prompt_dir, exist_ok=True)
    prompt_file = os.path.join(prompt_dir, f"{match.group(1)}.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"Saved prompt to: {prompt_file}")


def prompt_copilot(request: AgentPromptRequest, timeout: Optional[float] = None) -> AgentPromptResponse:
    """Execute Copilot with the given prompt configuration."""
    error_msg = check_copilot_installed()
    if error_msg:
        return AgentPromptResponse(output=error_msg, success=False, session_id=None)

    save_prompt(request.prompt, request.adw_id, request.agent_name)
    output_dir = os.path.dirname(request.output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    cmd = [
        COPILOT_PATH, "-p", request.prompt,
        "--model", MODEL_NAMES[request.model],
        "--output-format", "json", "--stream", "on", "--log-level", "info", "--trust-folder",
    ]
    if request.dangerously_skip_permissions:
        cmd.append("--allow-all")

    try:
        with open(request.output_file, "w", encoding="utf-8") as f:
            result = subprocess.run(
                cmd, stdout=f, stderr=subprocess.PIPE, text=True,
                env=get_copilot_env(), timeout=timeout,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            )

        if result.returncode != 0:
            raise RuntimeError(f"Copilot CLI exited with code {result.returncode}: {result.stderr}")

        print(f"Output saved to: {request.output_file}")
        messages, assistant_message = parse_jsonl_output(request.output_file)
        convert_jsonl_to_json(request.output_file, messages)
        if assistant_message is None:
            raise ValueError("Copilot output contains no assistant.message event")
        data = assistant_message.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("content"), str):
            raise ValueError("Copilot assistant.message has no text data.content")
        session_id = next(
            (message["sessionID"] for message in reversed(messages) if isinstance(message.get("sessionID"), str)),
            None,
        )
        return AgentPromptResponse(output=data["content"], success=True, session_id=session_id)
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as e:
        error_msg = f"Error executing Copilot: {e}"
        print(error_msg, file=sys.stderr)
        return AgentPromptResponse(output=error_msg, success=False, session_id=None)


def execute_template(request: AgentTemplateRequest) -> AgentPromptResponse:
    """Execute a Copilot skill with the supplied arguments."""
    prompt = f"Use the skill {request.slash_command} with these arguments {json.dumps(request.args)}"
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(project_root, "agents", request.adw_id, request.agent_name)
    os.makedirs(output_dir, exist_ok=True)
    prompt_request = AgentPromptRequest(
        prompt=prompt,
        adw_id=request.adw_id,
        agent_name=request.agent_name,
        model=request.model,
        dangerously_skip_permissions=True,
        output_file=os.path.join(output_dir, "raw_output.jsonl"),
    )
    return prompt_copilot(prompt_request)
