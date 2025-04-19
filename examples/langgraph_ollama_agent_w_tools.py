# examples/langgraph_ollama_agent_w_tools.py

import os, sys, asyncio, subprocess, time, socket
from datetime import datetime
from dotenv import load_dotenv
import argparse

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END, MessagesState

# ── 1) Arg parsing: pick a mode, default "local" ────────────────────────
parser = argparse.ArgumentParser(
    description="Run NBA MCP in local/claude mode + Langgraph agent"
)
parser.add_argument(
    "--mode",
    choices=["claude", "local"],
    default=os.getenv("NBA_MCP_MODE", "local"),
    help="Which NBA‑MCP mode to run (and which port to bind)"
)
args = parser.parse_args()
MODE = args.mode

# ── 2) Compute port just like nba_server does ───────────────────────────
#    (reads NBA_MCP_PORT from your .env or defaults)
if MODE == "claude":
    MCP_PORT = int(os.getenv("NBA_MCP_PORT", "8000"))
else:
    MCP_PORT = int(os.getenv("NBA_MCP_PORT", "8001"))
MCP_URL = f"http://localhost:{MCP_PORT}/sse"

load_dotenv()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
llm = ChatOllama(host=OLLAMA_HOST, model="llama3.2:3b", timeout=30)

def wait_for_port(host: str, port: int, timeout: float = 5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                time.sleep(0.1)
    return False



def get_system_prompt() -> str:
    return (
        f"Today is {datetime.now():%Y-%m-%d}.\n"
        "Tools you can call:\n"
        "- get_league_leaders_info(season, stat_category, per_mode)\n"
        "    • per_mode must be one of: 'Totals', 'PerGame', 'Per48'\n"
        "    • e.g.: get_league_leaders_info('2024-25','AST','PerGame')\n"
        "- get_player_career_information(player_name, season)\n"
        "- get_live_scores(target_date)\n"
        "- play_by_play_info_for_current_games()\n"
        "When you want data, emit a tool call. Otherwise, answer directly."
    )


def create_chatbot_node(llm_instance, tools):
    """
    llm_instance: ChatOllama bound to your MCP tools
    tools: list of tool objects
    """
    async def chatbot(state: MessagesState):
        msgs = state["messages"]
        full = [AIMessage(content=get_system_prompt())] + msgs
        response = await llm_instance.ainvoke(full)
        # DEBUG: check that we got structured tool_calls
        print("DEBUG tool_calls:", getattr(response, "tool_calls", None), file=sys.stderr)
        return {"messages": msgs + [response]}
    return chatbot

async def async_tool_executor(state):
    messages = state["messages"]
    last     = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    if not tool_calls:
        return {"messages": messages}

    new_msgs = messages.copy()
    for tc in tool_calls:
        # 1) Normalize call into (name, args, call_id)
        if isinstance(tc, dict):
            name    = tc.get("name")
            args    = tc.get("args", {}) or {}
            call_id = tc.get("id")
        else:
            name    = tc.name
            args    = tc.args or {}
            call_id = tc.id

        # 2) Lookup the tool by name
        tool = next((t for t in tools if t.name == name), None)
        if not tool:
            new_msgs.append(
                AIMessage(content=f"Unknown tool {name}, available: {[t.name for t in tools]}")
            )
            continue

        # 3) Execute the tool, sync or async
        try:
            if call_id and hasattr(tool, "coroutine") and asyncio.iscoroutinefunction(tool.coroutine):
                result = await tool.coroutine(**args)
            else:
                result = tool.func(**args) if hasattr(tool, "func") else tool(**args)

            new_msgs.append(
                ToolMessage(content=str(result), tool_call_id=call_id, name=name)
            )
        except Exception as e:
            new_msgs.append(
                AIMessage(content=f"Error running {name}: {e}")
            )

    return {"messages": new_msgs}


async def main():
    try:
        async with MultiServerMCPClient({
            "nba": {"url": MCP_URL, "transport": "sse", "timeout": 30}
        }) as client:
            global tools
            tools = client.get_tools()

            # 1) bind LLM to the tools
            llm_with_tools = llm.bind_tools(tools)

            print("Loaded tools:", [t.name for t in tools])

            # 2) wire up the graph, passing in the bound LLM
            builder = StateGraph(MessagesState)
            builder.add_node("chatbot", create_chatbot_node(llm_with_tools, tools))
            builder.add_node("tools",  async_tool_executor)

            def router(state):
                last = state["messages"][-1]
                return "tools" if getattr(last, "tool_calls", []) else END

            builder.add_edge(START, "chatbot")
            builder.add_conditional_edges("chatbot", router, {"tools": "tools", END: END})
            builder.add_edge("tools", "chatbot")
            graph = builder.compile()

            print("Enter a question:")
            state = {"messages": [HumanMessage(content=input("> "))]}
            result = await graph.ainvoke(state)
            for msg in result["messages"]:
                print(f"{msg.__class__.__name__}: {msg.content}")

    except Exception as e:
        print(f"❌ Could not run agent: {e}")
        print("   • Is your NBA MCP server running on SSE port 9888?")
        print("     Try: `python -m nba_mcp --transport sse`")
        return

if __name__ == "__main__":
    # 3) Launch the MCP with the same mode → binds to MCP_PORT automatically
    print(f"Starting NBA MCP server in {MODE!r} mode (port {MCP_PORT})…")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "nba_mcp",
         "--mode", MODE,
         "--transport", "sse"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # 4) Wait for it to bind
    if not wait_for_port("127.0.0.1", MCP_PORT, timeout=5):
        err = server_proc.stderr.read()
        print("❌ NBA MCP server failed to start:", file=sys.stderr)
        print(err, file=sys.stderr)
        server_proc.terminate()
        sys.exit(1)

    try:
        print("Langgraph agent starting…")
        asyncio.run(main())
    finally:
        server_proc.terminate()
        server_proc.wait()