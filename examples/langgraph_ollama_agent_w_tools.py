import os, sys, asyncio
from datetime import datetime
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END, MessagesState

load_dotenv()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MCP_URL     = os.getenv("NBA_MCP_URL",  "http://localhost:8000/sse")

# Base LLM (unbound)
llm = ChatOllama(host=OLLAMA_HOST, model="llama3.2:3b", timeout=30)

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
        print("   • Is your NBA MCP server running on SSE port 8000?")
        print("     Try: `python -m nba_mcp --transport sse`")
        return

if __name__ == "__main__":
    print("Starting NBA MCP server...")
    # use os to run python -m nba_mcp --transport sse
    #os.system("python -m nba_mcp --transport sse")
    print("Langgraph agent starting…")
    asyncio.run(main())
