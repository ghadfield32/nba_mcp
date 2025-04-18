# examples/langgraph_ollama_agent.py

import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END, MessagesState

load_dotenv()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MCP_URL     = os.getenv("NBA_MCP_URL", "http://localhost:8000/sse")

llm = ChatOllama(
    host=OLLAMA_HOST,
    model="gemma3:latest",
    timeout=30
)

tools = []  # will be populated at runtime

def get_system_prompt(tools: list, openapi_spec: str) -> str:
    # build a bullet list of tool names + signatures
    tool_list = "\n".join(f"- {t.name}{t.signature}" for t in tools)

    return f"""
Today is {datetime.now():%Y-%m-%d}

🛑 YOU MUST use an MCP tool for *any* NBA data request.
Do NOT invent or guess answers; always emit a single `tool_call`.

Available MCP tools (name + parameters):
{tool_list}

Full OpenAPI spec for reference:

{openapi_spec}


When you need data, respond with exactly one tool invocation.
After the tool returns, summarize the result in plain language.
"""



def create_chatbot_node(tools: list, openapi_spec: str):
    async def chatbot(state: MessagesState):
        msgs = state["messages"]
        if isinstance(msgs, str):
            msgs = [HumanMessage(content=msgs)]

        # system prompt now includes your tool list + spec
        full = [AIMessage(content=get_system_prompt(tools, openapi_spec))] + msgs
        response = await llm.ainvoke(full)
        return {"messages": msgs + [response]}

    return chatbot

# ─── instrumented executor ───────────────────────────────────────────────
async def async_tool_executor(state):
    messages = state["messages"]
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    print("🛠 Detected tool_calls:", tool_calls)

    if not tool_calls:
        return {"messages": messages}

    new_msgs = messages.copy()
    for tc in tool_calls:
        print(f"▶️  Executing tool `{tc.name}` with args {tc.args}")
        tool = next((t for t in tools if t.name == tc.name), None)
        if not tool:
            err = f"Unknown tool {tc.name}; available: {[t.name for t in tools]}"
            print("❌", err)
            new_msgs.append(AIMessage(content=err))
            continue

        try:
            if asyncio.iscoroutinefunction(tool.coroutine):
                result = await tool.coroutine(**tc.args)
            else:
                result = tool.func(**tc.args)
            print(f"✅ Tool `{tc.name}` returned: {result!r}")
            new_msgs.append(ToolMessage(content=str(result),
                                       tool_call_id=tc.id,
                                       name=tc.name))
        except Exception as e:
            print(f"❌ Tool `{tc.name}` raised:", e)
            new_msgs.append(AIMessage(content=f"Error running tool {tc.name}: {e}"))

    return {"messages": new_msgs}


# ─── fetch the spec, then build your graph ────────────────────────────────
async def main():
    try:
        async with MultiServerMCPClient({
            "nba": {
                "url": MCP_URL,
                "transport": "sse",
                "timeout": 30
            }
        }) as client:
            global tools

            # 1) load tools
            tools = client.get_tools()
            print("Loaded tools:", [t.name for t in tools])

            # 2) fetch and inline your OpenAPI spec via HTTP
            import httpx
            base = MCP_URL.rsplit("/", 1)[0]
            async with httpx.AsyncClient() as ac:
                resp = await ac.get(f"{base}/api-docs/openapi.json")
                resp.raise_for_status()
                spec = resp.text
            print("✅ OpenAPI spec loaded via HTTP, passing to the prompt…")

            # 3) build the StateGraph with spec
            builder = StateGraph(MessagesState)
            builder.add_node("chatbot", create_chatbot_node(tools, spec))
            builder.add_node("tools", async_tool_executor)

            def router(state):
                last = state["messages"][-1]
                return "tools" if getattr(last, "tool_calls", []) else END

            builder.add_edge(START, "chatbot")
            builder.add_conditional_edges("chatbot", router, {"tools": "tools", END: END})
            builder.add_edge("tools", "chatbot")

            graph = builder.compile()

            print("Enter a question (e.g. 'Who led the league in AST this year?')")
            state = {"messages": [HumanMessage(content=input("> "))]}
            result = await graph.ainvoke(state)
            for msg in result["messages"]:
                print(f"{msg.__class__.__name__}: {msg.content}")

    except Exception as e:
        print(f"❌ Could not connect to MCP server at {MCP_URL}: {e}")
        print("   • Is your NBA MCP server running in SSE mode on port 8000?")
        print("     Try: `python -m nba_mcp --transport sse`")
        return





if __name__ == "__main__":
    print("Starting NBA MCP server...")
    # use os to run python -m nba_mcp --transport sse
    #os.system("python -m nba_mcp --transport sse")
    print("Langgraph agent started")
    asyncio.run(main())
