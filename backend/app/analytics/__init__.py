"""MedGraph analytics package.

Pure functions over pandas DataFrames / networkx graphs. Kept free of I/O so the
logic is unit-testable and reusable by both the ingest (precompute) and the API
(on-demand) layers.
"""
