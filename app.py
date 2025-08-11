import streamlit as st
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
import uvicorn
import threading
import sqlite3


# SQLite persistent storage
DB_PATH = "iot_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Check if sensor_data table exists and has channelId column
    c.execute("PRAGMA table_info(sensor_data)")
    columns = [row[1] for row in c.fetchall()]
    if 'channelId' not in columns:
        c.execute("DROP TABLE IF EXISTS sensor_data")
    c.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            channelId TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            fields TEXT NOT NULL -- comma separated field names
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channelId TEXT NOT NULL,
            field TEXT NOT NULL,
            value TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def create_channel(channelId, name, fields):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Check for duplicate channelId
    c.execute("SELECT channelId FROM channels WHERE channelId=?", (channelId,))
    if c.fetchone():
        conn.close()
        return False, "Channel already exists"
    c.execute("INSERT INTO channels (channelId, name, fields) VALUES (?, ?, ?)", (channelId, name, ','.join(fields)))
    conn.commit()
    conn.close()
    return True, "Channel created"

def get_channels():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT channelId, name, fields FROM channels")
    rows = c.fetchall()
    conn.close()
    return rows

def insert_data(channelId, data_list):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Validate channel exists
    c.execute("SELECT fields FROM channels WHERE channelId=?", (channelId,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "Channel does not exist"
    allowed_fields = row[0].split(',')
    for d in data_list:
        if d["field"] not in allowed_fields:
            conn.close()
            return False, f"Field {d['field']} not allowed in channel {channelId}"
        # Optionally validate data type here (e.g., float, int, str)
    c.executemany(
        "INSERT INTO sensor_data (channelId, field, value) VALUES (?, ?, ?)",
        [ (channelId, d["field"], str(d["value"])) for d in data_list ]
    )
    conn.commit()
    conn.close()
    return True, "Data inserted"

def fetch_data(channelId=None):
    conn = sqlite3.connect(DB_PATH)
    if channelId:
        query = "SELECT channelId, field, value, timestamp FROM sensor_data WHERE channelId=? ORDER BY timestamp ASC"
        df = pd.read_sql_query(query, conn, params=(channelId,))
    else:
        df = pd.read_sql_query("SELECT channelId, field, value, timestamp FROM sensor_data ORDER BY timestamp ASC", conn)
    conn.close()
    return df

init_db()

# FastAPI setup with rate limiting
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter


# API to create a channel
@app.post("/api/channel")
async def api_create_channel(request: Request):
    payload = await request.json()
    channelId = payload.get("channelId")
    name = payload.get("name")
    fields = payload.get("fields")
    if not channelId or not name or not fields or not isinstance(fields, list):
        return JSONResponse({"error": "Missing or invalid channelId, name, or fields (must be a list)"}, status_code=400)
    success, msg = create_channel(channelId, name, fields)
    if not success:
        return JSONResponse({"error": msg}, status_code=400)
    return {"status": "success", "message": msg}

# API to get channels
@app.get("/api/channels")
async def api_get_channels():
    rows = get_channels()
    return {"channels": [ {"channelId": r[0], "name": r[1], "fields": r[2].split(',')} for r in rows ]}

# API to insert data
@app.post("/api/data")
@limiter.limit("50/minute")
async def receive_data(request: Request):
    payload = await request.json()
    channelId = payload.get("channelId")
    data_list = payload.get("data")
    if not channelId or not data_list or not isinstance(data_list, list):
        return JSONResponse({"error": "Missing or invalid channelId or data (must be a list of {field, value})"}, status_code=400)
    for item in data_list:
        if not all(k in item for k in ("field", "value")):
            return JSONResponse({"error": "Each item must have 'field' and 'value'"}, status_code=400)
    success, msg = insert_data(channelId, data_list)
    if not success:
        return JSONResponse({"error": msg}, status_code=400)
    return {"status": "success", "message": msg, "count": len(data_list)}

# API to get data by channelId
@app.get("/api/data/{channelId}")
async def api_get_data(channelId: str):
    df = fetch_data(channelId)
    return {"data": df.to_dict(orient="records")}

# Run FastAPI in a separate thread
def run_api():
    uvicorn.run(app, host="0.0.0.0", port=8000)

api_thread = threading.Thread(target=run_api, daemon=True)
api_thread.start()


# Streamlit UI with navigation
st.set_page_config(page_title="IoT Data Dashboard", layout="wide")
st.title("IoT Data Visualization Dashboard")

menu = st.sidebar.radio("Navigate", ["Create Channel", "Visualize & Export Data"])

channels = get_channels()
channel_ids = [c[0] for c in channels]
channel_names = {c[0]: c[1] for c in channels}
channel_fields = {c[0]: c[2].split(',') for c in channels}

if menu == "Create Channel":
    st.header("Create a Channel")
    with st.form("create_channel_form"):
        new_channel_id = st.text_input("Channel ID")
        new_channel_name = st.text_input("Channel Name")
        new_fields = st.text_area("Fields (comma separated, e.g. temperature,humidity,pressure)")
        submitted = st.form_submit_button("Create Channel")
        if submitted:
            fields_list = [f.strip() for f in new_fields.split(",") if f.strip()]
            if new_channel_id and new_channel_name and fields_list:
                success, msg = create_channel(new_channel_id, new_channel_name, fields_list)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.error("Please provide all details.")
    st.subheader("Existing Channels")
    for cid, name, fields in channels:
        st.write(f"**ID:** {cid} | **Name:** {name} | **Fields:** {fields}")

elif menu == "Visualize & Export Data":
    st.header("Data Visualization & Export")
    selected_channel = st.selectbox("Select Channel", channel_ids, format_func=lambda x: f"{x} ({channel_names.get(x,'')})")
    st.write(f"**Channel Name:** {channel_names.get(selected_channel,'')} | **Fields:** {', '.join(channel_fields.get(selected_channel,[]))}")
    vis_df = fetch_data(selected_channel)
    if not vis_df.empty:
        fields = channel_fields.get(selected_channel,[])
        combine = st.multiselect("Select fields to combine in one graph", fields, default=fields[:1])
        for field in fields:
            field_df = vis_df[vis_df['field'] == field].sort_values("timestamp")
            try:
                field_df['value'] = field_df['value'].astype(float)
            except:
                pass
            st.subheader(f"Field: {field}")
            st.line_chart(field_df.set_index("timestamp")["value"], use_container_width=True)
        if len(combine) > 1:
            st.subheader("Combined Graph")
            combined_df = vis_df[vis_df['field'].isin(combine)].copy()
            try:
                combined_df['value'] = combined_df['value'].astype(float)
            except:
                pass
            pivot_df = combined_df.pivot(index="timestamp", columns="field", values="value")
            st.line_chart(pivot_df, use_container_width=True)
        import io
        st.subheader("Export Data")
        st.download_button("Download CSV", vis_df.to_csv(index=False), file_name=f"{selected_channel}_data.csv", mime="text/csv")
        excel_buffer = io.BytesIO()
        vis_df.to_excel(excel_buffer, index=False)
        st.download_button("Download Excel", excel_buffer.getvalue(), file_name=f"{selected_channel}_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("No data for selected channel.")

    st.markdown("""
    **API Endpoints:**
    - Create Channel: `/api/channel` (POST)
        - JSON: `{ "channelId": "ch1", "name": "Room1", "fields": ["temperature", "humidity"] }`
    - List Channels: `/api/channels` (GET)
    - Insert Data: `/api/data` (POST)
        - JSON: `{ "channelId": "ch1", "data": [ { "field": "temperature", "value": 25.5 }, ... ] }`
    - Get Data: `/api/data/{channelId}` (GET)
    
    Rate limit: 5 requests/minute per IP
    Data is stored persistently in SQLite (`iot_data.db`).
    """)
