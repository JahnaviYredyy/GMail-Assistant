import asyncio
import json
import os

from dotenv import load_dotenv
from groq import Groq
from mcp import Client, StdioServerParameters
load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set.")

# CREATE GROQ CLIENT

groq_client = Groq(
    api_key=GROQ_API_KEY
)

MODEL = "openai/gpt-oss-120b"


async def main():
    # Start MCP server automatically
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"]
    )
    
    # Connect to MCP server

    async with Client(server_params) as mcp_client:

        tool_result = await mcp_client.list_tools()

        print("\nAvailable MCP tools:")

        for tool in tool_result.tools:

            print(     
                "-",
                tool.name
            )

        # CONVERT MCP TOOLS TO GROQ TOOLS

        groq_tools = []

        for tool in tool_result.tools:

            groq_tools.append({

                "type": "function",

                "function": {

                    "name":
                        tool.name,

                    "description":
                        tool.description or "",

                    "parameters":
                        tool.input_schema
                }
            })

        # CONVERSATION MEMORY 
        messages = [ {
            "role": "system",  
            "content": """ 
            You are an intelligent Gmail assistant. 
            You can use Gmail tools to retrieve emails. 
            Your job is to: 
            1. Understand the user's request.
            2. Choose the correct Gmail tool. 
            3. Retrieve the required emails. 
            4. Analyze the email content. 
            5. Identify important information. 
            6. Identify actions and deadlines. 
            7. Give the user a clear and useful answer. 
            
            --------------------------------------------------
              EMAIL CLASSIFICATION 
            -------------------------------------------------- 
        You can classify emails into categories such as: 
        - Job opportunity 
        - Interview - Recruitment 
        - Assessment - Rejection 
        - Offer 
        - Work 
        - Personal 
        - Newsletter 
        - Promotion 
        - Other 
        
        -------------------------------------------------- 
        IMPORTANT EMAIL DETECTION 
        --------------------------------------------------
         
     Consider an email IMPORTANT when it contains things such as: 
     - An interview invitation 
     - A job opportunity 
     - An assessment that must be completed 
     - A deadline - A meeting - An urgent request 
     - A request that requires the user to take action 
     - Important account or security information 
     - A time-sensitive request 
     
     Consider an email LESS IMPORTANT when it is mainly: 
     - Advertisement 
     - Promotion 
     - Newsletter 
     - Marketing 
     - General notification 
     - Information that requires no action 
     
     Do not decide importance from the subject alone. 
     Consider: 
     - Sender 
     - Subject 
     - Email body 
     - Dates 
     - Deadlines 
     - Required actions 
     - Urgency 
     
     -------------------------------------------------- 
     ACTION DETECTION 
     -------------------------------------------------- 
     
     When analyzing an email, look for things the user needs to do. 
     
     Examples: 
     - Complete an assessment 
     - Attend an interview - Reply to an email 
     - Submit a document 
     - Confirm availability 
     - Register for an event 
     - Complete a form 
     - Pay a bill 
     - Respond before a deadline If an action has a deadline, identify the deadline. 
     
     -------------------------------------------------- 
     TOOL SELECTION 
     -------------------------------------------------- 
     1. If the user asks about unread emails, use get_unread_emails. 
     2. If the user asks about today's emails, use get_todays_emails. 
     3. If the user asks about emails from a particular company or person, 
         use search_emails.
     4. If the user asks about a specific email, use get_email. 
     5. If the user asks about a category such as job emails, 
         interview emails, or recruitment emails, 
          retrieve the relevant emails and analyze them. 
     6. If the user asks whether they have anything important to do, 
         retrieve relevant emails and analyze them for importance,  
         actions, and deadlines. 
     7. You may call multiple tools if necessary. 
     
     -------------------------------------------------- 
     FOLLOW-UP QUESTIONS 
     -------------------------------------------------- 
     
     Remember the previous conversation and 
      use that context when answering follow-up questions. 
      
    For example: 
    User: Show me my unread emails. 
    User: Which ones are important? 
        You should use the previous email information when answering the second question. 
        
-------------------------------------------------- 
ANSWER FORMAT 
-------------------------------------------------- 
When identifying important emails, 
explain briefly: 
- Why the email is important 
- What action is required 
- Deadline, if one exists 
- Priority when appropriate 

Use: 
HIGH PRIORITY 
MEDIUM PRIORITY 
LOW PRIORITY 

Do not invent deadlines or actions that are not present in the email. 
If there are no important emails or actions, clearly tell the user that. 

--------------------------------------------------
ACTION DETECTION
--------------------------------------------------

When analyzing an email, determine whether the user
needs to take an action.

For each relevant email, identify:

- important: true or false
- action_required: true or false
- action: what the user needs to do
- deadline: when the action must be completed
- priority: HIGH, MEDIUM, or LOW

Examples of actions:

- Complete an assessment
- Attend an interview
- Reply to an email
- Submit a document
- Confirm availability
- Upload a file
- Register for an event
- Complete a form
- Pay a bill
- Respond before a deadline

Do not invent an action or deadline.

If the email does not require an action:

action_required: false
action: null
deadline: null

If no deadline is mentioned:

deadline: null

When presenting action information to the user,
use this format:

Action: <what the user needs to do>
Deadline: <deadline or "No deadline mentioned">
Priority: <HIGH / MEDIUM / LOW>
Reason: <brief explanation>

""" 
} ]

        print("\nGmail Agent is ready!")

        print(
            "Type 'exit', 'quit', or 'done' to stop."
        )


        while True:
            user_question = input(
                "\nYou: "
            )

            if user_question.lower() in [
                "exit",
                "quit",
                "done"
            ]:

                print("\nAgent: Goodbye!" )

                break

            # Add user message to conversation
            messages.append({

                "role":
                    "user",

                "content":
                    user_question
            })

            # AGENT LOOP

            while True:
                print("\nAgent is thinking...")

                # Ask Groq what to do
                response = (
                    groq_client
                    .chat
                    .completions
                    .create(

                        model=MODEL,

                        messages=messages,

                        tools=groq_tools,

                        tool_choice="auto"
                    )
                )
                assistant_message = (
                    response
                    .choices[0]
                    .message
                )

                messages.append(
                    assistant_message
                )

                # CHECK IF TOOL IS NEEDED

                if not assistant_message.tool_calls:

                    print("\nAgent:")

                    print(assistant_message.content)

                    break

                # EXECUTE TOOL CALLS

                for tool_call in (assistant_message.tool_calls):
                    tool_name = (tool_call.function.name)
                    arguments_text = (tool_call.function.arguments)


                    print(
                        f"\nAgent selected tool: "
                        f"{tool_name}"
                    )


                    print(
                        f"Arguments: "
                        f"{arguments_text}"
                    )
                    arguments = json.loads(arguments_text)
                    print("\nTool input:")
                    print(json.dumps(arguments,indent=4))

                    result = await mcp_client.call_tool(

                        tool_name,

                        arguments
                    )

                    # GET TOOL RESULT
                    tool_output = ""
                    for content in result.content:
                        
                        if hasattr(content,"text"):

                            tool_output += (content.text)


                    print("\nTool returned:")
                    print(tool_output[:1000])


                    # SEND TOOL RESULT BACK TO GROQ

                    messages.append({

                        "role":
                            "tool",

                        "tool_call_id":
                            tool_call.id,

                        "content":
                            tool_output
                    })


# RUN APPLICATION

if __name__ == "__main__":

    asyncio.run(
        main()
    )
