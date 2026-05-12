#!/usr/bin/env python3
"""Teste les statistiques du fichier musique_complete.csv avec songs.csv"""

import pandas as pd

df = pd.read_csv('data/clean/musique_complete.csv')
print(f'Total rows: {len(df)}')
print(f'Rows with track_id (genres): {df["track_id"].notna().sum()}')
matching_rate = df["track_id"].notna().sum()/len(df)*100
print(f'Matching rate: {matching_rate:.2f}%')
print(f'Songs WITHOUT genres: {df["track_id"].isna().sum()} ({100-matching_rate:.2f}%)')
print(f'\nColumns:')
print(df.columns.tolist())
print(f'\nSample with genres:')
sample = df[df['track_id'].notna()][['song', 'artist', 'track_genre', 'source_chart']].head(20)
print(sample)

# Check niche_genres
if 'niche_genres' in df.columns:
    print(f'\n\nNiche genres distribution:')
    print(df['niche_genres'].value_counts().head(20))
