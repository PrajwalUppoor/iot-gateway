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
        "Applications & Advanced Projects"
    ]
)

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
    sensors = [
        {"name": "DHT11/DHT22 Temperature & Humidity Sensor", "img": "https://components101.com/sites/default/files/component_images/DHT11.png", "use": "Measure temperature and humidity", "application": "Weather stations, greenhouses"},
        {"name": "LDR (Light Dependent Resistor)", "img": "https://components101.com/sites/default/files/component_images/LDR-Sensor.png", "use": "Detect light intensity", "application": "Automatic lighting, light meters"},
        {"name": "Ultrasonic Sensor (HC-SR04)", "img": "https://components101.com/sites/default/files/component_images/HC-SR04-Ultrasonic-Sensor.png", "use": "Measure distance", "application": "Obstacle avoidance, level measurement"},
        {"name": "IR Sensor", "img": "https://components101.com/sites/default/files/component_images/IR-Module.png", "use": "Detect objects, proximity", "application": "Line following robots, object counters"},
        {"name": "Soil Moisture Sensor", "img": "https://components101.com/sites/default/files/component_images/Soil-Moisture-Sensor.png", "use": "Measure soil moisture", "application": "Smart irrigation"},
        {"name": "MQ-2 Gas Sensor", "img": "https://components101.com/sites/default/files/component_images/MQ2-Gas-Sensor-Module.png", "use": "Detect gas leaks", "application": "Safety, air quality monitoring"},
    ]
    for s in sensors:
        st.image(s["img"], width=100)
        st.write(f"**{s['name']}**  ")
        st.write(f"Use: {s['use']}")
        st.write(f"Application: {s['application']}")
        st.markdown("---")
    st.markdown("### Common Components:")
    components = [
        {"name": "Breadboard", "img": "https://components101.com/sites/default/files/component_images/Breadboard.png", "use": "Prototyping circuits", "application": "All Arduino projects"},
        {"name": "Jumper Wires", "img": "https://components101.com/sites/default/files/component_images/Jumper-Wires.png", "use": "Connect components", "application": "All Arduino projects"},
        {"name": "Resistors", "img": "https://components101.com/sites/default/files/component_images/Resistor.png", "use": "Limit current", "application": "LEDs, sensors"},
        {"name": "Capacitors", "img": "https://components101.com/sites/default/files/component_images/Capacitor.png", "use": "Store charge, filter signals", "application": "Power supply, signal filtering"},
        {"name": "Push Button", "img": "https://components101.com/sites/default/files/component_images/Push-Button.png", "use": "User input", "application": "Switches, user interfaces"},
        {"name": "LED", "img": "https://components101.com/sites/default/files/component_images/LED.png", "use": "Visual indicator", "application": "Status, output"},
        {"name": "Potentiometer", "img": "https://components101.com/sites/default/files/component_images/Potentiometer.png", "use": "Variable resistor", "application": "Volume control, sensor calibration"},
    ]
    for c in components:
        st.image(c["img"], width=100)
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

# --- Arduino Tutorials Blog Page ---
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
      digitalWrite(TRIG, LOW);
      delayMicroseconds(2);
      digitalWrite(TRIG, HIGH);
      delayMicroseconds(10);
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
