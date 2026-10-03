# Snowflake-native Streamlit project snapshot

This directory preserves the project metadata generated for the original
Streamlit in Snowflake deployment. It is retained for provenance and possible
native redeployment; the public portfolio deployment uses Streamlit Community
Cloud instead.

The canonical application remains `app/streamlit_app.py`, and the canonical
theme/configuration remains `.streamlit/config.toml` at the repository root.
The archived `snowflake.yml` reflects the original Snowsight workspace layout,
where `streamlit_app.py`, `pyproject.toml` and `.streamlit/config.toml` were
siblings in one app project. Do not run this manifest directly from its
archival directory without first assembling that native project layout.

The original Snowflake `.streamlit/config.toml` contained comments only, so it
is not duplicated here; the repository's configured version is more complete.
