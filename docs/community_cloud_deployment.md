# RoutePulse public Streamlit deployment

Live deployment:
[routepulse-qdwrvckapptwi9xp74ueuuo.streamlit.app](https://routepulse-qdwrvckapptwi9xp74ueuuo.streamlit.app/)

The production deployment uses Python 3.12, the `main` branch and
`app/streamlit_app.py` as its entry point.

This deployment makes RoutePulse available at a normal `*.streamlit.app` URL.
Visitors do **not** need a Snowflake account. The app connects to Snowflake on
the server through a dedicated read-only service identity.

The public app retains the current filters, charts, maps and Snowflake-backed
queries. It is not a static export.

## Security design

- `ROUTEPULSE_PUBLIC_SERVICE` is the non-human service user.
- `ROUTEPULSE_PUBLIC_READER` can read the dashboard models but cannot modify
  data or Snowflake objects.
- `ROUTEPULSE_PUBLIC_WH` is a separate XSMALL warehouse with 60-second
  auto-suspend.
- The private key belongs only in Streamlit Community Cloud's Secrets editor.
  It must never be committed to GitHub or pasted into a Snowflake worksheet.
- The public key is the only key placed in Snowflake.

Do not deploy the public app as `ACCOUNTADMIN`, `ROUTEPULSE_APP_OWNER` or a
personal user.

## 1. Generate the service key locally

The first migration pass has already generated the key pair in `.secrets/`.
Do not regenerate it before completing deployment. These are the commands that
were used, and the same procedure is used for a future key rotation:

```bash
mkdir -p .secrets
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out .secrets/routepulse_rsa_key.p8 -nocrypt
openssl rsa -in .secrets/routepulse_rsa_key.p8 -pubout -out .secrets/routepulse_rsa_key.pub
```

`.secrets/` and private-key file extensions are ignored by Git. Keep the
private key as carefully as a password.

Copy the public-key body (this output is safe to place in Snowflake):

```bash
sed '/-----/d' .secrets/routepulse_rsa_key.pub | tr -d '\n'
```

## 2. Create the read-only Snowflake identity

For a new deployment, open
[13_community_cloud_access.sql](../sql/13_community_cloud_access.sql), replace
`PASTE_PUBLIC_KEY_WITHOUT_HEADERS_OR_LINE_BREAKS` with the generated public-key
body, select the complete worksheet and run it once as `ACCOUNTADMIN`. The
current RoutePulse Snowflake identity has already been configured.

Confirm the final `SHOW GRANTS` results contain the reader role, warehouse
usage, database/schema usage and SELECT grants. They should not contain
INSERT, UPDATE, DELETE, CREATE, MODIFY or OWNERSHIP.

Find the Community Cloud account identifier with:

```sql
SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME();
```

Use `organization-account` in the secret—for example,
`MYORG-MYACCOUNT`. Do not use the full `snowflakecomputing.com` hostname.

## 3. Test the public connection locally

Copy the example secrets file:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Fill in:

- `account`: the `organization-account` identifier from the SQL above;
- the complete contents of `.secrets/routepulse_rsa_key.p8` between the
  triple quotes.

The other values should remain as provided. Then install and run:

```bash
python3.12 -m venv .venv-dashboard
source .venv-dashboard/bin/activate
python -m pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

Keep this dashboard environment separate from the pipeline `.venv`. Streamlit
and `gtfs-realtime-bindings` currently require incompatible major versions of
`protobuf`, while the deployed dashboard does not need the collection package.

Open the local URL, change every transport mode, and visit Network map,
Stations, Lines, When and Data quality. Stop the server with `Ctrl+C`.

Never commit `.streamlit/secrets.toml`.

## 4. Put the app on GitHub

Create a GitHub repository and push this folder. The minimum deployment files
are:

- `app/streamlit_app.py`
- `requirements.txt`
- `.streamlit/config.toml`

The maps and boundaries used by v4 are read from the Snowflake presentation
models; the older local GeoJSON exports are not required by the public app.

Keep the SQL, validator and this guide in the repository as reproducible
project evidence. Confirm that neither `.streamlit/secrets.toml` nor
`.secrets/` appears on GitHub.

## 5. Deploy to Streamlit Community Cloud

1. Sign in at [share.streamlit.io](https://share.streamlit.io/) with GitHub.
2. Choose **Create app** and select the repository and branch.
3. Set the entrypoint to `app/streamlit_app.py`.
4. Choose Python 3.12 in Advanced settings.
5. In **Advanced settings → Secrets**, paste the same structure as
   `.streamlit/secrets.toml.example`, replacing the account and private-key
   placeholders with the real values.
6. Deploy the app and choose a memorable subdomain when prompted.

The GitHub repository may be private or public. The Streamlit app itself must
be set to public for recruiters to open it without signing in.

## 6. Verify the deployed result

Use an incognito/private browser window where neither GitHub nor Snowflake is
signed in. Verify:

- the public URL loads without an authentication prompt;
- every transport-mode button updates the KPIs;
- all five views render and the map can be panned/zoomed;
- the Lines selector draws a route;
- no error reveals connection details or secrets;
- Snowflake query history for `ROUTEPULSE_PUBLIC_SERVICE` shows only SELECT
  statements from the public app.

The app currently caches query results for 10 minutes. New or refreshed
Snowflake presentation data can therefore take up to 10 minutes to appear.

## Operating notes

- A public app can generate Snowflake warehouse cost. The dedicated warehouse
  auto-suspends, but add a resource monitor before advertising the link widely.
- Streamlit Community Cloud may put an inactive app to sleep; the first visit
  afterward can take longer while it wakes and Snowflake resumes the warehouse.
- If a private key is ever exposed, generate a replacement, update the
  Snowflake user's public key and the Streamlit secret, then discard the old
  key.
