#tools.api_documentation.py
import sys
import os
from pathlib import Path
import inspect
import json
from datetime import datetime
import pandas as pd
from typing import Optional, Dict

# Import NBA API modules
from nba_api.stats import endpoints
from nba_api.stats.static import teams, players

# ---------------------------------------------------
# Load static lookups once and create reverse lookups
# ---------------------------------------------------
_TEAM_LOOKUP: Dict[int, str] = {
    t["id"]: t["full_name"] for t in teams.get_teams()
}
_PLAYER_LOOKUP: Dict[int, str] = {
    p["id"]: f"{p['first_name']} {p['last_name']}" for p in players.get_players()
}

# Create reverse lookups (name -> id)
_TEAM_NAME_TO_ID = {name: id for id, name in _TEAM_LOOKUP.items()}
_PLAYER_NAME_TO_ID = {name: id for id, name in _PLAYER_LOOKUP.items()}

def get_player_id(player_name: str) -> Optional[int]:
    """Convert player name to ID, with case-insensitive partial matching."""
    if not player_name:
        return None

    player_name_lower = player_name.lower()
    # Try exact match first
    for name, id in _PLAYER_NAME_TO_ID.items():
        if name.lower() == player_name_lower:
            return id

    # Try partial match
    for name, id in _PLAYER_NAME_TO_ID.items():
        if player_name_lower in name.lower():
            return id

    return None


def get_team_id(team_name: str) -> Optional[int]:
    """Convert team name to ID, with case-insensitive partial matching."""
    if not team_name:
        return None

    team_name_lower = team_name.lower()
    # Try exact match first
    for name, id in _TEAM_NAME_TO_ID.items():
        if name.lower() == team_name_lower:
            return id

    # Try partial match
    for name, id in _TEAM_NAME_TO_ID.items():
        if team_name_lower in name.lower():
            return id

    return None

def get_endpoint_data_structure(endpoint_class):
    """Get the detailed data structure for an endpoint including metrics and column info.
    This is intended to run once so we can cache the result.
    """
    try:
        # Get the required parameters for the endpoint (if any)
        required_params = getattr(endpoint_class, '_required_parameters', [])

        # Initialize parameters dictionary with default sample values
        params = {}
        for param in required_params:
            param_lower = param.lower()
            if 'player_id' in param_lower:
                # Use Nikola Jokić as default example
                params[param] = get_player_id("Nikola Jokić")
            elif 'team_id' in param_lower:
                # Use Denver Nuggets as default example
                params[param] = get_team_id("Denver Nuggets")
            elif 'game_id' in param_lower:
                # Use a sample game_id (for example, from a recent playoff game)
                params[param] = '0042200401'
            elif 'league_id' in param_lower:
                params[param] = '00'  # NBA league ID
            elif 'season' in param_lower:
                params[param] = '2022-23'  # Use most recent completed season
            else:
                params[param] = '0'  # Use a generic default value

        # Create an instance of the endpoint
        instance = endpoint_class(**params)

        data_sets = {}
        # Get all available data frames from the endpoint
        all_frames = instance.get_data_frames()
        raw_data = instance.get_dict()

        for idx, df in enumerate(all_frames):
            if df is not None and not df.empty:
                result_set = raw_data['resultSets'][idx]
                data_sets[f'dataset_{idx}'] = {
                    'name': result_set['name'],
                    'headers': result_set['headers'],
                    'columns': df.columns.tolist(),
                    'dtypes': df.dtypes.apply(lambda x: str(x)).to_dict(),
                    'sample_data': df.head(2).to_dict('records'),
                    'row_count': len(df)
                }

        return {
            'parameters_used': params,
            'datasets': data_sets
        }
    except Exception as e:
        return {'error': str(e)}

def analyze_api_structure():
    """Analyze the NBA API structure and generate a quick guide for each endpoint.
    The quick guide includes the endpoint URL, the parameters, and a short description
    of what the endpoint is good for (derived from its datasets).
    """
    print("Analyzing NBA API structure...")

    # Get all endpoint classes from the endpoints module
    endpoint_classes = inspect.getmembers(endpoints, inspect.isclass)

    # Initialize documentation structure
    api_docs = {
        'endpoints': {},
        'static_data': {
            'teams': teams.get_teams(),
            'players': players.get_players()
        }
    }

    print(f"Found {len(endpoint_classes)} potential endpoints")

    # Document each endpoint
    for endpoint_name, endpoint_class in endpoint_classes:
        try:
            # Only process those classes that declare an endpoint property
            if not hasattr(endpoint_class, 'endpoint'):
                continue

            # Generate the detailed data structure once
            detailed_data = get_endpoint_data_structure(endpoint_class)

            # Create a quick description based on the datasets available.
            dataset_names = []
            if 'datasets' in detailed_data:
                for ds in detailed_data['datasets'].values():
                    dataset_names.append(ds['name'])
            description = f"This endpoint returns data related to {', '.join(dataset_names)}." if dataset_names else "No dataset information available."

            api_docs['endpoints'][endpoint_name] = {
                'endpoint_url': endpoint_class.endpoint,
                'parameters': getattr(endpoint_class, '_required_parameters', []),
                'optional_parameters': getattr(endpoint_class, '_optional_parameters', []),
                'default_parameters': getattr(endpoint_class, '_default_parameters', {}),
                'quick_description': description,
                'data_structure': detailed_data
            }
        except Exception as e:
            print(f"Error processing endpoint {endpoint_name}: {str(e)}")

    print(f"Successfully documented {len(api_docs['endpoints'])} endpoints")
    return api_docs

def save_documentation(api_docs, output_dir='api_documentation'):
    """Save the API documentation to files (both JSON and markdown).
    This only happens once so that subsequent queries for documentation load quickly.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    endpoints_file = output_path / 'endpoints.json'
    with open(endpoints_file, 'w') as f:
        json.dump(api_docs['endpoints'], f, indent=2)

    static_file = output_path / 'static_data.json'
    with open(static_file, 'w') as f:
        json.dump(api_docs['static_data'], f, indent=2)

    # Create markdown documentation for quick reference
    markdown_content = f"""# NBA API Documentation Quick Guide
        Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

        This guide provides a quick reference to available NBA API endpoints and what they are used for.

        ## Available Endpoints

"""

    for endpoint_name, endpoint_info in api_docs['endpoints'].items():
        markdown_content += f"\n### {endpoint_name}\n"
        markdown_content += f"**Endpoint URL:** `{endpoint_info['endpoint_url']}`\n\n"
        markdown_content += f"**Quick Description:** {endpoint_info['quick_description']}\n\n"

        if endpoint_info['parameters']:
            markdown_content += "#### Required Parameters:\n```python\n"
            markdown_content += json.dumps(endpoint_info['parameters'], indent=2)
            markdown_content += "\n```\n"
        if endpoint_info['optional_parameters']:
            markdown_content += "\n#### Optional Parameters:\n```python\n"
            markdown_content += json.dumps(endpoint_info['optional_parameters'], indent=2)
            markdown_content += "\n```\n"
        markdown_content += "\n#### Example Parameters Used:\n```python\n"
        markdown_content += json.dumps(endpoint_info['data_structure'].get('parameters_used', {}), indent=2)
        markdown_content += "\n```\n"

        # Add details about available datasets from this endpoint
        if 'datasets' in endpoint_info['data_structure'] and endpoint_info['data_structure']['datasets']:
            markdown_content += "\n#### Available Datasets:\n"
            for ds in endpoint_info['data_structure']['datasets'].values():
                markdown_content += f"\n**{ds['name']}** (Rows: {ds['row_count']})\n"
                markdown_content += "Headers:\n```python\n"
                markdown_content += json.dumps(ds['headers'], indent=2)
                markdown_content += "\n```\n"
                markdown_content += "Columns and Data Types:\n```python\n"
                markdown_content += json.dumps(ds['dtypes'], indent=2)
                markdown_content += "\n```\n"
                markdown_content += "Sample Data:\n```python\n"
                markdown_content += json.dumps(ds['sample_data'], indent=2)
                markdown_content += "\n```\n"

    markdown_file = output_path / 'api_documentation.md'
    with open(markdown_file, 'w') as f:
        f.write(markdown_content)

    print(f"Documentation saved in directory: {output_path}")

if __name__ == "__main__":
    # Generate the documentation quickly
    api_docs = analyze_api_structure()

    # Display a summary for the console
    print("\nDocumentation Summary:")
    print(f"Total endpoints documented: {len(api_docs['endpoints'])}")
    print(f"Total teams in static data: {len(api_docs['static_data']['teams'])}")
    print(f"Total players in static data: {len(api_docs['static_data']['players'])}")
    print(api_docs['endpoints'])

    # Save to files for quick later retrieval
    save_documentation(api_docs)


    # Display first endpoint details
    # if api_docs['endpoints']:
    #     first_endpoint = next(iter(api_docs['endpoints']))
    #     print(f"\nSample endpoint ({first_endpoint}):")
    #     print(json.dumps(api_docs['endpoints'][first_endpoint], indent=2))






