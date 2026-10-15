
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq
from mcp import Client, StdioServerParameters

load_dotenv()

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
SERVER_PATH = BASE_DIR / "server.py"

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

groq_client = Groq(
    api_key=os.environ["GROQ_API_KEY"]
)

SYSTEM_PROMPT = """
You are a helpful Gmail assistant.

Use the available MCP tools to answer questions about the user's Gmail.
Never claim you read emails unless an MCP tool returned their contents.

You can help with:
- Today's emails and unread emails.
- Searching emails by sender, subject, or keywords.
- Finding job opportunities, interviews, assessments, and offers.
- Identifying actions, deadlines, and important messages.
- Summarizing email content.

When analyzing emails:
- Identify importance and priority.
- Identify whether an action is required.
- State the action requested, if any.
- State deadlines only when supported by the email.
- Use HIGH, MEDIUM, or LOW priority when appropriate.

Never invent emails, actions, or deadlines.
Explain results in simple, organized language.
"""


# --------------------------------------------------
# MCP RESULT HELPERS
# --------------------------------------------------

def normalize_tools_result(result):
    """
    Extract the list of tools from common MCP SDK result formats.
    Some wrappers return (tools, metadata), while standard MCP
    results may expose a .tools attribute.
    """

    if hasattr(result, "tools"):
        tools = result.tools

    elif isinstance(result, tuple):
        # Some clients return a tuple containing tools and metadata.
        tools = next(
            (
                item for item in result
                if isinstance(item, (list, tuple))
                and all(hasattr(tool, "name") for tool in item)
            ),
            None,
        )

        if tools is None:
            raise TypeError(
                "Could not find the tool list in the tuple returned "
                "by mcp_client.list_tools()."
            )

    elif isinstance(result, list):
        tools = result

    else:
        raise TypeError(
            f"Unexpected list_tools result type: {type(result).__name__}"
        )

    for tool in tools:
        if not hasattr(tool, "name"):
            raise TypeError(
                "MCP tool list contains an unexpected item: "
                f"{type(tool).__name__}"
            )

    return list(tools)


def get_tool_schema(tool):
    """Read the input schema from the MCP tool object."""

    schema = getattr(tool, "input_schema", None)

    if schema is None:
        schema = getattr(tool, "inputSchema", None)

    if schema is None:
        schema = {
            "type": "object",
            "properties": {},
        }

    return schema


def extract_tool_text(result):
    """Convert MCP tool results into text for Groq."""

    content = getattr(result, "content", None) or []

    text_parts = [
        item.text
        for item in content
        if getattr(item, "text", None) is not None
    ]

    output = "\n".join(text_parts)

    if getattr(result, "isError", False):
        return f"Tool error: {output or 'The MCP tool failed.'}"

    return output or str(result)


# --------------------------------------------------
# AGENT
# --------------------------------------------------

async def run_agent(
    user_id: str,
    messages: list,
    token_path: str,
) -> str:

    if not SERVER_PATH.is_file():
        raise FileNotFoundError(
            f"MCP server not found: {SERVER_PATH}"
        )

    if not Path(token_path).is_file():
        raise FileNotFoundError(
            f"Gmail token not found for user ID {user_id}."
        )

    # Pass the current user's token to the MCP server.
    server_env = {
        **os.environ,
        "GMAIL_TOKEN_PATH": token_path,
        "GMAIL_CREDENTIALS_PATH": str(
            BASE_DIR / "credentials.json"
        ),
    }

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
        env=server_env,
    )

    agent_messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        *messages,
    ]

    async with Client(server_params) as mcp_client:

        # Retrieve and normalize the available MCP tools.
        tools_result = await mcp_client.list_tools()
        available_tools = normalize_tools_result(tools_result)

        print(
            "Available MCP tools:",
            [tool.name for tool in available_tools],
            file=sys.stderr,
        )

        groq_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": (
                        getattr(tool, "description", "") or ""
                    ),
                    "parameters": get_tool_schema(tool),
                },
            }
            for tool in available_tools
        ]

        # Allow multiple tool calls before returning the final answer.
        for round_number in range(8):

            response = await asyncio.to_thread(
                groq_client.chat.completions.create,
                model=MODEL,
                messages=agent_messages,
                tools=groq_tools if groq_tools else None,
                tool_choice="auto" if groq_tools else "none",
            )

            assistant_message = response.choices[0].message

            agent_messages.append(
                assistant_message.model_dump(
                    exclude_none=True
                )
            )

            # The model has finished responding.
            if not assistant_message.tool_calls:
                return (
                    assistant_message.content
                    or "I couldn't generate a response."
                )

            # Execute every requested MCP tool.
            for tool_call in assistant_message.tool_calls:

                tool_name = tool_call.function.name

                try:
                    arguments = json.loads(
                        tool_call.function.arguments or "{}"
                    )

                    result = await mcp_client.call_tool(
                        tool_name,
                        arguments,
                    )

                    tool_output = extract_tool_text(result)

                except Exception as exc:
                    print(
                        f"Tool {tool_name} failed: "
                        f"{type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )

                    tool_output = (
                        f"Tool {tool_name} failed: "
                        f"{type(exc).__name__}: {exc}"
                    )

                agent_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_output[:20000],
                })

        return (
            "I reached the tool-call limit. "
            "Please try a more specific request."
        )
