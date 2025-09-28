import streamlit as st
import sqlite3
import bcrypt
import pandas as pd
from datetime import date
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv

# ------------------ Load environment variables ------------------
load_dotenv()
EMAIL = os.getenv("EDUNET_EMAIL")
EMAIL_PASSWORD = os.getenv("EDUNET_EMAIL_PASSWORD")

# ------------------ Database Functions ------------------
DB_FILE = "tasks.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task TEXT,
            due_date DATE,
            priority TEXT DEFAULT 'Medium',
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

def register_user(username, email, password):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    if cur.fetchone():
        conn.close()
        return False
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    cur.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, hashed))
    conn.commit()
    conn.close()
    return True

def login_user(email, password):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    user = cur.fetchone()
    conn.close()
    if user and bcrypt.checkpw(password.encode(), user["password"]):
        return (user["id"], user["username"], user["email"])
    return None

# ------------------ Upgrade old DB ------------------
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()
try: cur.execute("ALTER TABLE tasks ADD COLUMN due_date DATE")
except: pass
try: cur.execute("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'Medium'")
except: pass
try: cur.execute("ALTER TABLE tasks ADD COLUMN status TEXT DEFAULT 'Pending'")
except: pass
conn.commit(); conn.close()

# ------------------ Initialize ------------------
create_tables()
if "user" not in st.session_state: st.session_state.user = None

st.title("📚 Smart Study Planner")

# ------------------ Helper Functions ------------------
def update_overdue_tasks(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    today = date.today()
    cur.execute("""
        UPDATE tasks
        SET status='Overdue'
        WHERE user_id=? AND status='Pending' AND due_date < ?
    """, (user_id, today))
    conn.commit()
    conn.close()

def display_tasks(df, user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    for idx, row in df.iterrows():
        cols = st.columns([4,1,1])
        due_str = str(row['due_date']) if pd.notna(row['due_date']) else "No due date"
        cols[0].write(f"**{row['task']}** | Due: {due_str} | Priority: {row['priority']} | Status: {row['status']}")

        # Complete button
        if row['status'] != "Completed":
            if cols[1].button("✅ Complete", key=f"comp_{row['id']}"):
                cur.execute("UPDATE tasks SET status=? WHERE id=? AND user_id=?", 
                            ("Completed", row['id'], user_id))
                conn.commit()
                st.rerun()

        # Delete button
        if cols[2].button("🗑 Delete", key=f"del_{row['id']}"):
            cur.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (row['id'], user_id))
            conn.commit()
            st.rerun()
    conn.close()

# ------------------ Login/Register ------------------
if st.session_state.user is None:
    choice = st.sidebar.selectbox("Login / Register", ["Login", "Register"])
    if choice == "Register":
        username = st.text_input("Username", key="reg_username")
        email = st.text_input("Email", key="reg_email")
        password = st.text_input("Password", type="password", key="reg_password")
        if st.button("Register", key="register_button"):
            if register_user(username, email, password):
                st.success("Registered successfully! Please log in.")
            else:
                st.error("User already exists.")
    elif choice == "Login":
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", key="login_button"):
            user = login_user(email, password)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid login.")

# ------------------ Main App ------------------
else:
    st.sidebar.success(f"Welcome, {st.session_state.user[1]}!")
    user_id = st.session_state.user[0]
    update_overdue_tasks(user_id)

    # Add Task
    st.subheader("➕ Add New Task")
    task = st.text_input("Task", key="new_task")
    due_date = st.date_input("Due Date", key="new_due_date")
    priority = st.selectbox("Priority", ["High", "Medium", "Low"], key="new_priority")
    if st.button("Add Task", key="add_task_btn"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO tasks (user_id, task, due_date, priority, status) VALUES (?, ?, ?, ?, ?)",
                    (user_id, task, due_date, priority, "Pending"))
        conn.commit()
        conn.close()
        st.success("Task added!")
        st.rerun()

    # Display Tasks
    st.subheader("📝 Your Tasks")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE user_id=?", (user_id,))
    tasks = cur.fetchall()
    df = pd.DataFrame(tasks, columns=["id", "user_id", "task", "due_date", "priority", "status"])
    conn.close()

    if not df.empty:
        df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce')
        status_filter = st.selectbox("Filter by Status", ["All", "Pending", "Completed", "Overdue"], key="status_filter")
        df_filtered = df if status_filter=="All" else df[df['status']==status_filter]
        display_tasks(df_filtered, user_id)

        # Pie Chart
        st.subheader("📊 Task Status Overview")
        status_counts = df["status"].value_counts()
        fig1, ax1 = plt.subplots()
        ax1.pie(status_counts, labels=status_counts.index, autopct="%1.1f%%")
        ax1.set_title("Task Completion Status")
        st.pyplot(fig1)

        # Bar Chart
        st.subheader("📈 Tasks by Priority & Status")
        fig2 = px.bar(df, x="priority", color="status", barmode="group", title="Priority vs Status")
        st.plotly_chart(fig2)

        # Export CSV
        st.subheader("⬇ Export Tasks")
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Task List as CSV", csv, "study_tasks.csv", "text/csv")

        # Send Email
        st.subheader("📧 Send Tasks to Email")
        if st.button("Send My Tasks to Email"):
            recipient_email = st.session_state.user[2]
            body = df.to_string(index=False)
            msg = MIMEText(body)
            msg["Subject"] = "Your Study Tasks"
            msg["From"] = EMAIL
            msg["To"] = recipient_email
            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(EMAIL, EMAIL_PASSWORD)
                    server.sendmail(EMAIL, recipient_email, msg.as_string())
                st.success("Tasks sent to your email!")
            except Exception as e:
                st.error(f"Email failed: {e}")
    else:
        st.info("No tasks yet!")

    # Footer
    st.markdown("""
    <style>
    .footer {
        text-align: center;
        font-size: 14px;
        color: white;
        background-color: #4B4B4B;
        padding: 10px;
        border-radius: 5px;
        margin-top: 20px;
    }
    </style>
    <div class="footer">
        Developed by MITTAMEEDI GOWTHAMI | Email: <a href="mailto:mittameedigowthami124@gmail.com" style="color: white;">mittameedigowthami124@gmail.com</a> | MGIT - ECE | Smart Study Planner 2025
    </div>
    """, unsafe_allow_html=True)
