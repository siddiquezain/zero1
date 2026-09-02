"""
src/intelligence — framework-agnostic service + tool layer for SIH26162.

Both the Streamlit UI and the Fire Intelligence Agent call ONLY this package.
There must be no Streamlit / UI import anywhere under src/intelligence/.

Modules:
    geo        lat/lon -> Indian state / region (offline, no network)
    queries    read-only data access (alerts, investigations, analytics, facilities)
    actions    read-only outputs (GeoJSON / CSV / incident report) + manual-UI helpers
    agent/     deterministic natural-language layer over the read-only tool registry
"""
