"""
JSON Schema publisher for NBA MCP tools.
This module exports all tool parameter schemas as JSON Schema files,
making them easily consumable by:
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from nba_mcp.schemas.tool_params import (
    AnswerNBAQuestionParams,
    ComparePlayersEraAdjustedParams,
    ComparePlayersParams,
    GetDateRangeGameLogParams,
    GetGameContextParams,
    GetLiveScoresParams,
    GetMetricsInfoParams,
    GetPlayerAdvancedStatsParams,
    GetPlayerCareerInformationParams,
    GetShotChartParams,
    GetTeamAdvancedStatsParams,
    GetTeamStandingsParams,
    LeagueLeadersParams,
    PlayByPlayParams,
    ResolveNBAEntityParams,
)

# Tool Registry

# Map tool names to their parameter models and metadata
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "resolve_nba_entity": {
        "model": ResolveNBAEntityParams,
        "description": "Resolve ambiguous player/team names to specific entities with fuzzy matching",
        "category": "Entity Resolution",
        "returns": "JSON with entity details, confidence score, and suggestions",
    },
    "get_player_career_information": {
        "model": GetPlayerCareerInformationParams,
        "description": "Get comprehensive career statistics for an NBA player",
        "category": "Player Data",
        "returns": "Formatted career stats (games, points, rebounds, assists, percentages)",
    },
    "get_league_leaders_info": {
        "model": LeagueLeadersParams,
        "description": "Get top-10 NBA league leaders for a statistical category",
        "category": "League Data",
        "returns": "Ranked list of top players for the specified stat",
    },
    "get_live_scores": {
        "model": GetLiveScoresParams,
        "description": "Get live or historical NBA game scores for a date",
        "category": "Live Data",
        "returns": "Game summaries with scores, teams, and status",
    },
    "get_date_range_game_log_or_team_game_log": {
        "model": GetDateRangeGameLogParams,
        "description": "Get game-by-game logs for a team or league within a date range",
        "category": "Game Data",
        "returns": "Detailed game logs with stats, outcomes, and matchups",
    },
    "play_by_play": {
        "model": PlayByPlayParams,
        "description": "Get detailed play-by-play data for NBA games",
        "category": "Game Data",
        "returns": "Chronological game events with timestamps and descriptions",
    },
    "get_team_standings": {
        "model": GetTeamStandingsParams,
        "description": "Get NBA team standings with rankings and records",
        "category": "Team Data",
        "returns": "Comprehensive standings (W-L, GB, rankings, streaks)",
    },
    "get_team_advanced_stats": {
        "model": GetTeamAdvancedStatsParams,
        "description": "Get team advanced statistics (Offensive/Defensive Rating, Pace, Four Factors)",
        "category": "Team Data",
        "returns": "Advanced team metrics and efficiency ratings",
    },
    "get_player_advanced_stats": {
        "model": GetPlayerAdvancedStatsParams,
        "description": "Get player advanced statistics (Usage%, TS%, eFG%, PER, ratings)",
        "category": "Player Data",
        "returns": "Comprehensive player efficiency metrics",
    },
    "compare_players": {
        "model": ComparePlayersParams,
        "description": "Compare two players side-by-side with normalized stats",
        "category": "Comparison",
        "returns": "Fair comparison with shared metrics and optional era adjustments",
    },
    "compare_players_era_adjusted": {
        "model": ComparePlayersEraAdjustedParams,
        "description": "Compare players across different eras with pace and scoring adjustments",
        "category": "Comparison",
        "returns": "Cross-era comparison with adjusted stats accounting for pace/scoring environment",
    },
    "get_shot_chart": {
        "model": GetShotChartParams,
        "description": "Get shot chart data with coordinates and hexbin aggregation for visualization",
        "category": "Shot Data",
        "returns": "Shooting data with raw coordinates, hexbin aggregation, and zone summaries",
    },
    "get_game_context": {
        "model": GetGameContextParams,
        "description": "Get comprehensive game context with standings, stats, form, and narrative",
        "category": "Game Context",
        "returns": "Matchup analysis with standings, advanced stats, recent form, head-to-head, and narrative summary",
    },
    "answer_nba_question": {
        "model": AnswerNBAQuestionParams,
        "description": "Answer natural language questions about NBA data (NLQ pipeline)",
        "category": "Natural Language",
        "returns": "Formatted markdown answer with tables/narratives",
    },
    "get_metrics_info": {
        "model": GetMetricsInfoParams,
        "description": "Get server metrics and observability information",
        "category": "Observability",
        "returns": "Server health, cache stats, rate limits, and metrics endpoint info",
    },
}

# Schema Export Functions

def get_tool_schema(tool_name: str) -> Dict[str, Any]:
    """
    Get the JSON Schema for a specific tool.

    Args:
        tool_name: Name of the tool (e.g., "resolve_nba_entity")

    Returns:
        JSON Schema dictionary for the tool's parameters

    Raises:
        ValueError: If tool_name not found in registry

    if tool_name not in TOOL_REGISTRY:
        raise ValueError(
            f"Tool '{tool_name}' not found. Available tools: {list(TOOL_REGISTRY.keys())}"
        )

    tool_info = TOOL_REGISTRY[tool_name]
    model = tool_info["model"]

    # Generate JSON Schema from Pydantic model
    schema = model.model_json_schema()

    # Add custom metadata
    schema["title"] = tool_name
    schema["description"] = tool_info["description"]
    schema["x-category"] = tool_info["category"]
    schema["x-returns"] = tool_info["returns"]

    return schema

def export_all_schemas(output_dir: str = "schemas") -> Dict[str, Path]:
    """
    Export all tool schemas to individual JSON files.

    Creates one JSON Schema file per tool in the output directory.
    Files are named: {tool_name}.json

    Args:
        output_dir: Directory to write schema files (created if doesn't exist)

    Returns:
        Dictionary mapping tool names to their file paths

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    exported = {}

    for tool_name in TOOL_REGISTRY.keys():
        schema = get_tool_schema(tool_name)

        # Write to JSON file with sorted keys (deterministic)
        file_path = output_path / f"{tool_name}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2, sort_keys=True, ensure_ascii=False)

        exported[tool_name] = file_path

    return exported

def list_available_tools() -> List[Dict[str, Any]]:
    """
    List all available tools with their metadata.

    Returns:
        List of tool information dictionaries

    return [
        {
            "name": tool_name,
            "description": info["description"],
            "category": info["category"],
            "returns": info["returns"],
        }
        for tool_name, info in TOOL_REGISTRY.items()
    ]

# OpenAPI Specification Export

def export_openapi_spec(output_file: str = "schemas/openapi.yaml") -> Path:
    """
    Generate and export an OpenAPI 3.1.0 specification for all tools.

    Creates a comprehensive OpenAPI spec that can be used with:
    - Swagger UI / Redoc for documentation
    - API client generators (openapi-generator, etc.)
    - LLM function calling frameworks

    Args:
        output_file: Path to write OpenAPI YAML file

    Returns:
        Path to the generated OpenAPI file

    # OpenAPI 3.1.0 base structure
    openapi_spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "NBA MCP API",
            "version": "1.0.0",
            "description": (
                "NBA Model Context Protocol (MCP) Server providing comprehensive "
                "NBA data through 12 specialized tools. Supports natural language queries, "
                "entity resolution, player/team statistics, live scores, and advanced analytics."
            ),
            "contact": {
                "name": "NBA MCP",
                "url": "https://github.com/your-org/nba_mcp",
            },
            "license": {"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
        },
        "servers": [
            {"url": "http://localhost:8000", "description": "Local development server"}
        ],
        "paths": {},
        "components": {"schemas": {}},
    }

    # Add each tool as an endpoint
    for tool_name, tool_info in TOOL_REGISTRY.items():
        schema = get_tool_schema(tool_name)

        # Add schema to components
        openapi_spec["components"]["schemas"][tool_name] = schema

        # Create endpoint (tools are POST operations in MCP)
        path = f"/tools/{tool_name}"
        openapi_spec["paths"][path] = {
            "post": {
                "summary": tool_info["description"],
                "description": schema.get("description", ""),
                "operationId": tool_name,
                "tags": [tool_info["category"]],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{tool_name}"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {
                                            "type": "string",
                                            "enum": ["success"],
                                        },
                                        "data": {"type": "object"},
                                        "metadata": {"type": "object"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Invalid parameters",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "enum": ["error"]},
                                        "errors": {"type": "array"},
                                    },
                                }
                            }
                        },
                    },
                },
            }
        }

    # Write to YAML file
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_spec, f, default_flow_style=False, sort_keys=False)

    return output_path

# Utility Functions

def get_schema_summary() -> Dict[str, Any]:
    """
    Get a summary of all available schemas.

    Returns:
        Dictionary with schema statistics and metadata

    categories = {}
    for tool_name, info in TOOL_REGISTRY.items():
        category = info["category"]
        if category not in categories:
            categories[category] = []
        categories[category].append(tool_name)

    return {
        "total_tools": len(TOOL_REGISTRY),
        "categories": categories,
        "tool_names": list(TOOL_REGISTRY.keys()),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

def validate_schema(tool_name: str, params: Dict[str, Any]) -> bool:
    """
    Validate parameters against a tool's schema.

    Args:
        tool_name: Name of the tool
        params: Parameters to validate

    Returns:
        True if valid, raises ValidationError if invalid

    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Tool '{tool_name}' not found")

    model = TOOL_REGISTRY[tool_name]["model"]
    model(**params)  # Will raise ValidationError if invalid
    return True

# CLI for Schema Export

def main():
    """
    CLI entry point for exporting schemas.

    Usage:
        python -m nba_mcp.schemas.publisher

    This will:
    1. Export all individual JSON Schema files to schemas/
    2. Generate OpenAPI specification at schemas/openapi.yaml
    3. Print summary statistics
    """
    import sys

    print("NBA MCP Schema Publisher")
    print("=" * 70)

    # Export individual schemas
    print("\n1. Exporting individual JSON Schemas...")
    exported = export_all_schemas(output_dir="schemas")
    print(f"   ✓ Exported {len(exported)} schemas to schemas/")
    for tool_name, path in exported.items():
        print(f"     - {path}")

    # Export OpenAPI spec
    print("\n2. Generating OpenAPI specification...")
    openapi_path = export_openapi_spec(output_file="schemas/openapi.yaml")
    print(f"   ✓ OpenAPI spec written to: {openapi_path}")

    # Print summary
    print("\n3. Schema Summary:")
    summary = get_schema_summary()
    print(f"   Total Tools: {summary['total_tools']}")
    print(f"   Categories:")
    for category, tools in summary["categories"].items():
        print(f"     - {category}: {len(tools)} tools")

    print("\n" + "=" * 70)
    print("Schema export complete!")
    print(f"Generated at: {summary['generated_at']}")
    print("\nNext steps:")
    print("  - Review schemas in schemas/ directory")
    print("  - Import OpenAPI spec into Swagger UI or Redoc")
    print("  - Use schemas for LLM function calling")

    return 0

if __name__ == "__main__":
    import sys

    sys.exit(main())
