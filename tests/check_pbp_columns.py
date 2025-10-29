from nba_api.stats.endpoints import PlayByPlayV3

result = PlayByPlayV3(game_id='0022300001', start_period=1, end_period=1)
dfs = result.get_data_frames()

print(f'Number of dataframes: {len(dfs)}')
for i, df in enumerate(dfs):
    print(f'\nDF[{i}]:')
    print(f'  Shape: {df.shape}')
    print(f'  Columns: {list(df.columns)[:15]}')
