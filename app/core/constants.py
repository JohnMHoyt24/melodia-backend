EMBEDDING_DIM = 768
"""Dimensionality of artist embeddings - matches Gemini's text-embedding-004 output."""

CHARACTERISTIC_NAMES = [
    "energy",
    "valence",
    "melody",
    "aggression",
    "danceability",
    "complexity",
]
"""Fixed vocabulary of LLM-derived characteristic scores, each a float in [0, 1]."""
