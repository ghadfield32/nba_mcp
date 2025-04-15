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
    """Get the data structure for an endpoint including metrics and column info"""
    try:
        # Get the required parameters for the endpoint
        required_params = getattr(endpoint_class, '_required_parameters', [])
        
        # Initialize parameters dictionary
        params = {}
        
        # Handle parameters based on their names
        for param in required_params:
            param_lower = param.lower()
            if 'player_id' in param_lower:
                # Use Nikola Jokić as default example
                params[param] = get_player_id("Nikola Jokić")
            elif 'team_id' in param_lower:
                # Use Denver Nuggets as default example
                params[param] = get_team_id("Denver Nuggets")
            elif 'game_id' in param_lower:
                # Use a recent playoff game as example
                params[param] = '0042200401'
            elif 'league_id' in param_lower:
                params[param] = '00'  # NBA league ID
            elif 'season' in param_lower:
                params[param] = '2022-23'  # Use most recent completed season
            else:
                # For other parameters, use a default value
                params[param] = '0'
        
        # Create instance with parameters
        instance = endpoint_class(**params)
        
        data_sets = {}
        
        # Get all available data frames
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
                    'sample_data': df.head(2).to_dict('records') if not df.empty else None,
                    'row_count': len(df)
                }
        
        return {
            'parameters_used': params,
            'datasets': data_sets
        }
    
    except Exception as e:
        return {'error': str(e)}

def analyze_api_structure():
    """Analyze and document the NBA API structure"""
    print("Analyzing NBA API structure...")
    
    # Get all endpoint classes from the endpoints module
    endpoint_classes = inspect.getmembers(endpoints, inspect.isclass)
    
    # Create documentation structure
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
            # Skip if not a proper endpoint class
            if not hasattr(endpoint_class, 'endpoint'):
                continue
                
            api_docs['endpoints'][endpoint_name] = {
                'endpoint_url': endpoint_class.endpoint,
                'parameters': getattr(endpoint_class, '_required_parameters', []),
                'optional_parameters': getattr(endpoint_class, '_optional_parameters', []),
                'default_parameters': getattr(endpoint_class, '_default_parameters', {}),
                'data_structure': get_endpoint_data_structure(endpoint_class)
            }
                
        except Exception as e:
            print(f"Error processing endpoint {endpoint_name}: {str(e)}")
    
    print(f"Successfully documented {len(api_docs['endpoints'])} endpoints")
    return api_docs

def save_documentation(api_docs, output_dir='api_documentation'):
    """Save the API documentation to files"""
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save endpoints documentation
    endpoints_file = output_path / 'endpoints.json'
    with open(endpoints_file, 'w') as f:
        json.dump(api_docs['endpoints'], f, indent=2)
    
    # Save static data
    static_file = output_path / 'static_data.json'
    with open(static_file, 'w') as f:
        json.dump(api_docs['static_data'], f, indent=2)
    
    # Create markdown documentation
    markdown_content = f"""# NBA API Documentation
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Available Endpoints

The following endpoints are available in the NBA API:

"""
    
    for endpoint_name, endpoint_info in api_docs['endpoints'].items():
        markdown_content += f"\n### {endpoint_name}\n"
        markdown_content += f"Endpoint URL: `{endpoint_info['endpoint_url']}`\n\n"
        
        if endpoint_info['parameters']:
            markdown_content += "Required Parameters:\n```python\n"
            markdown_content += json.dumps(endpoint_info['parameters'], indent=2)
            markdown_content += "\n```\n"
        
        if endpoint_info['optional_parameters']:
            markdown_content += "\nOptional Parameters:\n```python\n"
            markdown_content += json.dumps(endpoint_info['optional_parameters'], indent=2)
            markdown_content += "\n```\n"
        
        # Add data structure information
        if 'data_structure' in endpoint_info:
            data_structure = endpoint_info['data_structure']
            
            if 'parameters_used' in data_structure:
                markdown_content += "\nExample Parameters Used:\n```python\n"
                markdown_content += json.dumps(data_structure['parameters_used'], indent=2)
                markdown_content += "\n```\n"
            
            if 'datasets' in data_structure:
                markdown_content += "\nAvailable Datasets:\n"
                for dataset_name, dataset_info in data_structure['datasets'].items():
                    markdown_content += f"\n#### {dataset_info['name']}\n"
                    markdown_content += f"Row Count: {dataset_info['row_count']}\n\n"
                    
                    markdown_content += "Headers:\n```python\n"
                    markdown_content += json.dumps(dataset_info['headers'], indent=2)
                    markdown_content += "\n```\n"
                    
                    markdown_content += "\nColumns and Data Types:\n```python\n"
                    markdown_content += json.dumps(dataset_info['dtypes'], indent=2)
                    markdown_content += "\n```\n"
                    
                    if dataset_info['sample_data']:
                        markdown_content += "\nSample Data:\n```python\n"
                        markdown_content += json.dumps(dataset_info['sample_data'], indent=2)
                        markdown_content += "\n```\n"
    
    # Save markdown documentation
    markdown_file = output_path / 'api_documentation.md'
    with open(markdown_file, 'w') as f:
        f.write(markdown_content)
    
    print(f"\nDocumentation generated in: {output_path}")
    print(f"- Endpoints JSON: {endpoints_file}")
    print(f"- Static Data JSON: {static_file}")
    print(f"- Markdown Documentation: {markdown_file}")

# Generate and save the documentation
api_docs = analyze_api_structure()

# Display summary
print("\nDocumentation Summary:")
print(f"Total endpoints documented: {len(api_docs['endpoints'])}")
print(f"Total teams in static data: {len(api_docs['static_data']['teams'])}")
print(f"Total players in static data: {len(api_docs['static_data']['players'])}")

# Save the documentation
save_documentation(api_docs)

# Display first endpoint details
if api_docs['endpoints']:
    first_endpoint = next(iter(api_docs['endpoints']))
    print(f"\nSample endpoint ({first_endpoint}):")
    print(json.dumps(api_docs['endpoints'][first_endpoint], indent=2))