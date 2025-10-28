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
    model="llama3.2:3b",
    timeout=30
)

tools = []  # will be populated at runtime

def get_system_prompt() -> str:
    return (
        f"Today is {datetime.now():%Y-%m-%d}.\n"
        "You can call any of the following MCP tools to fetch NBA data:\n"
        "- get_league_leaders_info(season, stat_category, per_mode)\n"
        "- get_player_career_information(player_name, season)\n"
        "- get_live_scores(target_date)\n"
        "- play_by_play_info_for_current_games()\n"
        "When you want data, emit a tool call. Otherwise, answer directly."
    )

def create_chatbot_node(tools):
    async def chatbot(state: MessagesState):
        msgs = state["messages"]
        if isinstance(msgs, str):
            msgs = [HumanMessage(content=msgs)]
        full = [AIMessage(content=get_system_prompt())] + msgs
        response = await llm.ainvoke(full)
        return {"messages": msgs + [response]}
    return chatbot

async def async_tool_executor(state):
    messages = state["messages"]
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    if not tool_calls:
        return {"messages": messages}

    new_msgs = messages.copy()
    for tc in tool_calls:
        name = tc.name
        args = tc.args or {}
        tool = next((t for t in tools if t.name == name), None)
        if not tool:
            new_msgs.append(AIMessage(
                content=f"Unknown tool {name}, choose from {[t.name for t in tools]}"
            ))
            continue
        try:
            # support async or sync tool.coroutine
            if tc.id and hasattr(tool, "coroutine") and asyncio.iscoroutinefunction(tool.coroutine):
                result = await tool.coroutine(**args)
            else:
                # sync fallback
                result = tool.func(**args) if hasattr(tool, "func") else tool(**args)
            new_msgs.append(ToolMessage(
                content=str(result), tool_call_id=tc.id, name=name
            ))
        except Exception as e:
            new_msgs.append(AIMessage(content=f"Error running {name}: {e}"))
    return {"messages": new_msgs}

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

            # FIX: get_tools takes no args
            tools = client.get_tools()
            llm_with_tools = llm.bind_tools(tools)  # <-- bind tools here
            print("Loaded tools:", [t.name for t in tools])

            builder = StateGraph(MessagesState)
            builder.add_node("chatbot", create_chatbot_node(tools))
            builder.add_node("tools", async_tool_executor)

            def router(state):
                last = state["messages"][-1]
                return "tools" if getattr(last, "tool_calls", []) else END

            builder.add_edge(START, "chatbot")
            builder.add_conditional_edges("chatbot", router, {"tools": "tools", END: END})
            builder.add_edge("tools", "chatbot")
            graph = builder.compile()

            print("Enter a question (e.g. 'who leads the nba in assists this season?')")
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
