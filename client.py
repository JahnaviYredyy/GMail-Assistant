
import asyncio
import json
import os
import re
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq
from mcp import Client, StdioServerParameters


# ============================================================
# 1. CONFIGURATION
# ============================================================

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY is not set. Check your .env file."
    )

MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b",
)

MAX_TOOL_ROUNDS = 5

BASE_DIR = Path(__file__).resolve().parent
SKILLS_DIR = BASE_DIR / "skills"

groq_client = Groq(api_key=GROQ_API_KEY)


# ============================================================
# 2. SKILL DISCOVERY
# ============================================================

def discover_skills():
    """Discover skills stored under skills/<skill-name>/."""

    skills = []

    if not SKILLS_DIR.exists():
        print(f"Skills directory not found: {SKILLS_DIR}")
        return skills

    skill_files = list(SKILLS_DIR.glob("*/SKILL.md"))
    skill_files += list(SKILLS_DIR.glob("*/skill.md"))

    # Avoid loading the same file twice on case-insensitive systems.
    seen_paths = set()

    for skill_path in skill_files:
        normalized_path = str(skill_path.resolve()).lower()

        if normalized_path in seen_paths:
            continue

        seen_paths.add(normalized_path)

        try:
            raw_content = skill_path.read_text(
                encoding="utf-8"
            )

            name = skill_path.parent.name
            description = ""
            instructions = raw_content

            if raw_content.startswith("---"):
                parts = raw_content.split("---", 2)

                if len(parts) == 3:
                    metadata = parts[1]
                    instructions = parts[2].strip()

                    for line in metadata.splitlines():
                        key, separator, value = line.partition(":")

                        if not separator:
                            continue

                        key = key.strip().lower()
                        value = value.strip().strip('"').strip("'")

                        if key == "name":
                            name = value

                        elif key == "description":
                            description = value

            skills.append({
                "name": name,
                "description": description,
                "instructions": instructions,
                "path": str(skill_path),
            })

            print(f"Loaded skill: {name}")

        except OSError as exc:
            print(f"Could not load {skill_path}: {exc}")

    return skills


def choose_skill(user_request, skills):
    """Choose the file-creation skill for document requests."""

    request = user_request.lower()

    file_phrases = [
        "create a document",
        "create document",
        "create a word",
        "create a file",
        "create a report",
        "generate a document",
        "generate document",
        "generate a file",
        "generate a report",
        "make a document",
        "make a word document",
        "word document",
        "word file",
        "save as docx",
        "export to word",
    ]

    asks_for_file = any(
        phrase in request
        for phrase in file_phrases
    )

    if not asks_for_file:
        return None

    for skill in skills:
        searchable = (
            skill["name"] + " " + skill["description"]
        ).lower()

        if any(
            word in searchable
            for word in ("file", "document", "word", "report")
        ):
            return skill

    return None


# ============================================================
# 3. DETECT THE TYPE OF REQUEST
# ============================================================

def request_needs_email_data(user_request):
    """
    Return True when the user asks to retrieve or analyze emails.

    Generic requests such as 'Create a document about mathematics'
    do not need Gmail retrieval.
    """

    request = user_request.lower()

    email_phrases = [
        "email",
        "emails",
        "e-mail",
        "gmail",
        "unread",
        "inbox",
        "received mail",
        "received mails",
        "received email",
        "received emails",
        "my mail",
        "my mails",
        "my messages",
        "my emails",
        "today's mail",
        "today's mails",
        "today's emails",
        "yesterday's mail",
        "yesterday's mails",
        "yesterday's emails",
        "this month's mails",
        "this month's emails",
        "this month mails",
        "this month emails",
        "important mails",
        "important emails",
        "action items from",
        "summarize my",
        "summarise my",
        "deadline in my",
        "deadlines in my",
    ]

    return any(
        phrase in request
        for phrase in email_phrases
    )


# ============================================================
# 4. MCP TOOL CONVERSION
# ============================================================

def convert_mcp_tools_to_groq(mcp_tools):
    """Convert MCP tool schemas to Groq's function-tool format."""

    groq_tools = []

    for tool in mcp_tools:
        groq_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        })

    return groq_tools


def extract_tool_output(result):
    """Convert an MCP result into readable text."""

    if getattr(result, "isError", False):
        error_parts = []

        for item in getattr(result, "content", []) or []:
            text_value = getattr(item, "text", None)

            if text_value:
                error_parts.append(text_value)

        return "TOOL ERROR: " + (
            "\n".join(error_parts)
            or "The MCP tool returned an error."
        )

    output_parts = []

    for item in getattr(result, "content", []) or []:
        text_value = getattr(item, "text", None)

        if text_value:
            output_parts.append(text_value)

    if output_parts:
        return "\n".join(output_parts)

    structured = getattr(result, "structuredContent", None)

    if structured is not None:
        return json.dumps(
            structured,
            ensure_ascii=False,
            default=str,
        )

    return str(result)


# ============================================================
# 5. GENERAL TOOL-CALLING AGENT
# ============================================================

async def run_tool_agent(
    mcp_client,
    groq_tools,
    messages,
):
    """
    Let Groq select tools and execute those tools through MCP.

    Tool-enabled requests use tool_choice='auto'.
    Text-only requests are handled by separate functions below.
    """

    for round_number in range(MAX_TOOL_ROUNDS):
        print(
            f"\nAgent is thinking... "
            f"(round {round_number + 1}/{MAX_TOOL_ROUNDS})"
        )

        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=groq_tools,
            tool_choice="auto",
        )

        assistant_message = response.choices[0].message

        messages.append(
            assistant_message.model_dump(exclude_none=True)
        )

        tool_calls = assistant_message.tool_calls or []

        if not tool_calls:
            return assistant_message.content or ""

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            raw_arguments = tool_call.function.arguments or "{}"

            print(f"\nAgent selected tool: {tool_name}")

            try:
                arguments = json.loads(raw_arguments)

                if not isinstance(arguments, dict):
                    raise ValueError(
                        "Tool arguments must be a JSON object."
                    )

                print(
                    "Tool arguments:\n"
                    + json.dumps(
                        arguments,
                        indent=2,
                        ensure_ascii=False,
                    )
                )

                result = await mcp_client.call_tool(
                    tool_name,
                    arguments,
                )

                tool_output = extract_tool_output(result)

            except Exception as exc:
                tool_output = (
                    f"TOOL ERROR: {type(exc).__name__}: {exc}"
                )

            print("\nTool result:")
            print(tool_output)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_output,
            })

    return (
        "The agent reached the maximum tool-calling rounds. "
        "The requested task may not have completed."
    )


# ============================================================
# 6. EMAIL RETRIEVAL AGENT
# ============================================================

async def email_retrieval_agent(
    mcp_client,
    groq_tools,
    user_request,
):
    """Retrieve the emails relevant to the user's request."""

    available_tools = [
        item["function"]["name"]
        for item in groq_tools
    ]

    current_date = datetime.now().strftime("%Y-%m-%d")

    system_prompt = f"""
You are the Gmail email retrieval agent.

Today's date is {current_date}.

Available tools:
{", ".join(available_tools)}

Your task is to retrieve relevant emails through the tools.

Rules:
- Use get_unread_emails for unread-email requests.
- Use get_todays_emails for emails received today.
- Use search_emails for senders, subjects, companies, date
  ranges, keywords, and other Gmail searches.
- Use get_email when the user requests a specific email and
  that tool is available.
- Use the appropriate Gmail search operators.
- For unread emails received this month, use is:unread and
  an explicit date range based on today's date.
- For emails from a specific month, calculate the correct
  date range rather than guessing.
- Do not invent senders, subjects, dates, email contents,
  actions, or deadlines.
- Retrieve emails before analyzing them.
- Report honestly when no matching emails are found.
- Do not create documents in this step.
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_request,
        },
    ]

    return await run_tool_agent(
        mcp_client,
        groq_tools,
        messages,
    )


# ============================================================
# 7. TEXT-ONLY GROQ HELPER
# ============================================================

def generate_text(system_prompt, user_prompt):
    """
    Generate text without providing any tools.

    IMPORTANT:
    Do not pass tool_choice='none' here. Some model/tool
    combinations may still emit a tool call and trigger a 400.
    Omitting both tools and tool_choice avoids that conflict.
    """

    response = groq_client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    message = response.choices[0].message

    if message.tool_calls:
        raise RuntimeError(
            "The model returned a tool call during a text-only "
            "request. No tools were provided to this request. "
            "Check the selected model and GROQ_MODEL setting."
        )

    content = message.content or ""

    if not content.strip():
        raise RuntimeError(
            "The model returned an empty text response."
        )

    return content


# ============================================================
# 8. EMAIL ANALYSIS AGENT
# ============================================================

def email_analysis_agent(
    user_request,
    retrieved_emails,
):
    """Analyze retrieved emails without executing tools."""

    system_prompt = """
You are the Gmail email analysis agent.

Analyze the email results supplied by the retrieval agent.

Rules:
- Base your answer on the supplied email results.
- Do not invent emails, facts, actions, or deadlines.
- Identify important emails based on their actual content.
- Identify explicit actions and deadlines.
- If no deadline is provided, write 'Not specified'.
- Separate facts from interpretations.
- Classify emails when relevant:
  Job Opportunity, Interview / Recruitment, Assessment /
  Rejection, Offer, Work, Personal, Newsletter, Promotion,
  Other.
- For action items, include:
  Importance, Action Required, Action, Deadline, Priority,
  and Reason where supported by the email.
- Do not treat every promotional email as urgent.
- Do not add unrelated general information.
- If no emails were found, state that clearly.
- Do not create Word files in this step.
"""

    user_prompt = (
        f"User request:\n{user_request}\n\n"
        f"Retrieved email results:\n{retrieved_emails}"
    )

    return generate_text(
        system_prompt,
        user_prompt,
    )


# ============================================================
# 9. DOCUMENT CONTENT GENERATION
# ============================================================

def create_document_content(
    user_request,
    source_information,
    selected_skill=None,
):
    """
    Generate document content only.

    This function does not execute MCP tools and does not pass
    tool_choice='none' to Groq.
    """

    skill_instructions = ""

    if selected_skill:
        skill_instructions = selected_skill.get(
            "instructions",
            "",
        )

    system_prompt = f"""
You are a professional document-writing agent.

Prepare the content for a Word document that satisfies the
user's request.

Skill instructions:
{skill_instructions or "Create a clear, professional document."}

Rules:
- Follow the requested topic.
- Use a meaningful title and clear headings.
- Use bullet points or numbered lists where appropriate.
- If the source is email analysis, preserve the relevant
  email summaries, actions, and deadlines.
- Do not invent email details or claim an action was required
  when the source does not support that conclusion.
- For a general topic, write relevant content about that
  topic instead of inventing Gmail information.
- Do not include unrelated information.
- Return only the document content.
- Do not attempt to call tools.
"""

    user_prompt = (
        f"User request:\n{user_request}\n\n"
        f"Source information:\n{source_information}\n\n"
        "Write the complete content for the Word document."
    )

    return generate_text(
        system_prompt,
        user_prompt,
    )


# ============================================================
# 10. DOCUMENT FILENAME
# ============================================================

def extract_document_title(content, user_request):
    """Extract the first Markdown heading or derive a title."""

    for line in content.splitlines():
        match = re.match(
            r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$",
            line,
        )

        if match:
            return match.group(1).strip()

    # Fall back to the user's request.
    cleaned = re.sub(
        r"(?i)\b(create|generate|make|write)\b",
        "",
        user_request,
    )

    cleaned = re.sub(
        r"(?i)\b(a|an|the|document|word file|word document|"
        r"report|file|about|on)\b",
        " ",
        cleaned,
    )

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-")

    return cleaned.title() if cleaned else "Gmail Summary"


def make_safe_filename(title):
    """Create a safe Word document filename."""

    filename = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "",
        title,
    )

    filename = re.sub(
        r"\s+",
        "_",
        filename,
    ).strip("._ ")

    if not filename:
        filename = "Gmail_Summary"

    if not filename.lower().endswith(".docx"):
        filename += ".docx"

    return filename


# ============================================================
# 11. DOCUMENT CREATION AGENT
# ============================================================

async def document_agent(
    mcp_client,
    mcp_tools,
    user_request,
    source_information,
    selected_skill=None,
):
    """
    Generate document content, then invoke the actual MCP
    create_word_file tool directly.
    """

    document_tool = next(
        (
            tool
            for tool in mcp_tools
            if tool.name.split(".")[-1] == "create_word_file"
        ),
        None,
    )

    if document_tool is None:
        available_names = [
            tool.name for tool in mcp_tools
        ]

        raise RuntimeError(
            "The MCP server does not expose create_word_file. "
            f"Available tools: {available_names}"
        )

    print("\nDocument agent is preparing the content...")

    content = create_document_content(
        user_request,
        source_information,
        selected_skill,
    )

    title = extract_document_title(
        content,
        user_request,
    )

    filename = make_safe_filename(title)

    schema = document_tool.input_schema or {}
    properties = schema.get("properties", {})
    required_fields = schema.get("required", [])

    # Provide values only for fields actually supported
    # by the server's MCP tool schema.
    possible_values = {
        "title": title,
        "content": content,
        "filename": filename,
    }

    arguments = {
        key: value
        for key, value in possible_values.items()
        if key in properties
    }

    missing_fields = [
        field
        for field in required_fields
        if field not in arguments
    ]

    if missing_fields:
        raise RuntimeError(
            "The create_word_file schema requires fields that "
            "this client does not currently supply: "
            + ", ".join(missing_fields)
            + ". Check the tool definition in server.py."
        )

    print(f"\nDocument title: {title}")
    print(f"Filename: {filename}")
    print(f"Calling MCP tool: {document_tool.name}")

    # The Word file is created here, not by the text-generation
    # request. Use the actual name registered by the MCP server.
    result = await mcp_client.call_tool(
        document_tool.name,
        arguments,
    )

    output = extract_tool_output(result)

    if output.startswith("TOOL ERROR:"):
        raise RuntimeError(output)

    return output


# ============================================================
# 12. MULTI-AGENT WORKFLOW
# ============================================================

async def run_multi_agent_workflow(
    mcp_client,
    mcp_tools,
    groq_tools,
    user_request,
    skills,
):
    """
    Route the request to the required agents.

    Gmail request:
        Retrieval -> Analysis

    Gmail request + document request:
        Retrieval -> Analysis -> Document -> MCP file tool

    General document request:
        Document -> MCP file tool
    """

    selected_skill = choose_skill(
        user_request,
        skills,
    )

    needs_document = selected_skill is not None
    needs_email_data = request_needs_email_data(
        user_request
    )

    print("\nStarting assistant workflow...")

    # --------------------------------------------------------
    # General document request, such as:
    # "Create a document about mathematics"
    # --------------------------------------------------------

    if needs_document and not needs_email_data:
        print(
            "\nThis is a general document request. "
            "Gmail retrieval is not required."
        )

        document_result = await document_agent(
            mcp_client=mcp_client,
            mcp_tools=mcp_tools,
            user_request=user_request,
            source_information=(
                "No Gmail data was requested. "
                "Create the document from the user's topic "
                "and requirements."
            ),
            selected_skill=selected_skill,
        )

        return (
            "Document creation completed.\n\n"
            + document_result
        )

    # --------------------------------------------------------
    # Gmail request: retrieve emails first.
    # --------------------------------------------------------

    print("\n[1] Email retrieval agent")

    retrieved_emails = await email_retrieval_agent(
        mcp_client,
        groq_tools,
        user_request,
    )

    if not retrieved_emails.strip():
        retrieved_emails = (
            "The retrieval agent returned no email results."
        )

    print("\nEmail retrieval finished.")

    # --------------------------------------------------------
    # Analyze retrieved emails.
    # --------------------------------------------------------

    print("\n[2] Email analysis agent")

    analysis = email_analysis_agent(
        user_request,
        retrieved_emails,
    )

    print("\nEmail analysis finished.")

    # --------------------------------------------------------
    # Create a document only if requested.
    # --------------------------------------------------------

    if needs_document:
        print("\n[3] Document creation agent")

        document_result = await document_agent(
            mcp_client=mcp_client,
            mcp_tools=mcp_tools,
            user_request=user_request,
            source_information=analysis,
            selected_skill=selected_skill,
        )

        return (
            "Workflow completed.\n\n"
            "Email analysis:\n"
            f"{analysis}\n\n"
            "Word document result:\n"
            f"{document_result}"
        )

    return analysis


# ============================================================
# 13. MAIN PROGRAM
# ============================================================

async def main():
    skills = discover_skills()

    server_params = StdioServerParameters(
        command="python",
        args=[str(BASE_DIR / "server.py")],
    )

    print("\nConnecting to Gmail MCP server...")

    async with Client(server_params) as mcp_client:
        tool_response = await mcp_client.list_tools()
        mcp_tools = tool_response.tools

        groq_tools = convert_mcp_tools_to_groq(
            mcp_tools
        )

        print("\nConnected to MCP server.")

        print("\nAvailable tools:")

        for tool in mcp_tools:
            print(f"- {tool.name}")

        print("\nGmail Agent is ready!")
        print("Enter 'exit', 'quit', or 'done' to stop.\n")

        while True:
            try:
                user_request = input("You: ").strip()

                if user_request.lower() in {
                    "exit",
                    "quit",
                    "done",
                }:
                    print("Gmail Agent stopped.")
                    break

                if not user_request:
                    continue

                result = await run_multi_agent_workflow(
                    mcp_client=mcp_client,
                    mcp_tools=mcp_tools,
                    groq_tools=groq_tools,
                    user_request=user_request,
                    skills=skills,
                )

                print("\nAssistant:")
                print(result)
                print()

            except KeyboardInterrupt:
                print("\nGmail Agent stopped.")
                break

            except Exception as exc:
                print(
                    f"\nWorkflow error: "
                    f"{type(exc).__name__}: {exc}"
                )
                traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
