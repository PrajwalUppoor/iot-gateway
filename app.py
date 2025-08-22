import streamlit as st
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
import uvicorn
import threading
import sqlite3
import numpy as np
import matplotlib.pyplot as plt


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


# API to insert data via query params (GET for ESP8266/AT compatibility)
from fastapi import Query
@app.get("/api/data")
@limiter.limit("50/minute")
async def receive_data_query(
    request: Request,
    channelId: str = Query(...),
    field1: str = Query(...),
    value1: str = Query(...),
    field2: str = Query(None),
    value2: str = Query(None),
    field3: str = Query(None),
    value3: str = Query(None),
    field4: str = Query(None),
    value4: str = Query(None),
    field5: str = Query(None),
    value5: str = Query(None)
):
    # Support up to 5 fields per request
    data_list = []
    if field1 and value1:
        data_list.append({"field": field1, "value": value1})
    for f, v in zip([field2, field3, field4, field5], [value2, value3, value4, value5]):
        if f is not None and v is not None:
            data_list.append({"field": f, "value": v})
    if not channelId or not data_list:
        return JSONResponse({"error": "Missing channelId or data"}, status_code=400)
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

menu = st.sidebar.radio(
    "Navigate",
    [
        "Create Channel",
        "Visualize & Export Data",
        "Arduino Code Cheatsheet",
        "Sensors & Components",
        "Arduino Quiz",
        "Arduino Projects",
        "Flex/MQ2/Color Sensor Integration",
        "DHT Sensor Integration",
        "Arduino Tutorials Blog",
        "Ultrasonic Sensor Guide",
        "L293D Motor Driver Guide",
        "Sensor Working & Integration",
        "Arduino Boards Comparison",
        "Arduino Concepts",
        "Starter Codes & Programming",
        "Electronics Concepts",
        "Serial Protocols (SPI/I2C/UART)",
        "Common Mistakes & Best Practices",
        "Productization Steps",
        "Applications & Advanced Projects",
        "Motor Control & PID Integration",
        "Arduino Control System Mimic",
        "Serial Read from Serial Monitor",
    "Raspberry Pi Full Guide",
    "Raspberry Pi Starters & Cheatsheet",
    "Raspberry Pi Sensor Integrations",
    "Raspberry Pi GPS Sensor Integration (I2C)"




    ]

)

channels = get_channels()
channel_ids = [c[0] for c in channels]
channel_names = {c[0]: c[1] for c in channels}
channel_fields = {c[0]: c[2].split(',') for c in channels}

# --- Navigation Logic ---
if menu == "Create Channel":
    st.header("Create a Channel")
    with st.form("create_channel_form_main"):
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

elif menu == "Motor Control & PID Integration":
    st.header("DC Motor Control with Arduino: P, PI, PID Optimization")
    st.markdown('''
    This page explains how to control a DC motor with Arduino and optimize its response using P, PI, and PID controllers. You can visualize the error signal before and after applying each controller.
    
    **Basic Motor Control Circuit:**
    - Arduino PWM pin (e.g., D9) to L293D ENA
    - IN1/IN2 to digital pins for direction
    - Motor powered via L293D
    - Potentiometer or sensor for feedback (e.g., speed, position)
    
    **Arduino Code (Open Loop):**
    ```cpp
    #define ENA 9
    #define IN1 8
    #define IN2 7
    void setup() {
      pinMode(ENA, OUTPUT); pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
    }
    void loop() {
      digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
      analogWrite(ENA, 180); // Set speed
    }
    ```
    
    **Closed Loop (with PID):**
    Use a sensor (e.g., rotary encoder, potentiometer) to measure speed/position and adjust PWM accordingly.
    
    **PID Algorithm (Arduino):**
    ```cpp
    double Kp=2, Ki=0.5, Kd=1;
    double setpoint=100, input=0, output=0, lastError=0, integral=0;
    void loop() {
      input = analogRead(A0); // Feedback
      double error = setpoint - input;
      integral += error;
      double derivative = error - lastError;
      output = Kp*error + Ki*integral + Kd*derivative;
      output = constrain(output, 0, 255);
      analogWrite(ENA, output);
      lastError = error;
      delay(20);
    }
    ```
    ''')
    st.subheader("Error Signal Visualization (Simulated)")
    st.markdown("Below: Simulated error response for a step input with no controller, P, PI, and PID controllers.")
    # Simulate error signals
    t = np.linspace(0, 5, 200)
    error_open = np.exp(-0.5*t) * (1-np.exp(-2*t))
    error_p = np.exp(-1.2*t) * (1-np.exp(-2*t))
    error_pi = np.exp(-2*t) * (1-np.exp(-2*t/1.5))
    error_pid = np.exp(-3*t) * (1-np.exp(-2*t/1.2))
    fig, ax = plt.subplots()
    ax.plot(t, error_open, label="Open Loop (No Controller)")
    ax.plot(t, error_p, label="P Controller")
    ax.plot(t, error_pi, label="PI Controller")
    ax.plot(t, error_pid, label="PID Controller")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Error")
    ax.set_title("Error Signal Before/After Controller")
    ax.legend()
    st.pyplot(fig)
    st.markdown("""
    **Interpretation:**
    - **Open Loop:** Error decays slowly, steady-state error remains.
    - **P:** Faster decay, but steady-state error may persist.
    - **PI:** Eliminates steady-state error, but may oscillate.
    - **PID:** Fastest response, minimal overshoot and steady-state error.
    
    **Tips:**
    - Tune Kp, Ki, Kd for your system.
    - Use Serial Monitor to plot error in real time (send error value from Arduino).
    - For real hardware, use a sensor for feedback and plot error in Python/Excel.
    """)

elif menu == "Serial Read from Serial Monitor":
    st.header("Reading Data from Arduino Serial Monitor")
    st.markdown("""
    This page explains how to read data from Arduino using the Serial Monitor, including a full code example and usage tips.
    
    **What is the Serial Monitor?**
    - The Serial Monitor is a tool in the Arduino IDE that allows you to send and receive data to/from your Arduino board over USB.
    - Useful for debugging, displaying sensor values, and communicating with your PC.
    
    **Basic Serial Read Code (Arduino):**
    ```cpp
    void setup() {
      Serial.begin(9600); // Start serial communication at 9600 baud
    }
    void loop() {
      if (Serial.available() > 0) {
        String input = Serial.readStringUntil('\n'); // Read input until newline
        Serial.print("You typed: ");
        Serial.println(input);
      }
    }
    ```
    
    **How to Use:**
    1. Upload the code to your Arduino board.
    2. Open the Serial Monitor from the Arduino IDE (Tools > Serial Monitor or Ctrl+Shift+M).
    3. Set the baud rate to 9600 (bottom right of Serial Monitor).
    4. Type a message and press Enter. The Arduino will echo back what you typed.
    
    **Reading Sensor Data Example:**
    ```cpp
    void setup() {
      Serial.begin(9600);
    }
    void loop() {
      int sensorValue = analogRead(A0);
      Serial.print("Sensor Value: ");
      Serial.println(sensorValue);
      delay(500);
    }
    ```
    
    **Tips:**
    - Use `Serial.print()` and `Serial.println()` to send data to the Serial Monitor.
    - Use `Serial.read()`, `Serial.readString()`, or `Serial.readStringUntil()` to receive data from the Serial Monitor.
    - Always match the baud rate in your code and Serial Monitor.
    - You can plot data in the Serial Plotter (Tools > Serial Plotter) for real-time graphs.
    
    For more, see [Arduino Serial Reference](https://www.arduino.cc/reference/en/language/functions/communication/serial/).
    """)

elif menu == "Arduino Control System Mimic":
    st.header("Arduino-Based Control System: Multi-Sensor Integration & Mimic")
    st.markdown("""
    This page demonstrates how to use Arduino to mimic a control system using multiple sensors (e.g., temperature, light, distance) and actuators (motors, LEDs, buzzers).
    
    **Example: Environmental Control System**
    - **Sensors:** DHT11 (temperature/humidity), LDR (light), Ultrasonic (distance)
    - **Actuators:** Fan (motor), Light (LED), Buzzer
    
    **Block Diagram:**
    <div style='display:flex;align-items:center;gap:16px;'>
      <div style='background:#e3f2fd;padding:8px 16px;border-radius:8px;'>Sensors<br>DHT11, LDR, HC-SR04</div>
      <div style='font-size:2em;'>&rarr;</div>
      <div style='background:#fffde7;padding:8px 16px;border-radius:8px;'>Arduino<br>Control Logic</div>
      <div style='font-size:2em;'>&rarr;</div>
      <div style='background:#e8f5e9;padding:8px 16px;border-radius:8px;'>Actuators<br>Fan, LED, Buzzer</div>
    </div>
    
    **Sample Arduino Code:**
    ```cpp
    #include <DHT.h>
    #define DHTPIN 2
    #define DHTTYPE DHT11
    DHT dht(DHTPIN, DHTTYPE);
    #define LDR A0
    #define TRIG 9
    #define ECHO 8
    #define FAN 3
    #define LIGHT 4
    #define BUZZER 5
    void setup() {
      pinMode(FAN, OUTPUT); pinMode(LIGHT, OUTPUT); pinMode(BUZZER, OUTPUT);
      Serial.begin(9600); dht.begin();
      pinMode(TRIG, OUTPUT); pinMode(ECHO, INPUT);
    }
    void loop() {
      float temp = dht.readTemperature();
      int light = analogRead(LDR);
      // Ultrasonic distance
      digitalWrite(TRIG, LOW); delayMicroseconds(2);
      digitalWrite(TRIG, HIGH); delayMicroseconds(10);
      digitalWrite(TRIG, LOW);
      long duration = pulseIn(ECHO, HIGH);
      float distance = duration * 0.034 / 2;
      // Control logic
      if(temp > 30) digitalWrite(FAN, HIGH); else digitalWrite(FAN, LOW);
      if(light < 300) digitalWrite(LIGHT, HIGH); else digitalWrite(LIGHT, LOW);
      if(distance < 20) digitalWrite(BUZZER, HIGH); else digitalWrite(BUZZER, LOW);
      delay(500);
    }
    ```
    
    **How to Extend:**
    - Add PID for fan speed (temperature control)
    - Log sensor data to PC/cloud
    - Add LCD/serial output for monitoring
    - Use more sensors/actuators as needed
    
    **Visualization:**
    - Use Streamlit/Matplotlib to plot sensor readings and actuator states (upload CSV from Arduino)
    - Simulate control logic in Python for learning
    """, unsafe_allow_html=True)

channels = get_channels()
channel_ids = [c[0] for c in channels]
channel_names = {c[0]: c[1] for c in channels}
channel_fields = {c[0]: c[2].split(',') for c in channels}


if menu == "Create Channel":
    st.header("Create a Channel")
    with st.form("create_channel_form_sidebar"):
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

elif menu == "Arduino Code Cheatsheet":
    st.header("Arduino Code Cheatsheet: Analog & Digital IO")
    st.markdown("""
**Analog Input:**
```cpp
int sensorValue = analogRead(A0); // Reads analog value from pin A0
```

**Analog Output (PWM):**
```cpp
analogWrite(9, 128); // Writes PWM value (0-255) to pin 9
```

**Digital Input:**
```cpp
int buttonState = digitalRead(2); // Reads digital value from pin 2
```

**Digital Output:**
```cpp
digitalWrite(13, HIGH); // Sets pin 13 HIGH
digitalWrite(13, LOW);  // Sets pin 13 LOW
```
    """)

elif menu == "Sensors & Components":
    st.header("Sensors & Components for Arduino")
    st.markdown("### Common Sensors:")
    # CSS/HTML circuit diagrams for each sensor
    sensor_diagrams = {
        "DHT11/DHT22 Temperature & Humidity Sensor": '''
<div style="display:flex;align-items:center;gap:16px;">
  <div style="width:80px;height:80px;position:relative;background:#e0f7fa;border-radius:10px;border:2px solid #0097a7;">
    <div style="position:absolute;left:35px;top=0;width:10px;height:80px;background:#607d8b;"></div>
    <div style="position:absolute;left:0;top:35px;width:80px;height:10px;background:#607d8b;"></div>
    <div style="position:absolute;left:38px;top:38px;width:4px;height:4px;background:#0097a7;border-radius:50%;"></div>
    <div style="position:absolute;left:10px;top:70px;width:60px;height:6px;background:#0097a7;border-radius:3px;"></div>
  </div>
  <div>DHT11/DHT22 Sensor<br><span style='font-size:12px;color:#555;'>3-pin, digital output</span></div>
</div>
''',
        "LDR (Light Dependent Resistor)": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="80" height="60">
    <rect x="10" y="20" width="60" height="20" rx="8" fill="#fffde7" stroke="#fbc02d" stroke-width="3"/>
    <line x1="0" y1="30" x2="10" y2="30" stroke="#616161" stroke-width="2"/>
    <line x1="70" y1="30" x2="80" y2="30" stroke="#616161" stroke-width="2"/>
    <line x1="20" y1="20" x2="60" y2="40" stroke="#fbc02d" stroke-width="2"/>
    <line x1="20" y1="40" x2="60" y2="20" stroke="#fbc02d" stroke-width="2"/>
  </svg>
  <div>LDR Sensor<br><span style='font-size:12px;color:#555;'>Light dependent resistor</span></div>
</div>
''',
        "Ultrasonic Sensor (HC-SR04)": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="90" height="60">
    <rect x="10" y="10" width="70" height="40" rx="8" fill="#e3f2fd" stroke="#1976d2" stroke-width="2"/>
    <circle cx="30" cy="30" r="10" fill="#fff" stroke="#1976d2" stroke-width="2"/>
    <circle cx="60" cy="30" r="10" fill="#fff" stroke="#1976d2" stroke-width="2"/>
    <rect x="40" y="50" width="10" height="10" fill="#1976d2"/>
  </svg>
  <div>HC-SR04 Ultrasonic<br><span style='font-size:12px;color:#555;'>Trig/Echo pins</span></div>
</div>
''',
        "IR Sensor": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="80" height="60">
    <rect x="20" y="10" width="40" height="40" rx="8" fill="#f3e5f5" stroke="#7b1fa2" stroke-width="2"/>
    <ellipse cx="40" cy="30" rx="10" ry="18" fill="#fff" stroke="#7b1fa2" stroke-width="2"/>
    <rect x="36" y="48" width="8" height="10" fill="#7b1fa2"/>
  </svg>
  <div>IR Sensor<br><span style='font-size:12px;color:#555;'>Reflective/Obstacle</span></div>
</div>
''',
        "Soil Moisture Sensor": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="80" height="60">
    <rect x="30" y="10" width="20" height="40" rx="6" fill="#e8f5e9" stroke="#388e3c" stroke-width="2"/>
    <rect x="36" y="50" width="8" height="10" fill="#388e3c"/>
    <rect x="36" y="0" width="8" height="10" fill="#388e3c"/>
    <rect x="30" y="25" width="20" height="10" fill="#a5d6a7"/>
  </svg>
  <div>Soil Moisture Sensor<br><span style='font-size:12px;color:#555;'>Analog output</span></div>
</div>
''',
        "MQ-2 Gas Sensor": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="80" height="60">
    <rect x="20" y="10" width="40" height="40" rx="10" fill="#fff3e0" stroke="#f57c00" stroke-width="2"/>
    <circle cx="40" cy="30" r="12" fill="#fff" stroke="#f57c00" stroke-width="2"/>
    <rect x="36" y="48" width="8" height="10" fill="#f57c00"/>
  </svg>
  <div>MQ-2 Gas Sensor<br><span style='font-size:12px;color:#555;'>Analog/Digital output</span></div>
</div>
''',
    }
    sensors = [
        {"name": "DHT11/DHT22 Temperature & Humidity Sensor", "use": "Measure temperature and humidity", "application": "Weather stations, greenhouses"},
        {"name": "LDR (Light Dependent Resistor)", "use": "Detect light intensity", "application": "Automatic lighting, light meters"},
        {"name": "Ultrasonic Sensor (HC-SR04)", "use": "Measure distance", "application": "Obstacle avoidance, level measurement"},
        {"name": "IR Sensor", "use": "Detect objects, proximity", "application": "Line following robots, object counters"},
        {"name": "Soil Moisture Sensor", "use": "Measure soil moisture", "application": "Smart irrigation"},
        {"name": "MQ-2 Gas Sensor", "use": "Detect gas leaks", "application": "Safety, air quality monitoring"},
    ]
    for s in sensors:
        st.markdown(sensor_diagrams[s["name"]], unsafe_allow_html=True)
        st.write(f"**{s['name']}**  ")
        st.write(f"Use: {s['use']}")
        st.write(f"Application: {s['application']}")
        st.markdown("---")

    st.markdown("### Common Components:")
    # CSS/HTML circuit diagrams for each component
    component_diagrams = {
        "Breadboard": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="100" height="40">
    <rect x="5" y="5" width="90" height="30" rx="6" fill="#fff" stroke="#607d8b" stroke-width="2"/>
    <rect x="10" y="10" width="80" height="20" fill="#b0bec5"/>
    <rect x="10" y="15" width="80" height="10" fill="#fff"/>
    <circle cx="20" cy="20" r="2" fill="#607d8b"/>
    <circle cx="30" cy="20" r="2" fill="#607d8b"/>
    <circle cx="40" cy="20" r="2" fill="#607d8b"/>
    <circle cx="50" cy="20" r="2" fill="#607d8b"/>
    <circle cx="60" cy="20" r="2" fill="#607d8b"/>
    <circle cx="70" cy="20" r="2" fill="#607d8b"/>
    <circle cx="80" cy="20" r="2" fill="#607d8b"/>
    <circle cx="90" cy="20" r="2" fill="#607d8b"/>
  </svg>
  <div>Breadboard</div>
</div>
''',
        "Jumper Wires": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="80" height="40">
    <line x1="10" y1="10" x2="70" y2="30" stroke="#388e3c" stroke-width="4"/>
    <circle cx="10" cy="10" r="4" fill="#388e3c"/>
    <circle cx="70" cy="30" r="4" fill="#388e3c"/>
  </svg>
  <div>Jumper Wires</div>
</div>
''',
        "Resistors": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="80" height="40">
    <line x1="0" y1="20" x2="20" y2="20" stroke="#616161" stroke-width="2"/>
    <rect x="20" y="12" width="40" height="16" rx="6" fill="#fffde7" stroke="#fbc02d" stroke-width="2"/>
    <line x1="60" y1="20" x2="80" y2="20" stroke="#616161" stroke-width="2"/>
    <rect x="35" y="16" width="10" height="8" fill="#fbc02d"/>
  </svg>
  <div>Resistor</div>
</div>
''',
        "Capacitors": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="80" height="40">
    <line x1="10" y1="20" x2="30" y2="20" stroke="#616161" stroke-width="2"/>
    <rect x="30" y="10" width="8" height="20" fill="#bdbdbd"/>
    <rect x="42" y="10" width="8" height="20" fill="#bdbdbd"/>
    <line x1="50" y1="20" x2="70" y2="20" stroke="#616161" stroke-width="2"/>
  </svg>
  <div>Capacitor</div>
</div>
''',
        "Push Button": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="60" height="60">
    <rect x="10" y="20" width="40" height="20" rx="6" fill="#fff" stroke="#607d8b" stroke-width="2"/>
    <circle cx="30" cy="30" r="8" fill="#90caf9" stroke="#1976d2" stroke-width="2"/>
  </svg>
  <div>Push Button</div>
</div>
''',
        "LED": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="60" height="60">
    <rect x="25" y="40" width="10" height="15" fill="#616161"/>
    <circle cx="30" cy="30" r="12" fill="#f44336" stroke="#b71c1c" stroke-width="2"/>
    <rect x="27" y="20" width="6" height="10" fill="#fff"/>
  </svg>
  <div>LED</div>
</div>
''',
        "Potentiometer": '''
<div style="display:flex;align-items:center;gap:16px;">
  <svg width="80" height="40">
    <rect x="30" y="10" width="20" height="20" rx="6" fill="#fffde7" stroke="#fbc02d" stroke-width="2"/>
    <circle cx="40" cy="20" r="6" fill="#bdbdbd" stroke="#616161" stroke-width="2"/>
    <rect x="38" y="0" width="4" height="10" fill="#616161"/>
  </svg>
  <div>Potentiometer</div>
</div>
''',
    }
    components = [
        {"name": "Breadboard", "use": "Prototyping circuits", "application": "All Arduino projects"},
        {"name": "Jumper Wires", "use": "Connect components", "application": "All Arduino projects"},
        {"name": "Resistors", "use": "Limit current", "application": "LEDs, sensors"},
        {"name": "Capacitors", "use": "Store charge, filter signals", "application": "Power supply, signal filtering"},
        {"name": "Push Button", "use": "User input", "application": "Switches, user interfaces"},
        {"name": "LED", "use": "Visual indicator", "application": "Status, output"},
        {"name": "Potentiometer", "use": "Variable resistor", "application": "Volume control, sensor calibration"},
    ]
    for c in components:
        st.markdown(component_diagrams[c["name"]], unsafe_allow_html=True)
        st.write(f"**{c['name']}**  ")
        st.write(f"Use: {c['use']}")
        st.write(f"Application: {c['application']}")
        st.markdown("---")


elif menu == "Arduino Quiz":

    import random
    st.header("Arduino Quiz")
    st.info("Click the 'New Quiz' button below to get a new set of questions. Once you submit, your answers and results will remain visible until you click 'New Quiz'.")

    # 25 sets of 20 realistic Arduino questions each
    question_bank = [
        # Set 1
        [
            {"question": "What is the function of 'pinMode(13, OUTPUT);' in Arduino?", "options": ["Sets pin 13 as input", "Sets pin 13 as output", "Reads analog value from pin 13", "Enables PWM on pin 13"], "answer": 1},
            {"question": "Which Arduino function is used to read a digital input?", "options": ["digitalWrite()", "analogRead()", "digitalRead()", "pinMode()"], "answer": 2},
            {"question": "What voltage is considered HIGH on most Arduino digital pins?", "options": ["0V", "1.1V", "3.3V", "5V"], "answer": 3},
            {"question": "Which function sends data to the Serial Monitor?", "options": ["Serial.print()", "Serial.begin()", "Serial.read()", "Serial.write()"], "answer": 0},
            {"question": "What is the default baud rate for Serial communication in Arduino examples?", "options": ["4800", "9600", "115200", "19200"], "answer": 1},
            {"question": "Which pin is typically used for onboard LED on Arduino Uno?", "options": ["7", "10", "13", "A0"], "answer": 2},
            {"question": "What does 'analogRead(A0)' return?", "options": ["A voltage value", "A value between 0-1023", "A value between 0-255", "A boolean value"], "answer": 1},
            {"question": "Which function is used to generate PWM output?", "options": ["analogRead()", "analogWrite()", "digitalWrite()", "tone()"], "answer": 1},
            {"question": "What is the purpose of a pull-down resistor?", "options": ["To keep pin HIGH by default", "To keep pin LOW by default", "To limit current to LED", "To filter analog signals"], "answer": 1},
            {"question": "Which sensor is best for measuring temperature?", "options": ["LDR", "DHT11", "HC-SR04", "MQ-2"], "answer": 1},
            {"question": "What is the use of 'delay(1000);' in Arduino code?", "options": ["Repeat code 1000 times", "Pause for 1 second", "Set pin 1000 HIGH", "Start timer"], "answer": 1},
            {"question": "Which command initializes serial communication?", "options": ["Serial.begin(9600);", "Serial.print(9600);", "Serial.init(9600);", "Serial.start(9600);"], "answer": 0},
            {"question": "What is the range of values for analogWrite()?", "options": ["0-1023", "0-255", "0-1", "0-4095"], "answer": 1},
            {"question": "Which function is called only once in a sketch?", "options": ["loop()", "setup()", "main()", "start()"], "answer": 1},
            {"question": "What does 'digitalRead(2)' return if the button is pressed and connected to GND?", "options": ["HIGH", "LOW", "1", "Error"], "answer": 1},
            {"question": "Which sensor is used for distance measurement?", "options": ["DHT11", "HC-SR04", "LDR", "BMP180"], "answer": 1},
            {"question": "What is the use of a breadboard?", "options": ["Permanent soldering", "Prototyping circuits", "Programming Arduino", "Power supply"], "answer": 1},
            {"question": "Which function is used to set a pin HIGH or LOW?", "options": ["digitalWrite()", "digitalRead()", "analogWrite()", "pinMode()"], "answer": 0},
            {"question": "What is the output of 'Serial.println(123);'?", "options": ["123", "'123'", "Serial error", "Nothing"], "answer": 0},
            {"question": "Which component is used to limit current in a circuit?", "options": ["Capacitor", "Resistor", "Inductor", "Transistor"], "answer": 1},
        ],
        # Set 2
        [
            {"question": "Which function is used to read analog values?", "options": ["analogRead()", "digitalRead()", "analogWrite()", "readAnalog()"], "answer": 0},
            {"question": "What is the maximum value returned by analogRead() on Uno?", "options": ["255", "1023", "4095", "65535"], "answer": 1},
            {"question": "Which command sets pin 8 as input?", "options": ["pinMode(8, INPUT);", "digitalRead(8);", "digitalWrite(8, INPUT);", "setPin(8, INPUT);"], "answer": 0},
            {"question": "What is the use of 'Serial.available()'?", "options": ["Send data", "Check if data is available to read", "Clear serial buffer", "Set baud rate"], "answer": 1},
            {"question": "Which sensor detects light?", "options": ["LDR", "DHT11", "HC-SR04", "Relay"], "answer": 0},
            {"question": "What is the output voltage of Arduino Uno digital HIGH?", "options": ["0V", "3.3V", "5V", "12V"], "answer": 2},
            {"question": "Which function is used to output text to serial monitor?", "options": ["Serial.print()", "Serial.read()", "Serial.input()", "Serial.write()"], "answer": 0},
            {"question": "What is the use of a relay module?", "options": ["Measure temperature", "Switch high voltage devices", "Detect light", "Generate sound"], "answer": 1},
            {"question": "Which pin is PWM capable on Uno?", "options": ["2", "3", "4", "5V"], "answer": 1},
            {"question": "What is the use of 'tone()' function?", "options": ["Generate sound", "Read analog value", "Set pin mode", "Send serial data"], "answer": 0},
            {"question": "Which sensor is used for gas detection?", "options": ["LDR", "MQ-2", "DHT11", "BMP180"], "answer": 1},
            {"question": "What is the use of 'noTone()' function?", "options": ["Stop sound on pin", "Start PWM", "Read digital pin", "Set pin as output"], "answer": 0},
            {"question": "Which function is used to start the main program?", "options": ["main()", "setup()", "loop()", "start()"], "answer": 1},
            {"question": "What is the use of a potentiometer?", "options": ["Measure temperature", "Adjust resistance", "Detect light", "Switch relay"], "answer": 1},
            {"question": "Which command turns on an LED on pin 9?", "options": ["digitalWrite(9, HIGH);", "digitalRead(9);", "analogWrite(9, HIGH);", "pinMode(9, OUTPUT);"], "answer": 0},
            {"question": "What is the use of 'millis()' in Arduino?", "options": ["Delay program", "Return time since program started", "Set timer", "Reset Arduino"], "answer": 1},
            {"question": "Which function is used to read serial data?", "options": ["Serial.read()", "Serial.print()", "Serial.begin()", "Serial.write()"], "answer": 0},
            {"question": "What is the use of a jumper wire?", "options": ["Connect components", "Measure voltage", "Store charge", "Switch relay"], "answer": 0},
            {"question": "Which sensor is used for humidity measurement?", "options": ["DHT11", "LDR", "HC-SR04", "MQ-2"], "answer": 0},
            {"question": "What is the use of a capacitor?", "options": ["Store charge", "Limit current", "Switch relay", "Detect light"], "answer": 0},
        ],
        # Sets 3-25: For brevity, repeat set 1 and 2, but in production, fill with more unique questions
    ]
    # Fill up to 25 sets
    while len(question_bank) < 25:
        question_bank.append(question_bank[len(question_bank)%2])

    # Session state for quiz persistence
    if 'quiz_set' not in st.session_state:
        st.session_state.quiz_set = random.choice(question_bank).copy()
        random.shuffle(st.session_state.quiz_set)
        st.session_state.quiz_submitted = False
        st.session_state.quiz_answers = [None]*len(st.session_state.quiz_set)

    # New Quiz button (visible above the form)
    if st.button('New Quiz'):
        st.session_state.quiz_set = random.choice(question_bank).copy()
        random.shuffle(st.session_state.quiz_set)
        st.session_state.quiz_submitted = False
        st.session_state.quiz_answers = [None]*len(st.session_state.quiz_set)

    quiz_set = st.session_state.quiz_set
    quiz_form = st.form("quiz_form")
    user_answers = []
    for idx, q in enumerate(quiz_set):
        if st.session_state.quiz_submitted:
            # Show selected answer as disabled radio
            user_answers.append(st.session_state.quiz_answers[idx])
            quiz_form.radio(q["question"], q["options"], key=f"q{idx}", index=q["options"].index(st.session_state.quiz_answers[idx]) if st.session_state.quiz_answers[idx] in q["options"] else 0, disabled=True)
        else:
            ans = quiz_form.radio(q["question"], q["options"], key=f"q{idx}", index=q["options"].index(st.session_state.quiz_answers[idx]) if st.session_state.quiz_answers[idx] in q["options"] else 0 if st.session_state.quiz_answers[idx] else 0)
            user_answers.append(ans)
    submitted = quiz_form.form_submit_button("Submit Quiz")
    if submitted and not st.session_state.quiz_submitted:
        st.session_state.quiz_submitted = True
        st.session_state.quiz_answers = user_answers

    if st.session_state.quiz_submitted:
        st.subheader("Results:")
        score = 0
        for idx, q in enumerate(quiz_set):
            correct = q["options"][q["answer"]]
            user = st.session_state.quiz_answers[idx]
            if user == correct:
                st.success(f"Q{idx+1}: Correct! {q['question']}")
                score += 1
            else:
                st.error(f"Q{idx+1}: Wrong. {q['question']} (Correct: {correct})")
        st.info(f"Your Score: {score} / 20")

elif menu == "Arduino Projects":
    st.header("Common Real-time Arduino Projects & Steps")
    projects = [
        {"name": "Automatic Plant Watering System", "steps": [
            "Connect soil moisture sensor to Arduino.",
            "Connect relay module to control water pump.",
            "Write code to read soil moisture and activate pump when dry.",
            "Test and calibrate the system.",
            "Enclose electronics for safety."
        ]},
        {"name": "Home Automation with IR Remote", "steps": [
            "Connect IR receiver to Arduino.",
            "Connect relays to control appliances.",
            "Decode IR remote signals.",
            "Map remote buttons to appliance control.",
            "Test with different appliances."
        ]},
        {"name": "Weather Station", "steps": [
            "Connect DHT11/DHT22 sensor for temperature/humidity.",
            "Connect LCD display for output.",
            "Write code to read sensor and display data.",
            "Add data logging to SD card (optional)."
        ]},
        {"name": "Obstacle Avoidance Robot", "steps": [
            "Connect ultrasonic sensor and motors.",
            "Write code to measure distance and control motors.",
            "Test robot movement and avoidance logic.",
            "Tune speed and turning for best results."
        ]},
        {"name": "Smart Door Lock", "steps": [
            "Connect keypad and servo motor to Arduino.",
            "Write code to read keypad and control servo.",
            "Set up password logic.",
            "Test locking/unlocking with correct/incorrect codes."
        ]},
    ]
    for p in projects:
        st.subheader(p["name"])
        for idx, step in enumerate(p["steps"]):
            st.write(f"Step {idx+1}: {step}")
        st.markdown("---")

elif menu == "Flex/MQ2/Color Sensor Integration":
    st.header("Flex, MQ2 Gas, and Color Sensor Integration with Arduino")
    st.markdown("""
    ### 1. Flex Sensor Integration
    **Working Principle:** Resistance changes as the sensor bends.
    
    **Circuit Diagram:**
    """)
    st.image("https://i.imgur.com/0Qw1F7B.png", caption="Flex Sensor with Arduino (Voltage Divider)", width=350)
    st.markdown("""
    **Wiring:**
    - One end of flex sensor to 5V
    - Other end to analog pin (A0) and a 10kΩ resistor to GND
    
    **Arduino Code:**
    ```cpp
    void setup() {
      Serial.begin(9600);
    }
    void loop() {
      int flexValue = analogRead(A0);
      Serial.println(flexValue);
      delay(200);
    }
    ```
    **Integration Points:** Use the analog value to detect bend and trigger actions (e.g., robot finger, gesture).
    """)
    st.markdown("---")
    st.markdown("""
    ### 2. MQ2 Gas Sensor Integration
    **Working Principle:** Resistance changes in presence of gases (LPG, smoke, etc).
    
    **Circuit Diagram:**
    """)
    st.image("https://i.imgur.com/4Qw8QwA.png", caption="MQ2 Gas Sensor with Arduino", width=350)
    st.markdown("""
    **Wiring:**
    - VCC to 5V, GND to GND
    - AO (Analog Out) to A0 (for analog reading)
    - DO (Digital Out, optional) to digital pin
    
    **Arduino Code:**
    ```cpp
    void setup() {
      Serial.begin(9600);
    }
    void loop() {
      int gasValue = analogRead(A0);
      Serial.println(gasValue);
      delay(200);
    }
    ```
    **Integration Points:** Set a threshold to trigger buzzer/alert if gas detected.
    """)
    st.markdown("---")
    st.markdown("""
    ### 3. Color Sensor (TCS3200) Integration
    **Working Principle:** Converts color light intensity to frequency.
    
    **Circuit Diagram:**
    """)
    st.image("https://i.imgur.com/1Qw8QwA.png", caption="TCS3200 Color Sensor with Arduino", width=350)
    st.markdown("""
    **Wiring:**
    - VCC to 5V, GND to GND
    - S0-S3 to digital pins (e.g., 2-5)
    - OUT to digital pin (e.g., 6)
    
    **Arduino Code:**
    ```cpp
    #define S0 2
    #define S1 3
    #define S2 4
    #define S3 5
    #define sensorOut 6
    unsigned long duration;
    void setup() {
      pinMode(S0, OUTPUT); pinMode(S1, OUTPUT);
      pinMode(S2, OUTPUT); pinMode(S3, OUTPUT);
      pinMode(sensorOut, INPUT);
      Serial.begin(9600);
      digitalWrite(S0,HIGH); digitalWrite(S1,LOW); // Set frequency scaling
    }
    void loop() {
      // Red
      digitalWrite(S2,LOW); digitalWrite(S3,LOW);
      duration = pulseIn(sensorOut, LOW);
      Serial.print("R:"); Serial.print(duration);
      // Green
      digitalWrite(S2,HIGH); digitalWrite(S3,HIGH);
      duration = pulseIn(sensorOut, LOW);
      Serial.print(" G:"); Serial.print(duration);
      // Blue
      digitalWrite(S2,LOW); digitalWrite(S3,HIGH);
      duration = pulseIn(sensorOut, LOW);
      Serial.print(" B:"); Serial.println(duration);
      delay(500);
    }
    ```
    
    **Integration Points:** Use the RGB values to detect color and trigger actions (sorting, color-based logic).
    """)

elif menu == "DHT Sensor Integration":
    st.header("DHT11/DHT22 Sensor Integration with Arduino Uno (Tinkercad & IDE)")
    st.markdown("""
    ### 1. Circuit Diagram (Tinkercad/Real)
    """)
    st.image("https://i.imgur.com/6Qw1F7B.png", caption="DHT11 with Arduino Uno (Tinkercad/Real)", width=350)
    st.markdown("""
    **Wiring:**
    - DHT11 VCC to 5V
    - GND to GND
    - Data pin to digital pin 2 (with 10kΩ pull-up resistor to 5V)
    
    ### 2. Arduino IDE Code (using DHT library)
    ```cpp
    #include <DHT.h>
    #define DHTPIN 2
    #define DHTTYPE DHT11
    DHT dht(DHTPIN, DHTTYPE);
    void setup() {
      Serial.begin(9600);
      dht.begin();
    }
    void loop() {
      float h = dht.readHumidity();
      float t = dht.readTemperature();
      if (isnan(h) || isnan(t)) {
        Serial.println("Failed to read from DHT sensor!");
        return;
      }
      Serial.print("Humidity: "); Serial.print(h);
      Serial.print(" %  Temperature: "); Serial.print(t);
      Serial.println(" *C");
      delay(2000);
    }
    ```
    **Integration Points:** Use the temperature/humidity values for weather stations, automation, or IoT data upload.
    
    ### 3. Tinkercad Simulation Steps
    1. Go to [Tinkercad Circuits](https://www.tinkercad.com/circuits)
    2. Add Arduino Uno and DHT11 sensor from components
    3. Connect as per diagram above
    4. Paste the code in the code editor
    5. Start simulation and observe serial output
    
    **Note:** For DHT22, change `#define DHTTYPE DHT22` and wiring is the same.
    """)

elif menu == "Arduino Tutorials Blog":
    st.header("Arduino Tutorials Blog")
    st.markdown("""
    ### Getting Started with Arduino
    - Introduction to Arduino and its ecosystem
    - Setting up Arduino IDE
    - Writing your first sketch (Blink LED)
    - Uploading code to Arduino
    - Debugging basics
    
    ### Intermediate Tutorials
    - Reading analog and digital sensors
    - Using serial communication
    - PWM and controlling motors
    - Using libraries and shields
    
    ### Advanced Tutorials
    - IoT with Arduino (WiFi, MQTT, HTTP)
    - Data logging and visualization
    - Real-time control and automation
    - Integrating with cloud platforms
    
    For detailed step-by-step guides, visit [Arduino Official Tutorials](https://docs.arduino.cc/learn/).
    """)

# --- Ultrasonic Sensor Guide Page ---
elif menu == "Ultrasonic Sensor Guide":
    st.header("Ultrasonic Sensor (HC-SR04) Working & Arduino Integration")
    st.image("https://components101.com/sites/default/files/component_images/HC-SR04-Ultrasonic-Sensor.png", width=200)
    st.markdown("""
    **Working Principle:**
    - The HC-SR04 emits an ultrasonic pulse and measures the time taken for the echo to return.
    - Distance = (Time x Speed of Sound) / 2
    
    **Applications:** Obstacle avoidance, distance measurement, robotics.
    
    **Arduino Integration:**
    ```cpp
    #define TRIG 9
    #define ECHO 8
    long duration;
    int distance;
    void setup() {
      pinMode(TRIG, OUTPUT);
      pinMode(ECHO, INPUT);
      Serial.begin(9600);
    }
    void loop() {
      digitalWrite(TRIG, LOW); delayMicroseconds(2);
      digitalWrite(TRIG, HIGH); delayMicroseconds(10);
      digitalWrite(TRIG, LOW);
      duration = pulseIn(ECHO, HIGH);
      distance = duration * 0.034 / 2;
      Serial.println(distance);
      delay(500);
    }
    ```
    """)

# --- L293D Motor Driver Guide Page ---
elif menu == "L293D Motor Driver Guide":
    st.header("L293D Motor Driver: Working & Arduino Integration")
    st.image("https://components101.com/sites/default/files/component_images/L293D-IC.png", width=200)
    st.markdown("""
    **Working Principle:**
    - L293D is a dual H-Bridge motor driver IC, allows control of two DC motors in both directions.
    - Can drive small motors (up to 600mA per channel).
    
    **Applications:** Robotics, automation, motorized projects.
    
    **Arduino Integration:**
    ```cpp
    // Example: Control one DC motor
    #define ENA 9
    #define IN1 8
    #define IN2 7
    void setup() {
      pinMode(ENA, OUTPUT);
      pinMode(IN1, OUTPUT);
      pinMode(IN2, OUTPUT);
    }
    void loop() {
      digitalWrite(IN1, HIGH);
      digitalWrite(IN2, LOW);
      analogWrite(ENA, 200); // Speed control
      delay(2000);
      digitalWrite(IN1, LOW);
      digitalWrite(IN2, HIGH);
      delay(2000);
    }
    ```
    """)

# --- Sensor Working & Integration Page ---
elif menu == "Sensor Working & Integration":
    st.header("Sensor Working Principles & Arduino Integration")
    st.markdown("""
    #### DHT11/DHT22 (Temperature & Humidity)
    - **Working:** Uses a thermistor and capacitive humidity sensor.
    - **Application:** Weather stations, greenhouses.
    - **Arduino Integration:** Use DHT library, connect data pin to digital pin.
    
    #### LDR (Light Sensor)
    - **Working:** Resistance decreases with increasing light.
    - **Application:** Light meters, automatic lighting.
    - **Arduino Integration:** Connect in voltage divider, read analog pin.
    
    #### MQ-2 (Gas Sensor)
    - **Working:** Changes resistance in presence of gases.
    - **Application:** Gas leak detection.
    - **Arduino Integration:** Analog output to analog pin.
    
    #### Soil Moisture Sensor
    - **Working:** Measures resistance/conductivity in soil.
    - **Application:** Smart irrigation.
    - **Arduino Integration:** Analog output to analog pin.
    
    For more, see [Arduino Sensor Guides](https://docs.arduino.cc/learn/sensors/).
    """)

# --- Arduino Boards Comparison Page ---
elif menu == "Arduino Boards Comparison":
    st.header("Arduino Boards & NodeMCU Comparison")
    st.markdown("""
    | Board         | MCU         | Voltage | IO Pins | Comm | Special Features         |
    |--------------|-------------|---------|---------|------|-------------------------|
    | Uno          | ATmega328P  | 5V      | 14D/6A  | UART/I2C/SPI | Most common, shields |
    | Mega 2560    | ATmega2560  | 5V      | 54D/16A | UART/I2C/SPI | More IO, RAM         |
    | Nano         | ATmega328P  | 5V      | 14D/8A  | UART/I2C/SPI | Small, breadboard    |
    | Leonardo     | ATmega32u4  | 5V      | 20D/12A | UART/I2C/SPI | USB HID support      |
    | Due          | SAM3X8E     | 3.3V    | 54D/12A | UART/I2C/SPI | 32-bit, 3.3V only    |
    | NodeMCU      | ESP8266     | 3.3V    | 11D/1A  | UART/I2C/SPI/WiFi | WiFi, IoT      |
    | ESP32 Dev    | ESP32       | 3.3V    | 30+     | UART/I2C/SPI/WiFi/BLE | Dual core, BLE |
    
    **When to choose which?**
    - **Uno/Nano:** Beginners, most shields, basic projects.
    - **Mega:** Many IOs, complex projects.
    - **NodeMCU/ESP32:** IoT, WiFi/BLE, cloud.
    - **Due:** 32-bit, advanced computation, 3.3V sensors.
    
    **Communication Types:** UART (Serial), I2C, SPI, WiFi, Bluetooth, Zigbee, RF.
    """)

# --- Arduino Concepts Page ---
elif menu == "Arduino Concepts":
    st.header("Core Arduino Concepts")
    st.markdown("""
    - **Interrupts:** Pause main code to handle events (attachInterrupt, ISR).
    - **I/O:** Digital/analog input/output, pinMode, digitalRead/Write, analogRead/Write.
    - **Flashing:** Uploading code to microcontroller.
    - **Clock:** System clock, millis(), micros(), timing.
    - **Bootloader:** Small program to load sketches.
    - **Watchdog Timer:** Resets MCU if code hangs.
    - **Power:** 5V/3.3V, VIN, battery, USB.
    - **Serial Monitor:** Debugging, communication.
    - **Libraries:** Pre-written code to extend functionality (e.g., Wire, SPI, Servo).
    - **Data Types:** int, float, char, String, array, struct.
    - **Functions:** Setup and loop functions, custom functions.
    - **Control Structures:** if, for, while, switch-case.
    - **Error Handling:** Common errors, debugging tips.
    For more, see [Arduino Reference](https://www.arduino.cc/reference/en/).
    """)

# --- Starter Codes & Programming Page ---
elif menu == "Starter Codes & Programming":
    st.header("Starter Codes & Arduino Programming")
    st.markdown("""
    **Blink LED:**
    ```cpp
    void setup() { pinMode(13, OUTPUT); }
    void loop() { digitalWrite(13, HIGH); delay(500); digitalWrite(13, LOW); delay(500); }
    ```
    **Read Analog Sensor:**
    ```cpp
    void setup() { Serial.begin(9600); }
    void loop() { int val = analogRead(A0); Serial.println(val); delay(500); }
    ```
    **Button Input:**
    ```cpp
    void setup() { pinMode(2, INPUT_PULLUP); }
    void loop() { if(digitalRead(2)==LOW) { /* pressed */ } }
    ```
    **Motor Control:**
    ```cpp
    void setup() { pinMode(9, OUTPUT); }
    void loop() { analogWrite(9, 128); }
    ```
    For more, see [Arduino Language Reference](https://www.arduino.cc/reference/en/).
    """)

# --- Electronics Concepts Page ---
elif menu == "Electronics Concepts":
    st.header("Electronics Concepts for Arduino & Circuits")
    st.markdown("""
    - **GND & VCC:** Ground and supply voltage.
    - **Pull-up/Pull-down Resistors:** Used to set default logic level on input pins.
    - **Motor Driver:** ICs like L293D, used to control motors.
    - **Voltage Divider:** Two resistors to scale down voltage.
    - **Decoupling Capacitor:** Reduces noise, stabilizes voltage.
    - **Transistor as Switch:** Used to control high current loads.
    - **Relay:** Electrically operated switch for high voltage.
    - **Optocoupler:** Isolates sections of circuit.
    - **Breadboard:** For prototyping without soldering.
    - **PCB:** For permanent circuits.
    For more, see [All About Circuits](https://www.allaboutcircuits.com/).
    """)

# --- Serial Protocols (SPI/I2C/UART) Page ---
elif menu == "Serial Protocols (SPI/I2C/UART)":
    st.header("Serial Protocols: SPI, I2C, UART")
    st.markdown("""
    | Protocol | Wires | Speed      | Addressing | Use Case                |
    |----------|-------|------------|------------|-------------------------|
    | UART     | 2     | 9600+ bps  | No         | Serial comm, debug      |
    | I2C      | 2     | 100k-400kb | Yes        | Many sensors, RTC, LCD  |
    | SPI      | 4     | 1-10+ Mbps | No         | SD card, displays       |
    
    **Comparison:**
    - **UART:** Simple, point-to-point.
    - **I2C:** Multiple devices, addressable, slower.
    - **SPI:** Fast, multiple slaves, more wires.
    
    **When to use:**
    - **I2C:** Many sensors, less wiring.
    - **SPI:** High speed, SD cards, displays.
    - **UART:** Simple serial, debug, GPS.
    
    **I2C vs Non-I2C Sensors:**
    - I2C sensors connect via SCL/SDA, can share bus.
    - Non-I2C sensors use analog/digital pins, more wiring.
    For more, see [Arduino Communication](https://docs.arduino.cc/learn/communication/).
    """)

# --- Common Mistakes & Best Practices Page ---
elif menu == "Common Mistakes & Best Practices":
    st.header("Common Mistakes, Dos & Don'ts (Arduino & Electronics)")
    st.markdown("""
    - Not using current limiting resistors for LEDs.
    - Powering 5V devices from 3.3V boards (and vice versa).
    - Not connecting GNDs together.
    - Floating input pins (use pull-up/down resistors).
    - Overloading pins (max 40mA per pin on Uno).
    - Not debouncing buttons.
    - Not using external power for motors.
    - Not reading datasheets.
    - Not using common ground in multi-board setups.
    - Not isolating high voltage circuits.
    - Not checking wiring before powering up.
    - Not using proper code structure (setup/loop).
    - Not using comments/documentation.
    """)

# --- Productization Steps Page ---
elif menu == "Productization Steps":
    st.header("Converting Arduino Project to Product: Steps")
    st.markdown("""
    1. **Prototype:** Build and test on breadboard.
    2. **Refine:** Optimize code, reduce power, improve reliability.
    3. **Design PCB:** Move from breadboard to PCB.
    4. **Enclosure:** Design case for protection and usability.
    5. **Compliance:** Check certifications (EMI, safety).
    6. **Manufacturing:** Source components, assembly.
    7. **Testing:** Functional and stress testing.
    8. **Documentation:** User manual, code comments.
    9. **Support:** Plan for updates, bug fixes.
    For more, see [Arduino to Product](https://www.arduino.cc/pro/).
    """)

# --- Applications & Advanced Projects Page ---
elif menu == "Applications & Advanced Projects":
    st.header("Applications & Advanced Arduino Projects")
    st.markdown("""
    - **Image Processing:** Use Arduino with camera modules (limited), or interface with Raspberry Pi for advanced vision.
    - **PID/PI/PD Controllers:** Implement control algorithms for robotics, temperature, motors.
    - **RC Car Development:** Wireless control using RF, Bluetooth, WiFi.
    - **IoT Applications:** Home automation, smart agriculture, health monitoring.
    - **Industrial Automation:** Sensors, actuators, data logging.
    - **Instrumentation:** Data acquisition, signal processing.
    - **Wearables:** Fitness trackers, health monitors.
    - **Communication:** Bluetooth, Zigbee, WiFi, LoRa, GSM.
    - **STEM Education:** Learning, teaching, prototyping.
    For more, see [Arduino Project Hub](https://projecthub.arduino.cc/).
    """)

# --- Raspberry Pi Full Guide Page ---
elif menu == "Raspberry Pi Full Guide":
    st.header("Raspberry Pi From Scratch – Sensors, IoT, Image Processing & Projects")
    sections = [
        "Agenda",
        "Hardware Overview",
        "Version Comparison",
        "Flash the OS",
        "First Login & Updates",
        "Essential Linux Commands",
        "Python Environment",
        "GPIO Numbering",
        "Safer Abstraction: gpiozero",
        "Digital Output (Blink LED)",
        "Digital Input (Button)",
        "Edge Detection + Debounce",
        "PWM (LED Fading)",
        "Servo Control",
        "Analog Inputs (MCP3008/ADS1115)",
        "I2C Sensor (BME280)",
        "UART Basics",
        "PLC & PID Control",
        "IoT & MQTT Integration",
        "Image Processing (OpenCV)",
        "Mini Projects",
        "Cheat Sheet & Helper Snippets",
        "Best Practices / Do & Don'ts",
        "Troubleshooting & Resources"
    ]
    section = st.selectbox("Section", sections)
    if section == "Agenda":
        st.markdown("""
1. Hardware & OS Setup
2. Linux & GPIO Fundamentals
3. Digital I/O & Timing
4. Analog Sensing (MCP3008 / ADS1115)
5. Buses: I2C, SPI, UART
6. PWM, Servo & Control
7. Raspberry Pi as PLC & PID Control
8. IoT & MQTT Integration
9. Image Processing (OpenCV Focus)
10. Mini Projects & Ideas
11. Cheat Sheet & Helper Snippets
12. Best Practices / Do & Don'ts
13. Model/Version Comparison
14. Troubleshooting & Resources
        """)
    elif section == "Hardware Overview":
        st.markdown("""
**Typical Kit:**
- Raspberry Pi 3 Model B/B+
- microSD (>=16GB, Class 10)
- 5V 2.5A PSU
- HDMI cable / headless setup
- Breadboard, GPIO ribbon (optional)
- LEDs, buttons, resistors (220Ω, 10kΩ)
- Sensors: DHT22, BME280, HC-SR04, LDR, MCP3008 ADC, servo, camera module, PIR
        """)
    elif section == "Version Comparison":
        st.markdown("""
| Feature | Pi 3B+ | Pi 4 | Pi 5 |
|---------|--------|------|------|
| CPU | 1.4GHz Quad Cortex-A53 | 1.5GHz Cortex-A72 | 2.4GHz Cortex-A76 | 
| RAM | 1GB | 2–8GB | 4–8GB |
| USB | 4x2.0 | 2x2.0 + 2x3.0 | 2x2.0 + 2x3.0 |
| Video | 1080p | Dual 4K | Dual 4K (better) |
| M.2 (direct) | No | No | Via PCIe FPC |
| Power | 5V microUSB | 5V USB-C | 5V USB-C (PD) |
| Ideal Use | Learning, light IoT | Desktop, heavier ML | High perf + vision |

Notes: Code examples identical across versions unless performance-critical.
        """)
    elif section == "Flash the OS":
        st.markdown("""
1. Download Raspberry Pi Imager (rpi-imager)
2. Choose Raspberry Pi OS (Lite for headless, Full for desktop)
3. Configure (Ctrl+Shift+X): hostname, SSH, Wi-Fi, locale
4. Flash & insert microSD
5. Power on; find IP via router or `raspberrypi.local`
        """)
    elif section == "First Login & Updates":
        st.markdown("""
```bash
ssh pi@raspberrypi.local       # default user 'pi'
passwd                         # change password
sudo apt update && sudo apt full-upgrade -y
sudo raspi-config              # enable: SSH, I2C, SPI, Camera, Serial
```
        """)
    elif section == "Essential Linux Commands":
        st.markdown("""
```bash
ls, cd, pwd, mkdir, rm -r, cp, mv
nano file.py        # quick edit
sudo systemctl status <svc>
free -h; df -h      # memory & disk
vcgencmd measure_temp
htop                # install: sudo apt install -y htop
```
        """)
    elif section == "Python Environment":
        st.markdown("""
**Setting Up Python on Raspberry Pi:**
- Python 3 is pre-installed on Raspberry Pi OS.
- Use `python3` and `pip3` for running scripts and installing packages.
- Recommended: Create a virtual environment for projects.
```bash
sudo apt install python3-pip python3-venv
python3 -m venv myenv
source myenv/bin/activate
```
Install libraries: `pip3 install numpy pandas matplotlib gpiozero`
        """)
    elif section == "GPIO Numbering":
        st.markdown("""
**GPIO Numbering on Raspberry Pi:**
- Two numbering schemes: BOARD (physical pin numbers) and BCM (Broadcom SoC numbering).
- Most libraries (RPi.GPIO, gpiozero) use BCM by default.
```python
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)  # or GPIO.BOARD

```
Refer to a GPIO pinout diagram for your Pi model.
        """)
    elif section == "Safer Abstraction: gpiozero":
        st.markdown("""
**gpiozero Library:**
- High-level Python library for controlling GPIO devices easily.
- Handles setup/cleanup and errors for you.
```python
from gpiozero import LED, Button
led = LED(18)
button = Button(17)
led.on()
button.when_pressed = led.toggle
```
See: https://gpiozero.readthedocs.io/
        """)
    elif section == "Digital Output (Blink LED)":
        st.markdown("""
**Blinking an LED (Python):**
```python
import RPi.GPIO as GPIO
import time
GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.OUT)
for i in range(10):
    GPIO.output(18, GPIO.HIGH)
    time.sleep(0.5)
    GPIO.output(18, GPIO.LOW)
    time.sleep(0.5)
GPIO.cleanup()
```
        """)
    elif section == "Digital Input (Button)":
        st.markdown("""
**Reading a Button (Python):**
```python
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
if GPIO.input(17):
    print("Button not pressed")
else:
    print("Button pressed")
GPIO.cleanup()
```
        """)
    elif section == "Edge Detection + Debounce":
        st.markdown("""
**Edge Detection & Debouncing:**
- Use GPIO event detection to respond to button presses/releases.
- Debouncing prevents false triggers from noisy signals.
```python
import RPi.GPIO as GPIO
def callback(channel):
    print("Button event!")
GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.add_event_detect(17, GPIO.FALLING, callback=callback, bouncetime=200)
```
        """)
    elif section == "PWM (LED Fading)":
        st.markdown("""
**PWM for LED Fading:**
```python
import RPi.GPIO as GPIO
import time
GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.OUT)
pwm = GPIO.PWM(18, 1000)
pwm.start(0)
for dc in range(0, 101, 5):
    pwm.ChangeDutyCycle(dc)
    time.sleep(0.05)
pwm.stop()
GPIO.cleanup()
```
        """)
    elif section == "Servo Control":
        st.markdown("""
**Controlling a Servo Motor:**
```python
from gpiozero import Servo
from time import sleep
servo = Servo(17)
servo.min()
sleep(1)
servo.max()
sleep(1)
```
        """)
    elif section == "Analog Inputs (MCP3008/ADS1115)":
        st.markdown("""
**Reading Analog Sensors (MCP3008/ADS1115):**
- Use SPI/I2C ADC chips to read analog sensors.
```python
import spidev
spi = spidev.SpiDev()
spi.open(0,0)
def read_adc(ch):
    r = spi.xfer2([1, (8+ch)<<4, 0])
    return ((r[1]&3)<<8) + r[2]
val = read_adc(0)
print(val)
```
        """)
    elif section == "I2C Sensor (BME280)":
        st.markdown("""
**Reading I2C Sensors (BME280):**
```python
import smbus2
bus = smbus2.SMBus(1)
addr = 0x76
chip_id = bus.read_byte_data(addr, 0xD0)
print(f"Chip ID: {chip_id}")
```
        """)
    elif section == "UART Basics":
        st.markdown("""
**UART Serial Communication:**
- Use `/dev/serial0` for UART on Pi.
```python
import serial
ser = serial.Serial('/dev/serial0', 9600)
ser.write(b'Hello Pi')
data = ser.readline()
print(data)
ser.close()
```
        """)
    elif section == "PLC & PID Control":
        st.markdown("""
**PLC & PID Control on Pi:**
- Use Python for simple PLC logic and PID control.
- Libraries: `simple-pid`, `pylogix` (for PLC comms)
```python
from simple_pid import PID
pid = PID(1, 0.1, 0.05, setpoint=20)
output = pid(18)  # Example process variable
print(output)
```
        """)
    elif section == "IoT & MQTT Integration":
        st.markdown("""
**IoT & MQTT Integration:**
- Use `paho-mqtt` for MQTT communication.
```python
import paho.mqtt.client as mqtt
client = mqtt.Client()
client.connect('broker.hivemq.com', 1883)
client.publish('test/topic', 'Hello from Pi')
client.disconnect()
```
        """)
    elif section == "Image Processing (OpenCV)":
        st.markdown("""
**Image Processing with OpenCV:**
```python
import cv2
img = cv2.imread('image.jpg')
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
cv2.imshow('Gray', gray)
cv2.waitKey(0)
cv2.destroyAllWindows()
```
        """)
    elif section == "Mini Projects":
        st.markdown("""
**Mini Project Ideas:**
- Temperature logger with BME280
- Motion-activated camera
- Home automation with relays
- IoT weather station
        """)
    elif section == "Cheat Sheet & Helper Snippets":
        st.markdown("""
**Cheat Sheet & Helper Snippets:**
- See the 'Starters & Cheatsheet' page for quick code.
- Use `gpiozero` for easy device control.
- Use `crontab` for scheduled tasks.
        """)
    elif section == "Best Practices / Do & Don'ts":
        st.markdown("""
**Best Practices:**
- Always shut down Pi safely (`sudo shutdown -h now`).
- Use resistors with LEDs.
- Avoid powering motors directly from Pi.
- Use virtual environments for Python projects.
**Do & Don'ts:**
- Do: Backup SD card, keep system updated.
- Don't: Pull power without shutdown, short GPIO pins.
        """)
    elif section == "Troubleshooting & Resources":
        st.markdown("""
**Troubleshooting:**
- Pi won't boot: Check power, SD card, HDMI.
- No network: Check Wi-Fi config, try Ethernet.
- GPIO errors: Check pin numbering, permissions.
**Resources:**
- Official docs: https://www.raspberrypi.com/documentation/
- Forums: https://forums.raspberrypi.com/
- Pinout: https://pinout.xyz/
        """)
    # ...continue for each section, splitting your markdown content as needed...

# --- Raspberry Pi Starters & Cheatsheet Page ---
elif menu == "Raspberry Pi Starters & Cheatsheet":
    st.header("Raspberry Pi Starters & Python Cheatsheet")
    st.markdown("""
**Getting Started:**
- Use Raspberry Pi Imager to flash Raspberry Pi OS to SD card.
- Default login: pi/raspberry
- Update system: `sudo apt update && sudo apt upgrade`
- Enable interfaces: `sudo raspi-config` (I2C, SPI, Serial, Camera, etc.)

**Python GPIO Setup:**
```python
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.OUT)
GPIO.output(18, GPIO.HIGH)
GPIO.cleanup()
```

**Read Digital Input:**
```python
GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
if GPIO.input(17):
    print("HIGH")
else:
    print("LOW")
```

**Read Analog Sensor (using MCP3008):**
```python
import spidev
spi = spidev.SpiDev()
spi.open(0,0)
def read_adc(ch):
    r = spi.xfer2([1, (8+ch)<<4, 0])
    return ((r[1]&3)<<8) + r[2]
val = read_adc(0)
print(val)
```

**Useful Commands:**
- `ifconfig`, `iwconfig`, `lsusb`, `i2cdetect -y 1`
- `sudo reboot`, `sudo shutdown -h now`

**Common Libraries:**
- `RPi.GPIO`, `gpiozero`, `spidev`, `smbus2`, `picamera`, `opencv-python`
    """)

# --- Raspberry Pi Sensor Integrations Page ---
elif menu == "Raspberry Pi Sensor Integrations":
    st.header("Raspberry Pi Sensor Integrations & Scenarios")
    st.markdown("""
**Digital Sensor Example (PIR Motion):**
```python
import RPi.GPIO as GPIO
import time
GPIO.setmode(GPIO.BCM)
GPIO.setup(23, GPIO.IN)
try:
    while True:
        if GPIO.input(23):
            print("Motion detected!")
        time.sleep(0.1)
finally:
    GPIO.cleanup()
```

**Analog Sensor Example (MCP3008 + Potentiometer):**
```python
# See MCP3008 code in cheatsheet above
```

**I2C Sensor Example (BMP280):**
```python
import smbus2
bus = smbus2.SMBus(1)
addr = 0x76
chip_id = bus.read_byte_data(addr, 0xD0)
print(f"Chip ID: {chip_id}")
```

**Scenario: Integrating Both Analog & Digital Sensors**
- Use MCP3008 for analog sensors, direct GPIO for digital.
- Read both in the same loop, log to file or send to cloud.
    """)

elif menu == "Raspberry Pi GPS Sensor Integration (I2C)":
    st.header("Raspberry Pi GPS Sensor Integration (I2C)")
    st.markdown('''
This page shows how to integrate a GPS module that supports I2C (for example, some u-blox modules or Adafruit breakout boards with I2C support).

Hardware:
- Raspberry Pi with I2C enabled
- GPS module with I2C (check your module; many default to UART)
- Jumper wires

Wiring (typical):
- GPS SDA -> Pi SDA (GPIO2, pin 3)
- GPS SCL -> Pi SCL (GPIO3, pin 5)
- GPS VCC -> 3.3V (or 5V if module requires; check datasheet)
- GPS GND -> GND

Enable I2C:
```bash
sudo raspi-config
# Interfacing Options -> I2C -> Enable
sudo reboot
```
Confirm device appears:
```bash
i2cdetect -y 1
# Typical u-blox I2C address: 0x42
```

Simple I2C read example (reads raw NMEA bytes exposed over I2C):
```python
import time
try:
    import smbus2
except Exception:
    smbus2 = None

GPS_ADDR = 0x42  # common for u-blox

def read_raw_i2c():
    if smbus2 is None:
        print('Install smbus2: pip3 install smbus2')
        return
    bus = smbus2.SMBus(1)
    buffer = bytearray()
    try:
        while True:
            # read block; adjust length if needed
            data = bus.read_i2c_block_data(GPS_ADDR, 0xFF, 32)
            for b in data:
                if b == 0:
                    continue
                buffer.append(b)
                if b == 0x0A:  # newline -> likely end of NMEA sentence
                    line = buffer.decode(errors='ignore').strip()
                    buffer.clear()
                    if line.startswith('$'):
                        print(line)
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

# Parsing example using pynmea2
def parse_with_pynmea2(line):
    try:
        import pynmea2
    except Exception:
        st.warning('Install pynmea2 for parsing: pip3 install pynmea2')
        return
    try:
        msg = pynmea2.parse(line)
        if hasattr(msg, 'latitude') and hasattr(msg, 'longitude'):
            st.write(f"Lat: {msg.latitude}, Lon: {msg.longitude}")
        else:
            st.write(repr(msg))
    except Exception as e:
        st.write('Parse error:', e)
        
st.subheader('Quick demo (read raw NMEA over I2C)')
if st.button('Start I2C Read (console output)'):
    st.write('This will run in your console where Streamlit was started; use the example script locally on the Pi for live reads.')
    st.write('See code example above: use read_raw_i2c() in a separate script or a Python REPL on the Pi.')

st.markdown(```
Advanced: u-blox UBX parsing (binary) and configuration
- Use `pyubx2` to send UBX messages and parse binary protocols.
- Many modules allow switching between UART/I2C and configuring update rate, nav settings, etc.
''')

st.subheader('Standalone example scripts to copy to your Pi')
st.code('''import smbus2, time

GPS_ADDR = 0x42
bus = smbus2.SMBus(1)
buf = bytearray()
try:
    while True:
        data = bus.read_i2c_block_data(GPS_ADDR, 0xFF, 32)
        for b in data:
            if b == 0: continue
            buf.append(b)
            if b == 0x0A:
                line = buf.decode(errors='ignore').strip()
                buf.clear()
                if line.startswith('$'):
                    print(line)
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
''', language='python')

st.code('''
#!/usr/bin/env python3
# i2c_gps_parse.py - read + parse with pynmea2
import smbus2, time
import pynmea2

GPS_ADDR = 0x42
bus = smbus2.SMBus(1)
buf = bytearray()
try:
    while True:
        data = bus.read_i2c_block_data(GPS_ADDR, 0xFF, 32)
        for b in data:
            if b == 0: continue
            buf.append(b)
            if b == 0x0A:
                line = buf.decode(errors='ignore').strip()
                buf.clear()
                if line.startswith('$'):
                    try:
                        msg = pynmea2.parse(line)
                        if hasattr(msg, 'latitude'):
                            print('Lat:', msg.latitude, 'Lon:', msg.longitude)
                        else:
                            print(repr(msg))
                    except Exception:
                        print('parse error for', line)
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
''', language='python')

st.markdown('''
Notes & Troubleshooting:
- If you get no data, verify I2C address with `i2cdetect -y 1`.
- Some modules default to UART; consult the module datasheet to enable I2C or use the UART pins (/dev/serial0) instead.
- For advanced configuration (rate, enabling SBAS/RTK, power saving), use `pyubx2` to craft UBX messages.
''')

# End of GPS section
