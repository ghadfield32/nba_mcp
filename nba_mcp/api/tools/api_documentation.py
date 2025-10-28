# tools.api_documentation.py
import inspect
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

# Import NBA API modules
from nba_api.stats import endpoints
from nba_api.stats.static import players, teams

from nba_mcp.api.tools.nba_api_utils import (
    get_player_id,
    get_team_id,
    normalize_per_mode,
    normalize_season,
    normalize_stat_category,
)

logger = logging.getLogger(__name__)


def get_endpoint_data_structure(endpoint_class):
    """Get the detailed data structure for an endpoint including metrics and column info.
    This is intended to run once so we can cache the result.
    """
    try:
        # Get the required parameters for the endpoint (if any)
        required_params = getattr(endpoint_class, "_required_parameters", [])

        # Initialize parameters dictionary with default sample values
        params = {}
        for param in required_params:
            param_lower = param.lower()
            if "player_id" in param_lower:
                # Use Nikola Jokić as default example
                params[param] = get_player_id("Nikola Jokić")
            elif "team_id" in param_lower:
                # Use Denver Nuggets as default example
                params[param] = get_team_id("Denver Nuggets")
            elif "game_id" in param_lower:
                # Use a sample game_id (for example, from a recent playoff game)
                params[param] = "0042200401"
            elif "league_id" in param_lower:
                params[param] = "00"  # NBA league ID
            elif "season" in param_lower:
                params[param] = "2022-23"  # Use most recent completed season
            else:
                params[param] = "0"  # Use a generic default value

        # Create an instance of the endpoint
        instance = endpoint_class(**params)

        data_sets = {}
        # Get all available data frames from the endpoint
        all_frames = instance.get_data_frames()
        raw_data = instance.get_dict()

        for idx, df in enumerate(all_frames):
            if df is not None and not df.empty:
                result_set = raw_data["resultSets"][idx]
                data_sets[f"dataset_{idx}"] = {
                    "name": result_set["name"],
                    "headers": result_set["headers"],
                    "columns": df.columns.tolist(),
                    "dtypes": df.dtypes.apply(lambda x: str(x)).to_dict(),
                    "sample_data": df.head(2).to_dict("records"),
                    "row_count": len(df),
                }

        return {"parameters_used": params, "datasets": data_sets}
    except Exception as e:
        return {"error": str(e)}


def analyze_api_structure() -> dict:
    """
    Analyze the NBA API structure and generate a quick guide for each endpoint.
    The quick guide includes the endpoint URL, parameters, and datasets.
    """
    logger.info("Analyzing NBA API structure…")

    # Get all endpoint classes from the endpoints module
    endpoint_classes = inspect.getmembers(endpoints, inspect.isclass)
    logger.info("Found %d potential endpoint classes", len(endpoint_classes))

    api_docs = {
        "endpoints": {},
        "static_data": {"teams": teams.get_teams(), "players": players.get_players()},
    }

    for endpoint_name, endpoint_class in endpoint_classes:
        try:
            if not hasattr(endpoint_class, "endpoint"):
                continue

            detailed_data = get_endpoint_data_structure(endpoint_class)

            dataset_names = [
                ds["name"] for ds in detailed_data.get("datasets", {}).values()
            ]
            description = (
                f"This endpoint returns data related to {', '.join(dataset_names)}."
                if dataset_names
                else "No dataset information available."
            )

            api_docs["endpoints"][endpoint_name] = {
                "endpoint_url": endpoint_class.endpoint,
                "parameters": getattr(endpoint_class, "_required_parameters", []),
                "optional_parameters": getattr(
                    endpoint_class, "_optional_parameters", []
                ),
                "default_parameters": getattr(
                    endpoint_class, "_default_parameters", {}
                ),
                "quick_description": description,
                "data_structure": detailed_data,
            }

        except Exception as e:
            logger.error(
                "Error processing endpoint %s: %s", endpoint_name, e, exc_info=True
            )

    logger.info("Successfully documented %d endpoints", len(api_docs["endpoints"]))
    return api_docs


def save_documentation(api_docs: dict, output_dir: str = "api_documentation"):
    """Save the API documentation to JSON and Markdown files."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 1) Write JSON files as before
    (output_path / "endpoints.json").write_text(
        json.dumps(api_docs["endpoints"], indent=2), encoding="utf-8"
    )
    (output_path / "static_data.json").write_text(
        json.dumps(api_docs["static_data"], indent=2), encoding="utf-8"
    )

    # 2) Build the markdown_content
    markdown_content = []
    # Header
    markdown_content.append(f"# NBA API Documentation Quick Guide\n")
    markdown_content.append(
        f"**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    markdown_content.append("## Available Endpoints\n")

    # Each endpoint
    for name, info in api_docs["endpoints"].items():
        markdown_content.append(f"### {name}\n")
        markdown_content.append(f"- **Endpoint URL:** `{info['endpoint_url']}`")
        markdown_content.append(
            f"- **Quick Description:** {info['quick_description']}\n"
        )

        # Required parameters
        if info["parameters"]:
            markdown_content.append("#### Required Parameters\n```json")
            markdown_content.append(json.dumps(info["parameters"], indent=2))
            markdown_content.append("```\n")

        # Optional parameters
        if info["optional_parameters"]:
            markdown_content.append("#### Optional Parameters\n```json")
            markdown_content.append(json.dumps(info["optional_parameters"], indent=2))
            markdown_content.append("```\n")

        # Default parameters
        if info["default_parameters"]:
            markdown_content.append("#### Default Parameters\n```json")
            markdown_content.append(json.dumps(info["default_parameters"], indent=2))
            markdown_content.append("```\n")

        # Example parameters used
        params_used = info["data_structure"].get("parameters_used", {})
        if params_used:
            markdown_content.append("#### Example Parameters Used\n```json")
            markdown_content.append(json.dumps(params_used, indent=2))
            markdown_content.append("```\n")

        # Datasets info
        datasets = info["data_structure"].get("datasets", {})
        if datasets:
            markdown_content.append("#### Available Datasets\n")
            for ds in datasets.values():
                markdown_content.append(f"- **{ds['name']}** (Rows: {ds['row_count']})")
                markdown_content.append("```json")
                markdown_content.append(
                    json.dumps(
                        {"headers": ds["headers"], "sample_data": ds["sample_data"]},
                        indent=2,
                    )
                )
                markdown_content.append("```\n")

    # Join all parts into one string
    markdown_str = "\n".join(markdown_content)

    # 3) Write the markdown file
    markdown_file = output_path / "api_documentation.md"
    with open(markdown_file, "w", encoding="utf-8") as f:
        f.write(markdown_str)

    logger.info("Documentation saved in directory: %s", output_path)


if __name__ == "__main__":
    # Generate the documentation quickly
    api_docs = analyze_api_structure()

    # Display a summary for the console
    print("\nDocumentation Summary:")
    print(f"Total endpoints documented: {len(api_docs['endpoints'])}")
    print(f"Total teams in static data: {len(api_docs['static_data']['teams'])}")
    print(f"Total players in static data: {len(api_docs['static_data']['players'])}")
    print(api_docs["endpoints"])

    # Save to files for quick later retrieval
    save_documentation(api_docs)

    # Display first endpoint details
    # if api_docs['endpoints']:
    #     first_endpoint = next(iter(api_docs['endpoints']))
    #     print(f"\nSample endpoint ({first_endpoint}):")
    #     print(json.dumps(api_docs['endpoints'][first_endpoint], indent=2))
