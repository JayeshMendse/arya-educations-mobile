import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import time
from datetime import datetime, timedelta
import json
import os
import re
from typing import Dict, List, Optional, Tuple
import base64
from io import BytesIO
import requests

# =============================================================================
# CONFIGURATION AND SETUP
# =============================================================================

# App Configuration
APP_CONFIG = {
    'app_name': 'Arya Educations',
    'tagline': 'Learn, Grow, Succeed',
    'max_video_size': 100 * 1024 * 1024,  # 100MB
    'session_timeout': 30,  # minutes
    'auto_logout_time': 1800,  # 30 minutes in seconds
}

# Database Configuration
DB_FILE = 'tutorial_app.db'

# =============================================================================
# DATABASE INITIALIZATION AND UTILITY FUNCTIONS
# =============================================================================

def init_database():
    """Initialize SQLite database with all required tables"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Stream Master Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stream_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stream_id TEXT UNIQUE NOT NULL,
            stream_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Class Master Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS class_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id TEXT UNIQUE NOT NULL,
            class_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Subject Master Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subject_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id TEXT UNIQUE NOT NULL,
            subject_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Chapter Master Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chapter_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id TEXT UNIQUE NOT NULL,
            chapter_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Admin Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Students Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            college_name TEXT,
            address_1 TEXT,
            address_2 TEXT,
            address_3 TEXT,
            address_4 TEXT,
            city TEXT,
            state TEXT,
            pin_code TEXT,
            dob DATE,
            stream_id TEXT,
            class_id TEXT,
            mobile_no TEXT UNIQUE NOT NULL,
            video_enabled BOOLEAN DEFAULT 1,
            password_hash,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            otp_code TEXT,
            otp_expiry TIMESTAMP,
            FOREIGN KEY (stream_id) REFERENCES stream_master (stream_id),
            FOREIGN KEY (class_id) REFERENCES class_master (class_id)
        )
    ''')
    
        # In init_database(), after students table creation:
    cursor.execute("PRAGMA table_info(students)")
    columns = [col[1] for col in cursor.fetchall()]
    if "password_hash" not in columns:
        cursor.execute("ALTER TABLE students ADD COLUMN password_hash TEXT")

    # Videos Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            date_added DATE DEFAULT CURRENT_DATE,
            class_id TEXT,
            stream_id TEXT,
            subject_id TEXT,
            chapter_id TEXT,
            content_description TEXT,
            video_link TEXT NOT NULL,
            thumbnail_url TEXT,
            duration INTEGER DEFAULT 0,
            file_size INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            is_published BOOLEAN DEFAULT 1,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (stream_id) REFERENCES stream_master (stream_id),
            FOREIGN KEY (class_id) REFERENCES class_master (class_id),
            FOREIGN KEY (subject_id) REFERENCES subject_master (subject_id),
            FOREIGN KEY (chapter_id) REFERENCES chapter_master (chapter_id)
        )
    ''')
    
    # User Progress Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            video_id TEXT NOT NULL,
            watched_duration INTEGER DEFAULT 0,
            total_duration INTEGER DEFAULT 0,
            completion_percentage REAL DEFAULT 0,
            is_completed BOOLEAN DEFAULT 0,
            last_watched TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            watch_count INTEGER DEFAULT 0,
            bookmarks TEXT,
            FOREIGN KEY (student_id) REFERENCES students (student_id),
            FOREIGN KEY (video_id) REFERENCES videos (video_id),
            UNIQUE(student_id, video_id)
        )
    ''')
    
    # Analytics Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE DEFAULT CURRENT_DATE,
            active_users INTEGER DEFAULT 0,
            videos_watched INTEGER DEFAULT 0,
            total_watch_time INTEGER DEFAULT 0,
            new_registrations INTEGER DEFAULT 0,
            UNIQUE(date)
        )
    ''')
    
    # Insert default admin user if not exists
    cursor.execute("SELECT COUNT(*) FROM admin_users")
    if cursor.fetchone()[0] == 0:
        admin_password = hash_password("admin123")
        cursor.execute(
            "INSERT INTO admin_users (username, password_hash, email) VALUES (?, ?, ?)",
            ("admin", admin_password, "admin@tutorial.com")
        )
    
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == hashed

def generate_id(prefix: str, table_name: str, id_column: str) -> str:
    """Generate unique ID with prefix"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    conn.close()
    return f"{prefix}{count + 1:04d}"

def generate_video_id() -> str:
    """Generate a unique video ID using UUID"""
    import uuid
    return f"V{uuid.uuid4().hex[:12].upper()}"
#=====================================================
def send_otp(mobile_no: str, otp: str) -> bool:
    """Send OTP via SMS using Fast2SMS API (free plan: only to registered number)"""
    api_key = "72aSrmCtyoHBjsPE8p0NTdI3uG9RMzX4VcWUqxFY5AkflLbOJZCZIVMi4Lmtb1a0QART5lUzGPuwFdDE"  # Replace with your actual API key
    url = "https://www.fast2sms.com/dev/bulkV2"
    headers = {
        "authorization": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "route": "q",
        "message": f"Your Arya Educations OTP is: {otp}",
        "language": "english",
        "flash": 0,
        "numbers": mobile_no
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        result = response.json()
        if result.get("return"):
            print(f"OTP {otp} sent to {mobile_no} via Fast2SMS.")
            return True
        else:
            print(f"Fast2SMS error: {result}")
            return False
    except Exception as e:
        print(f"Error sending OTP: {e}")
        return False


#====================================================

def is_valid_mobile(mobile_no: str) -> bool:
    """Validate mobile number format"""
    pattern = r'^[6-9]\d{9}$'
    return bool(re.match(pattern, mobile_no))

def is_valid_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

def initialize_session():
    """Initialize session state variables"""
    if 'screen' not in st.session_state:
        st.session_state.screen = 'welcome'
    if 'user_type' not in st.session_state:
        st.session_state.user_type = None
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'user_data' not in st.session_state:
        st.session_state.user_data = {}
    if 'is_authenticated' not in st.session_state:
        st.session_state.is_authenticated = False
    if 'login_time' not in st.session_state:
        st.session_state.login_time = None
    if 'last_activity' not in st.session_state:
        st.session_state.last_activity = time.time()
    if 'current_video' not in st.session_state:
        st.session_state.current_video = None
    if 'video_progress' not in st.session_state:
        st.session_state.video_progress = {}
    if 'selected_rows' not in st.session_state:
        st.session_state.selected_rows = {}

def check_session_timeout():
    """Check if session has timed out"""
    if st.session_state.is_authenticated and st.session_state.last_activity:
        if time.time() - st.session_state.last_activity > APP_CONFIG['auto_logout_time']:
            logout_user()
            st.warning("Session expired. Please login again.")
            return True
    return False

def update_activity():
    """Update last activity timestamp"""
    st.session_state.last_activity = time.time()

def logout_user():
    """Clear session and logout user"""
    st.session_state.screen = 'welcome'
    st.session_state.user_type = None
    st.session_state.user_id = None
    st.session_state.user_data = {}
    st.session_state.is_authenticated = False
    st.session_state.login_time = None
    st.session_state.last_activity = None
    st.session_state.current_video = None
    st.session_state.video_progress = {}
    st.session_state.selected_rows = {}

# =============================================================================
# WELCOME SCREEN
# =============================================================================

def show_welcome_screen():
    """Display welcome screen with branding"""
    st.markdown("""
        <style>
        .welcome-container {
            text-align: center;
            padding: 2rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
            color: white;
            margin-bottom: 2rem;
        }
        .welcome-title {
            font-size: 3rem;
            font-weight: bold;
            margin-bottom: 1rem;
        }
        .welcome-tagline {
            font-size: 1.2rem;
            margin-bottom: 2rem;
            opacity: 0.9;
        }
        .get-started-btn {
            background: #28a745;
            color: white;
            padding: 1rem 2rem;
            border-radius: 25px;
            border: none;
            font-size: 1.1rem;
            cursor: pointer;
            transition: all 0.3s;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
        <div class="welcome-container">
            <div class="welcome-title">📚 {APP_CONFIG['app_name']}</div>
            <div class="welcome-tagline">{APP_CONFIG['tagline']}</div>
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀 Get Started", use_container_width=True, type="primary"):
            st.session_state.screen = 'login_selection'
            st.rerun()

# =============================================================================
# LOGIN SELECTION SCREEN
# =============================================================================

def show_login_selection():
    """Display login type selection screen"""
    st.markdown("### Choose Login Type")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("👨‍💼 Admin Login", use_container_width=True, type="primary"):
            st.session_state.screen = 'admin_login'
            st.rerun()
    
    with col2:
        if st.button("👨‍🎓 Student Login", use_container_width=True, type="secondary"):
            st.session_state.screen = 'student_login'
            st.rerun()
    
    st.markdown("---")
    if st.button("⬅️ Back to Welcome", use_container_width=True):
        st.session_state.screen = 'welcome'
        st.rerun()

# =============================================================================
# ADMIN AUTHENTICATION
# =============================================================================

def show_admin_login():
    """Display admin login screen"""
    st.markdown("### Admin Login")
    
    with st.form("admin_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login", use_container_width=True, type="primary")
        
        if submit:
            if username and password:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, username, password_hash FROM admin_users WHERE username = ? AND is_active = 1",
                    (username,)
                )
                user = cursor.fetchone()
                conn.close()
                
                if user and verify_password(password, user[2]):
                    st.session_state.user_type = 'admin'
                    st.session_state.user_id = user[1]
                    st.session_state.user_data = {'username': user[1]}
                    st.session_state.is_authenticated = True
                    st.session_state.login_time = time.time()
                    st.session_state.screen = 'admin_dashboard'
                    
                    # Update last login
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE admin_users SET last_login = CURRENT_TIMESTAMP WHERE username = ?",
                        (username,)
                    )
                    conn.commit()
                    conn.close()
                    
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            else:
                st.error("Please fill in all fields")
    
    if st.button("⬅️ Back", use_container_width=True):
        st.session_state.screen = 'login_selection'
        st.rerun()

# =============================================================================
# STUDENT AUTHENTICATION
# =============================================================================
#=============================================================

#==========================================================

def show_student_login():
    """Student login with mobile number and password"""
    st.markdown("### Student Login")
    with st.form("student_login_form"):
        mobile_no = st.text_input("Mobile Number*", placeholder="Enter 10-digit mobile number")
        password = st.text_input("Password*", type="password")
        submit = st.form_submit_button("Login", type="primary")
        register = st.form_submit_button("Register as New Student")
        
        if submit:
            if not (mobile_no and password):
                st.error("Please fill in all fields")
            elif not is_valid_mobile(mobile_no):
                st.error("Invalid mobile number format")
            else:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT student_id, name, password_hash, video_enabled FROM students WHERE mobile_no = ? AND is_active = 1",
                    (mobile_no,)
                )
                student = cursor.fetchone()
                conn.close()
                if not student:
                    st.error("Mobile number not registered by admin. Please contact admin.")
                elif not student[3]:
                    st.error("Your video access is disabled. Please contact admin.")
                elif not student[2]:
                    st.error("No password set. Please register first.")
                elif not verify_password(password, student[2]):
                    st.error("Incorrect password.")
                else:
                    st.session_state.user_type = 'student'
                    st.session_state.user_id = student[0]
                    st.session_state.user_data = {
                        'student_id': student[0],
                        'name': student[1],
                        'mobile': mobile_no
                    }
                    st.session_state.is_authenticated = True
                    st.session_state.login_time = time.time()
                    st.session_state.screen = 'student_interface'
                    st.success("Login successful!")
                    st.rerun()
        if register:
            st.session_state.screen = 'student_registration'
            st.rerun()

#=====================================================================

def show_student_registration():
    """Student registration with mobile number and password"""
    st.markdown("### Student Registration")
    with st.form("student_registration_form"):
        mobile_no = st.text_input("Mobile Number*", placeholder="Enter 10-digit mobile number")
        password = st.text_input("Password*", type="password")
        confirm_password = st.text_input("Confirm Password*", type="password")
        submit = st.form_submit_button("Register", type="primary")
        cancel = st.form_submit_button("Cancel")
        
        if submit:
            if not (mobile_no and password and confirm_password):
                st.error("Please fill in all fields")
            elif not is_valid_mobile(mobile_no):
                st.error("Invalid mobile number format")
            elif password != confirm_password:
                st.error("Passwords do not match")
            else:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT student_id FROM students WHERE mobile_no = ? AND is_active = 1",
                    (mobile_no,)
                )
                student = cursor.fetchone()
                if not student:
                    st.error("Mobile number not registered by admin. Please contact admin.")
                else:
                    password_hash = hash_password(password)
                    cursor.execute(
                        "UPDATE students SET password_hash = ? WHERE mobile_no = ?",
                        (password_hash, mobile_no)
                    )
                    conn.commit()
                    conn.close()
                    st.success("Registration successful! You can now login.")
                    st.session_state.screen = 'student_login'
                    st.rerun()
        if cancel:
            st.session_state.screen = 'student_login'
            st.rerun()

# =============================================================================
# ADMIN DASHBOARD
# =============================================================================

def show_admin_dashboard():
    """Display admin dashboard with all management features"""
    if check_session_timeout():
        return
    
    update_activity()
    
    st.markdown(f"### Welcome, {st.session_state.user_data.get('username', 'Admin')}!")
    
    # Logout button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col3:
        if st.button("🚪 Logout", type="secondary"):
            if st.session_state.get('confirm_logout', False):
                logout_user()
                st.success("Logged out successfully!")
                st.rerun()
            else:
                st.session_state.confirm_logout = True
                st.rerun()
    
    if st.session_state.get('confirm_logout', False):
        st.warning("Are you sure you want to logout?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, Logout"):
                logout_user()
                st.success("Logged out successfully!")
                st.rerun()
        with col2:
            if st.button("Cancel"):
                st.session_state.confirm_logout = False
                st.rerun()
        return
    #===============================================================================================

    # Navigation tabs
    # Navigation tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Dashboard", 
        "🗂️ Master Data", 
        "🎥 Video Management", 
        "👨‍🎓 Student Management", 
        "📈 Analytics",
        "🔐 Admin Settings"  # New tab
    ])
    
    with tab1:
        show_dashboard_overview()
    
    with tab2:
        show_master_data_management()
    
    with tab3:
        show_video_management()
    
    with tab4:
        show_student_management()
    
    with tab5:
        show_analytics_dashboard()
    
    with tab6:
        show_admin_settings()  # New function call


#=================================================================================

def show_dashboard_overview():
    """Show overview dashboard with key metrics"""
    st.markdown("#### Dashboard Overview")
    
    # Get statistics
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM videos WHERE is_published = 1")
    total_videos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM students WHERE is_active = 1 AND video_enabled = 1")
    active_students = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(view_count) FROM videos")
    total_views = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM user_progress WHERE is_completed = 1")
    completed_videos = cursor.fetchone()[0]
    
    conn.close()
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Videos", total_videos)
    
    with col2:
        st.metric("Active Students", active_students)
    
    with col3:
        st.metric("Total Views", total_views)
    
    with col4:
        st.metric("Completed Videos", completed_videos)
    
    # Recent activity
    st.markdown("#### Recent Activity")
    conn = sqlite3.connect(DB_FILE)
    recent_videos = pd.read_sql_query("""
        SELECT title, created_at, view_count 
        FROM videos 
        ORDER BY created_at DESC 
        LIMIT 5
    """, conn)
    
    if not recent_videos.empty:
        st.dataframe(recent_videos, use_container_width=True)
    else:
        st.info("No videos uploaded yet.")
    
    conn.close()
#=====================================================================
def show_master_data_management():
    """Show master data management interface"""
    st.markdown("#### Master Data Management")
    
    subtab1, subtab2, subtab3, subtab4 = st.tabs([
        "Stream Master", 
        "Class Master", 
        "Subject Master", 
        "Chapter Master"
    ])
    
    with subtab1:
        manage_master_data("stream_master", "Stream", "stream_id", "stream_name", "S")
    
    with subtab2:
        manage_master_data("class_master", "Class", "class_id", "class_name", "C")
    
    with subtab3:
        manage_master_data("subject_master", "Subject", "subject_id", "subject_name", "SUB")
    
    with subtab4:
        manage_master_data("chapter_master", "Chapter", "chapter_id", "chapter_name", "CH")
#==================================================================================================

def manage_master_data(table_name: str, display_name: str, id_col: str, name_col: str, prefix: str):
    """Master data management: only allow adding, no edit or delete"""
    st.markdown(f"##### {display_name} Master Data")

    # Get current data
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(f"SELECT id, {id_col}, {name_col}, is_active FROM {table_name} ORDER BY id", conn)

    # Display data (all columns disabled)
    st.dataframe(
        df,
        column_config={
            id_col: st.column_config.TextColumn(f"{display_name} ID", disabled=True),
            name_col: st.column_config.TextColumn(f"{display_name} Name", disabled=True),
            "is_active": st.column_config.CheckboxColumn("Active", disabled=True)
        },
        hide_index=True,
        use_container_width=True
    )

    # Add new record form
    st.markdown("---")
    with st.form(f"add_{table_name}_form", clear_on_submit=True):
        st.markdown(f"##### Add New {display_name}")
        new_name = st.text_input(f"{display_name} Name")
        submit_add = st.form_submit_button("💾 Save", type="primary")
        if submit_add:
            if new_name and new_name.strip():
                new_id = generate_id(prefix, table_name, id_col)
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"INSERT INTO {table_name} ({id_col}, {name_col}) VALUES (?, ?)",
                        (new_id, new_name.strip())
                    )
                    conn.commit()
                    st.success(f"✅ {display_name} '{new_name}' added successfully!")
                    time.sleep(1)
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"❌ {display_name} '{new_name}' already exists!")
                except Exception as e:
                    st.error(f"❌ Error adding {display_name}: {str(e)}")
            else:
                st.error("Please enter a valid name")
    conn.close()


#=======================================================================================================
#=====================================================================================================
def show_video_management():
    """Show video management interface"""
    st.markdown("#### Video Management")
    
    # Get videos data
    conn = sqlite3.connect(DB_FILE)
    videos_df = pd.read_sql_query("""
        SELECT v.*, s.stream_name, c.class_name, sub.subject_name, ch.chapter_name
        FROM videos v
        LEFT JOIN stream_master s ON v.stream_id = s.stream_id
        LEFT JOIN class_master c ON v.class_id = c.class_id
        LEFT JOIN subject_master sub ON v.subject_id = sub.subject_id
        LEFT JOIN chapter_master ch ON v.chapter_id = ch.chapter_id
        ORDER BY v.created_at DESC
    """, conn)
    
    # Add video button
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("➕ Add New Video", type="primary"):
            st.session_state.add_video = True
    
    # Display videos
    if not videos_df.empty:
        videos_df = videos_df.reset_index(drop=True)
        # Add selection column
        videos_df['Select'] = False
        
        display_cols = ['Select','video_id', 'title', 'stream_name', 'class_name', 'subject_name', 
                       'chapter_name','video_link', 'view_count', 'is_published', 'created_at']

        # FIX: Wrap the data_editor in a proper form with submit button
        with st.form("video_management_form", clear_on_submit=False):
            edited_videos = st.data_editor(
                videos_df[display_cols],
                column_config={
                    "Select": st.column_config.CheckboxColumn("Select", default=False),
                    "video_id": st.column_config.TextColumn("Video ID", disabled=True),
                    "title": "Video Title",
                    "stream_name": "Stream",
                    "class_name": "Class",
                    "subject_name": "Subject",
                    "chapter_name": "Chapter",
                    "video_link": st.column_config.LinkColumn("Video Link",disabled=True),
                    "view_count": st.column_config.NumberColumn("Views"),
                    "is_published": st.column_config.CheckboxColumn("Published"),
                    "created_at": st.column_config.TextColumn("Created", disabled=True)
                },
                hide_index=True,
                use_container_width=True,
                disabled=['created_at']
            )
            
            # FIX: Add the missing submit button
            form_submitted = st.form_submit_button("Update Video List")
        
        # Process form submission
        if form_submitted:
            # Update any changes made in the data editor
            for idx, row in edited_videos.iterrows():
                if row['Select']:
                    video_id = videos_df.loc[idx, 'video_id']
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE videos SET 
                        is_published = ?
                        WHERE video_id = ?
                    """, (row['is_published'], video_id))
                    conn.commit()
            st.success("Video list updated!")
            st.rerun()
        
        # Action buttons (outside the form)
        selected_videos = edited_videos[edited_videos['Select'] == True]
        #============================================================
        # ...existing code...
        if not selected_videos.empty:
            selected_video_id = selected_videos.iloc[0]['video_id']
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("✏️ Edit Selected", key=f"edit_selected_{selected_video_id}"):
                    selected_idx = selected_videos.index[0]
                    # Get the complete video data from original videos_df using the correct index
                    video_data = videos_df.loc[selected_idx].copy()
                    # Only update editable fields, do NOT overwrite stream_id/class_id/subject_id/chapter_id with names
                    editable_cols = ['title', 'description', 'content_description', 'video_link', 'is_published']
                    for col in editable_cols:
                        if col in edited_videos.columns:
                            video_data[col] = edited_videos.loc[selected_idx, col]
                    st.session_state.edit_video = video_data.to_dict()
            with col2:
                if st.button("👁️ View Details", key=f"view_selected_{selected_video_id}"):
                    selected_idx = selected_videos.index[0]
                    st.session_state.view_video = videos_df.loc[selected_idx]
            with col3: 
                if st.button("🗑️ Delete Selected", type="secondary"):
                    selected_idx = selected_videos.index[0]
                    video_id = videos_df.loc[selected_idx, 'video_id']
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
                    conn.commit()
                    st.success("Video deleted successfully!")
                    st.rerun()
# ...existing code...
        #=====================================================================
    else:
        st.info("No videos uploaded yet.")
    
    # Add video form
    if st.session_state.get('add_video', False):
        show_add_video_form()
    
    # Edit video form
    if 'edit_video' in st.session_state:
        show_edit_video_form()
    
    # View video details
    if 'view_video' in st.session_state:
        show_video_details()
    
    conn.close()

#==================================================================================================================================
# ...existing code...
def show_add_video_form():
    """Show add video form"""
    st.markdown("##### Add New Video")
    
    with st.form("add_video_form"):
        title = st.text_input("Video Title*")
        description = st.text_area("Description")
        
        # Get master data for dropdowns
        conn = sqlite3.connect(DB_FILE)
        streams = pd.read_sql_query("SELECT stream_id, stream_name FROM stream_master WHERE is_active = 1", conn)
        classes = pd.read_sql_query("SELECT class_id, class_name FROM class_master WHERE is_active = 1", conn)
        subjects = pd.read_sql_query("SELECT subject_id, subject_name FROM subject_master WHERE is_active = 1", conn)
        chapters = pd.read_sql_query("SELECT chapter_id, chapter_name FROM chapter_master WHERE is_active = 1", conn)
        
        col1, col2 = st.columns(2)
        with col1:
            stream_options = streams['stream_id'].tolist() if not streams.empty else []
            selected_stream = st.selectbox(
                "Stream*",
                options=stream_options,
                format_func=lambda x: streams[streams['stream_id'] == x]['stream_name'].iloc[0] if not streams.empty and x in streams['stream_id'].values else str(x)
            )
            
            subject_options = subjects['subject_id'].tolist() if not subjects.empty else []
            selected_subject = st.selectbox(
                "Subject*",
                options=subject_options,
                format_func=lambda x: subjects[subjects['subject_id'] == x]['subject_name'].iloc[0] if not subjects.empty and x in subjects['subject_id'].values else str(x)
            )
        
        with col2:
            class_options = classes['class_id'].tolist() if not classes.empty else []
            selected_class = st.selectbox(
                "Class*",
                options=class_options,
                format_func=lambda x: classes[classes['class_id'] == x]['class_name'].iloc[0] if not classes.empty and x in classes['class_id'].values else str(x)
            )
            
            chapter_options = chapters['chapter_id'].tolist() if not chapters.empty else []
            selected_chapter = st.selectbox(
                "Chapter*",
                options=chapter_options,
                format_func=lambda x: chapters[chapters['chapter_id'] == x]['chapter_name'].iloc[0] if not chapters.empty and x in chapters['chapter_id'].values else str(x)
            )
        
        content_description = st.text_area("Content Description")
        video_link = st.text_input("Video Link (YouTube/Vimeo URL)*")
        is_published = st.checkbox("Publish immediately", value=True)
        
        submit = st.form_submit_button("Save Video", type="primary")
        cancel = st.form_submit_button("Cancel")
        
        if submit:
            if title and video_link and selected_stream and selected_class and selected_subject and selected_chapter:
                        
                video_id = generate_video_id()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO videos (
                        video_id, title, description, class_id, stream_id, 
                        subject_id, chapter_id, content_description, video_link, 
                        is_published, created_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    video_id, title, description, selected_class, selected_stream,
                    selected_subject, selected_chapter, content_description, 
                    video_link, is_published, st.session_state.user_id
                ))
                conn.commit()
                st.success("Video added successfully!")
                st.session_state.add_video = False
                st.rerun()
            else:
                st.error("Please fill in all required fields")
        if cancel:
            st.session_state.add_video = False
            st.rerun()
        
        conn.close()


#=========================================================================================================================
def show_edit_video_form():
    """Show edit video form"""
    video_data = st.session_state.edit_video
    st.markdown("##### Edit Video")
    
    with st.form("edit_video_form"):
        title = st.text_input("Video Title*", value=video_data['title'])
        description = st.text_area("Description", value=video_data.get('description', ''))
        
        # Get master data for dropdowns
        conn = sqlite3.connect(DB_FILE)
        streams = pd.read_sql_query("SELECT stream_id, stream_name FROM stream_master WHERE is_active = 1", conn)
        classes = pd.read_sql_query("SELECT class_id, class_name FROM class_master WHERE is_active = 1", conn)
        subjects = pd.read_sql_query("SELECT subject_id, subject_name FROM subject_master WHERE is_active = 1", conn)
        chapters = pd.read_sql_query("SELECT chapter_id, chapter_name FROM chapter_master WHERE is_active = 1", conn)
        
        col1, col2 = st.columns(2)
        with col1:
            current_stream_id = video_data['stream_id'] if pd.notna(video_data['stream_id']) else None
            stream_options = streams['stream_id'].tolist()
            try:
                stream_idx = stream_options.index(current_stream_id) if current_stream_id in stream_options else 0
            except (ValueError, TypeError):
                stream_idx = 0
            selected_stream = st.selectbox(
                "Stream*",
                options=stream_options,
                index=stream_idx,
                format_func=lambda x: streams[streams['stream_id'] == x]['stream_name'].iloc[0] if len(streams[streams['stream_id'] == x]) > 0 else str(x)
            )

            current_subject_id = video_data['subject_id'] if pd.notna(video_data['subject_id']) else None
            subject_options = subjects['subject_id'].tolist()
            try:
                subject_idx = subject_options.index(current_subject_id) if current_subject_id in subject_options else 0
            except (ValueError, TypeError):
                subject_idx = 0
            selected_subject = st.selectbox(
                "Subject*",
                options=subject_options,
                index=subject_idx,
                format_func=lambda x: subjects[subjects['subject_id'] == x]['subject_name'].iloc[0] if len(subjects[subjects['subject_id'] == x]) > 0 else str(x)
            )
        
        with col2:
            current_class_id = video_data['class_id'] if pd.notna(video_data['class_id']) else None
            class_options = classes['class_id'].tolist()
            try:
                class_idx = class_options.index(current_class_id) if current_class_id in class_options else 0
            except (ValueError, TypeError):
                class_idx = 0
            selected_class = st.selectbox(
                "Class*",
                options=class_options,
                index=class_idx,
                format_func=lambda x: classes[classes['class_id'] == x]['class_name'].iloc[0] if len(classes[classes['class_id'] == x]) > 0 else str(x)
            )

            current_chapter_id = video_data['chapter_id'] if pd.notna(video_data['chapter_id']) else None
            chapter_options = chapters['chapter_id'].tolist()
            try:
                chapter_idx = chapter_options.index(current_chapter_id) if current_chapter_id in chapter_options else 0
            except (ValueError, TypeError):
                chapter_idx = 0
            selected_chapter = st.selectbox(
                "Chapter*",
                options=chapter_options,
                index=chapter_idx,
                format_func=lambda x: chapters[chapters['chapter_id'] == x]['chapter_name'].iloc[0] if len(chapters[chapters['chapter_id'] == x]) > 0 else str(x)
            )
        
        content_description = st.text_area("Content Description", value=video_data.get('content_description', ''))
        video_link = st.text_input("Video Link*", value=video_data['video_link'])
        is_published = st.checkbox("Published", value=bool(video_data['is_published']))
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Update Video", type="primary"):
                if title and video_link:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE videos SET 
                        title = ?, description = ?, class_id = ?, stream_id = ?,
                        subject_id = ?, chapter_id = ?, content_description = ?, 
                        video_link = ?, is_published = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE video_id = ?
                    """, (
                        title, description, selected_class, selected_stream,
                        selected_subject, selected_chapter, content_description,
                        video_link, is_published, video_data['video_id']
                    ))
                    conn.commit()
                    st.success("Video updated successfully!")
                    del st.session_state.edit_video
                    st.rerun()
                else:
                    st.error("Please fill in all required fields")
        with col2:
            if st.form_submit_button("Cancel"):
                del st.session_state.edit_video
                st.rerun()
        conn.close()


    #=======================================================================================================================

def show_video_details():
    """Show video details"""
    video_data = st.session_state.view_video
    st.markdown("##### Video Details")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Title:** {video_data['title']}")
        st.write(f"**Stream:** {video_data['stream_name']}")
        st.write(f"**Subject:** {video_data['subject_name']}")
        st.write(f"**Views:** {video_data['view_count']}")
    
    with col2:
        st.write(f"**Class:** {video_data['class_name']}")
        st.write(f"**Chapter:** {video_data['chapter_name']}")
        st.write(f"**Published:** {'Yes' if video_data['is_published'] else 'No'}")
        st.write(f"**Created:** {video_data['created_at']}")
    
    if video_data.get('description'):
        st.write(f"**Description:** {video_data['description']}")
    
    if video_data.get('content_description'):
        st.write(f"**Content:** {video_data['content_description']}")
    
    st.write(f"**Video Link:** {video_data['video_link']}")
    
    if st.button("Close Details"):
        del st.session_state.view_video
        st.rerun()
#=======================================================================================================================================
def show_student_management():
    """Show student management interface - Robust for empty DB"""
    st.markdown("#### Student Management")
    
    # Get students data
    conn = sqlite3.connect(DB_FILE)
    students_df = pd.read_sql_query("""
        SELECT s.*, sm.stream_name, cm.class_name
        FROM students s
        LEFT JOIN stream_master sm ON s.stream_id = sm.stream_id
        LEFT JOIN class_master cm ON s.class_id = cm.class_id
        WHERE s.is_active = 1
        ORDER BY s.created_at DESC
    """, conn)
    
    # Add student button
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("➕ Add New Student", type="primary"):
            st.session_state.add_student = True
    
    # Display students only if data exists
    if not students_df.empty:
        students_df['Select'] = False
        display_cols = ['Select','student_id', 'name', 'mobile_no', 'stream_name', 'class_name', 
                       'city', 'video_enabled', 'last_login']
        edited_students = st.data_editor(
            students_df[display_cols],
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=False),
                "name": "Name",
                "mobile_no": "Mobile",
                "stream_name": "Stream",
                "class_name": "Class",
                "city": "City",
                "video_enabled": st.column_config.CheckboxColumn("Video Access"),
                "last_login": st.column_config.DatetimeColumn("Last Login")
            },
            hide_index=True,
            use_container_width=True,
            key="student_data_editor"
        )
        selected_students = edited_students[edited_students['Select'] == True]
        if not selected_students.empty:
            col1, col2, col3 = st.columns(3)
            selected_student_id = selected_students.iloc[0]['student_id']
            student_row = students_df[students_df['student_id'] == selected_student_id].iloc[0]
            with col1:
                if st.button("✏️ Edit Selected", key=f"edit_selected_{selected_student_id}"):
                    st.session_state.edit_student = student_row.to_dict()
                    st.session_state.add_student = False
                    st.rerun()
            with col2:
                if st.button("🗑️ Delete Selected", key=f"delete_selected_{selected_student_id}", type="secondary"):
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE students SET is_active = 0 WHERE student_id = ?", (selected_student_id,))
                    conn.commit()
                    conn.close()
                    st.success("Student deleted successfully!")
                    st.rerun()
    else:
        st.info("No students found. Please add a new student.")
    
    # Add/Edit forms
    if st.session_state.get('add_student', False):
        show_add_student_form()
    if 'edit_student' in st.session_state:
        show_edit_student_form()
    conn.close()

#===============================================================================================
def show_add_student_form():
    """Show add student form"""
    st.markdown("##### Add New Student")
    
    with st.form("add_student_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Full Name*")
            college_name = st.text_input("College Name")
            address_1 = st.text_input("Address Line 1")
            address_2 = st.text_input("Address Line 2")
            city = st.text_input("City")
            pin_code = st.text_input("Pin Code")
            mobile_no = st.text_input("Mobile Number*")
        
        with col2:
            address_3 = st.text_input("Address Line 3")
            address_4 = st.text_input("Address Line 4")
            state = st.text_input("State")
            dob = st.date_input("Date of Birth")
            
            # Get master data for dropdowns
            conn = sqlite3.connect(DB_FILE)
            streams = pd.read_sql_query("SELECT stream_id, stream_name FROM stream_master WHERE is_active = 1", conn)
            classes = pd.read_sql_query("SELECT class_id, class_name FROM class_master WHERE is_active = 1", conn)
            
            # FIX: Convert to Python int to avoid int64 issues
            #==============================================
             # ...existing code...
            stream_options = streams['stream_id'].tolist() if not streams.empty else []
            selected_stream = st.selectbox(
                "Stream*",
                options=stream_options,
                format_func=lambda x: streams[streams['stream_id'] == x]['stream_name'].iloc[0] if not streams.empty and x in streams['stream_id'].values else str(x)
            )

            class_options = classes['class_id'].tolist() if not classes.empty else []
            selected_class = st.selectbox(
                "Class*",
                options=class_options,
                format_func=lambda x: classes[classes['class_id'] == x]['class_name'].iloc[0] if not classes.empty and x in classes['class_id'].values else str(x)
            )
# ...existing code...
            #==========================================

            video_enabled = st.checkbox("Enable Video Access", value=True)
        
        col1, col2 = st.columns(2)
        with col1:
            # This submit button was already present - no fix needed for Error 1 here
            if st.form_submit_button("Save Student", type="primary"):
                if name and mobile_no and is_valid_mobile(mobile_no) and selected_stream and selected_class:
                    student_id = generate_id("STU", "students", "student_id")
                    
                    cursor = conn.cursor()
                    try:
                        cursor.execute("""
                            INSERT INTO students (
                                student_id, name, college_name, address_1, address_2, 
                                address_3, address_4, city, state, pin_code, dob, 
                                stream_id, class_id, mobile_no, video_enabled
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            student_id, name, college_name, address_1, address_2,
                            address_3, address_4, city, state, pin_code, dob,
                            selected_stream, selected_class, mobile_no, video_enabled
                        ))
                        conn.commit()
                        
                        st.success("Student added successfully!")
                        st.session_state.add_student = False
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Mobile number already registered!")
                else:
                    st.error("Please fill in all required fields with valid data")
        
        with col2:
            if st.form_submit_button("Cancel"):
                st.session_state.add_student = False
                st.rerun()
    
    conn.close()


#===============================================================================================================
def show_edit_student_form():
    """Show edit student form"""
    student_data = st.session_state.edit_student
    st.markdown("##### Edit Student")
    
    with st.form("edit_student_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Full Name*", value=student_data['name'])
            college_name = st.text_input("College Name", value=student_data.get('college_name', ''))
            address_1 = st.text_input("Address Line 1", value=student_data.get('address_1', ''))
            address_2 = st.text_input("Address Line 2", value=student_data.get('address_2', ''))
            city = st.text_input("City", value=student_data.get('city', ''))
            pin_code = st.text_input("Pin Code", value=student_data.get('pin_code', ''))
            mobile_no = st.text_input("Mobile Number*", value=student_data['mobile_no'])
        
        with col2:
            address_3 = st.text_input("Address Line 3", value=student_data.get('address_3', ''))
            address_4 = st.text_input("Address Line 4", value=student_data.get('address_4', ''))
            state = st.text_input("State", value=student_data.get('state', ''))
            
            # Handle DOB
            dob_value = student_data.get('dob')
            if dob_value:
                try:
                    if isinstance(dob_value, str):
                        dob_value = datetime.strptime(dob_value, '%Y-%m-%d').date()
                    dob = st.date_input("Date of Birth", value=dob_value)
                except:
                    dob = st.date_input("Date of Birth")
            else:
                dob = st.date_input("Date of Birth")
            
            # Get master data for dropdowns
            conn = sqlite3.connect(DB_FILE)
            streams = pd.read_sql_query("SELECT stream_id, stream_name FROM stream_master WHERE is_active = 1", conn)
            classes = pd.read_sql_query("SELECT class_id, class_name FROM class_master WHERE is_active = 1", conn)
            
            # FIX: Convert numpy int64 to Python int and handle index properly
            #===============================================
            
            # ...existing code...
            current_stream_id = student_data['stream_id'] if pd.notna(student_data['stream_id']) else None
            stream_options = streams['stream_id'].tolist()

            try:
                stream_idx = stream_options.index(current_stream_id) if current_stream_id in stream_options else 0
            except (ValueError, TypeError):
                stream_idx = 0

            selected_stream = st.selectbox(
                "Stream*",
                options=stream_options,
                index=stream_idx,
                format_func=lambda x: streams[streams['stream_id'] == x]['stream_name'].iloc[0] if len(streams[streams['stream_id'] == x]) > 0 else str(x)
            )

            current_class_id = student_data['class_id'] if pd.notna(student_data['class_id']) else None
            class_options = classes['class_id'].tolist()

            try:
                class_idx = class_options.index(current_class_id) if current_class_id in class_options else 0
            except (ValueError, TypeError):
                class_idx = 0

            selected_class = st.selectbox(
                "Class*",
                options=class_options,
                index=class_idx,
                format_func=lambda x: classes[classes['class_id'] == x]['class_name'].iloc[0] if len(classes[classes['class_id'] == x]) > 0 else str(x)
            )
            # ...existing code...

            #==================================================
            video_enabled = st.checkbox("Enable Video Access", value=bool(student_data['video_enabled']))
        
        col1, col2 = st.columns(2)
        with col1:
            # This submit button was already present - no fix needed for Error 1 here
            if st.form_submit_button("Update Student", type="primary"):
                if name and mobile_no and is_valid_mobile(mobile_no):
                    cursor = conn.cursor()
                    try:
                        cursor.execute("""
                            UPDATE students SET 
                            name = ?, college_name = ?, address_1 = ?, address_2 = ?,
                            address_3 = ?, address_4 = ?, city = ?, state = ?, pin_code = ?,
                            dob = ?, stream_id = ?, class_id = ?, mobile_no = ?, video_enabled = ?
                            WHERE student_id = ?
                        """, (
                            name, college_name, address_1, address_2, address_3, address_4,
                            city, state, pin_code, dob, selected_stream, selected_class,
                            mobile_no, video_enabled, student_data['student_id']
                        ))
                        conn.commit()
                        
                        st.success("Student updated successfully!")
                        del st.session_state.edit_student
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Mobile number already exists for another student!")
                else:
                    st.error("Please fill in all required fields with valid data")
        
        with col2:
            if st.form_submit_button("Cancel"):
                del st.session_state.edit_student
                st.rerun()
    
    conn.close()


    #==========================================================================================================

def show_student_progress():
    """Show individual student progress"""
    student_data = st.session_state.view_student_progress
    st.markdown(f"##### Progress for {student_data['name']}")
    
    conn = sqlite3.connect(DB_FILE)
    
    # Get student progress
    progress_df = pd.read_sql_query("""
        SELECT up.*, v.title, v.video_link, sm.stream_name, cm.class_name, 
               subm.subject_name, chm.chapter_name
        FROM user_progress up
        JOIN videos v ON up.video_id = v.video_id
        LEFT JOIN stream_master sm ON v.stream_id = sm.stream_id
        LEFT JOIN class_master cm ON v.class_id = cm.class_id
        LEFT JOIN subject_master subm ON v.subject_id = subm.subject_id
        LEFT JOIN chapter_master chm ON v.chapter_id = chm.chapter_id
        WHERE up.student_id = ?
        ORDER BY up.last_watched DESC
    """, conn, params=(student_data['student_id'],))
    
    if not progress_df.empty:
        # Summary stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Videos Watched", len(progress_df))
        with col2:
            completed = len(progress_df[progress_df['is_completed'] == 1])
            st.metric("Completed", completed)
        with col3:
            avg_completion = progress_df['completion_percentage'].mean()
            st.metric("Avg Completion", f"{avg_completion:.1f}%")
        with col4:
            total_watch_time = progress_df['watched_duration'].sum()
            st.metric("Watch Time", f"{total_watch_time//60}m")
        
        # Progress details
        st.markdown("##### Detailed Progress")
        display_progress = progress_df[[
            'title', 'subject_name', 'chapter_name', 'completion_percentage',
            'is_completed', 'watch_count', 'last_watched'
        ]].copy()
        
        st.dataframe(
            display_progress,
            column_config={
                "title": "Video Title",
                "subject_name": "Subject",
                "chapter_name": "Chapter",
                "completion_percentage": st.column_config.ProgressColumn(
                    "Progress",
                    min_value=0,
                    max_value=100,
                    format="%.1f%%"
                ),
                "is_completed": st.column_config.CheckboxColumn("Completed"),
                "watch_count": st.column_config.NumberColumn("Views"),
                "last_watched": st.column_config.DatetimeColumn("Last Watched")
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No video progress found for this student.")
    
    if st.button("Close Progress View"):
        del st.session_state.view_student_progress
        st.rerun()
    
    conn.close()

def show_analytics_dashboard():
    """Show analytics and statistics"""
    st.markdown("#### Analytics Dashboard")
    
    conn = sqlite3.connect(DB_FILE)
    
    # Overall statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM videos WHERE is_published = 1")
        total_videos = cursor.fetchone()[0]
        st.metric("Published Videos", total_videos)
    
    with col2:
        cursor.execute("SELECT COUNT(*) FROM students WHERE is_active = 1 AND video_enabled = 1")
        active_students = cursor.fetchone()[0]
        st.metric("Active Students", active_students)
    
    with col3:
        cursor.execute("SELECT SUM(view_count) FROM videos")
        total_views = cursor.fetchone()[0] or 0
        st.metric("Total Views", total_views)
    
    with col4:
        cursor.execute("SELECT COUNT(DISTINCT student_id) FROM user_progress WHERE last_watched > date('now', '-7 days')")
        weekly_active = cursor.fetchone()[0]
        st.metric("Weekly Active Users", weekly_active)
    
    # Most watched videos
    st.markdown("##### Most Watched Videos")
    most_watched = pd.read_sql_query("""
        SELECT v.title, v.view_count, sm.stream_name, cm.class_name, subm.subject_name
        FROM videos v
        LEFT JOIN stream_master sm ON v.stream_id = sm.stream_id
        LEFT JOIN class_master cm ON v.class_id = cm.class_id
        LEFT JOIN subject_master subm ON v.subject_id = subm.subject_id
        WHERE v.is_published = 1
        ORDER BY v.view_count DESC
        LIMIT 10
    """, conn)
    
    if not most_watched.empty:
        st.dataframe(most_watched, use_container_width=True)
    else:
        st.info("No video view data available.")
    
    # Student engagement
    st.markdown("##### Student Engagement")
    engagement = pd.read_sql_query("""
        SELECT s.name, s.mobile_no, COUNT(up.video_id) as videos_watched,
               AVG(up.completion_percentage) as avg_completion,
               MAX(up.last_watched) as last_activity
        FROM students s
        LEFT JOIN user_progress up ON s.student_id = up.student_id
        WHERE s.is_active = 1 AND s.video_enabled = 1
        GROUP BY s.student_id
        ORDER BY videos_watched DESC
        LIMIT 10
    """, conn)
    
    if not engagement.empty:
        st.dataframe(
            engagement,
            column_config={
                "name": "Student Name",
                "mobile_no": "Mobile",
                "videos_watched": st.column_config.NumberColumn("Videos Watched"),
                "avg_completion": st.column_config.NumberColumn("Avg Completion %", format="%.1f"),
                "last_activity": st.column_config.DatetimeColumn("Last Activity")
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No student engagement data available.")
    
    # Subject-wise statistics
    st.markdown("##### Subject-wise Video Distribution")
    subject_stats = pd.read_sql_query("""
        SELECT subm.subject_name, COUNT(v.video_id) as video_count,
               SUM(v.view_count) as total_views
        FROM videos v
        JOIN subject_master subm ON v.subject_id = subm.subject_id
        WHERE v.is_published = 1
        GROUP BY v.subject_id
        ORDER BY video_count DESC
    """, conn)
    
    if not subject_stats.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.bar_chart(subject_stats.set_index('subject_name')['video_count'])
        with col2:
            st.bar_chart(subject_stats.set_index('subject_name')['total_views'])
    else:
        st.info("No subject statistics available.")
    
    conn.close()

#===========================================================================
def show_admin_settings():
    """Show admin settings including password change"""
    st.markdown("#### Admin Settings")
    
    # Get current admin info
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, email, created_at, last_login FROM admin_users WHERE username = ?",
        (st.session_state.user_id,)
    )
    admin_info = cursor.fetchone()
    
    if not admin_info:
        st.error("Admin information not found.")
        conn.close()
        return
    
    username, email, created_at, last_login = admin_info
    
    # Admin Profile Section
    st.markdown("##### Admin Profile Information")
    col1, col2 = st.columns(2)
    
    with col1:
        st.write(f"**Username:** {username}")
        st.write(f"**Email:** {email or 'Not provided'}")
    
    with col2:
        st.write(f"**Account Created:** {created_at[:19] if created_at else 'Unknown'}")
        st.write(f"**Last Login:** {last_login[:19] if last_login else 'Never'}")
    
    st.markdown("---")
    
    # Password Change Section
    st.markdown("##### Change Password")
    
    with st.form("change_password_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        
        # Password strength indicator
        if new_password:
            strength_score = 0
            strength_messages = []
            
            if len(new_password) >= 8:
                strength_score += 1
            else:
                strength_messages.append("At least 8 characters")
            
            if any(c.isupper() for c in new_password):
                strength_score += 1
            else:
                strength_messages.append("At least one uppercase letter")
            
            if any(c.islower() for c in new_password):
                strength_score += 1
            else:
                strength_messages.append("At least one lowercase letter")
            
            if any(c.isdigit() for c in new_password):
                strength_score += 1
            else:
                strength_messages.append("At least one number")
            
            if any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in new_password):
                strength_score += 1
            else:
                strength_messages.append("At least one special character")
            
            # Display strength
            if strength_score < 2:
                st.error("❌ Weak password")
            elif strength_score < 4:
                st.warning("⚠️ Medium password")
            else:
                st.success("✅ Strong password")
            
            if strength_messages:
                st.info("Password should have: " + ", ".join(strength_messages))
        
        submit_password = st.form_submit_button("🔐 Change Password", type="primary")
        
        if submit_password:
            if not all([current_password, new_password, confirm_password]):
                st.error("❌ Please fill in all password fields")
            elif new_password != confirm_password:
                st.error("❌ New passwords do not match")
            elif len(new_password) < 6:
                st.error("❌ Password must be at least 6 characters long")
            else:
                # Verify current password
                cursor.execute(
                    "SELECT password_hash FROM admin_users WHERE username = ?",
                    (username,)
                )
                current_hash = cursor.fetchone()
                
                if current_hash and verify_password(current_password, current_hash[0]):
                    # Update password
                    new_hash = hash_password(new_password)
                    cursor.execute(
                        "UPDATE admin_users SET password_hash = ? WHERE username = ?",
                        (new_hash, username)
                    )
                    conn.commit()
                    st.success("✅ Password changed successfully!")
                    
                    # Clear form by rerunning
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("❌ Current password is incorrect")
    
    st.markdown("---")
    
    # Email Update Section
    st.markdown("##### Update Email Address")
    
    with st.form("update_email_form"):
        new_email = st.text_input("New Email Address", value=email or "", placeholder="admin@example.com")
        
        if st.form_submit_button("📧 Update Email", type="secondary"):
            if new_email and is_valid_email(new_email):
                cursor.execute(
                    "UPDATE admin_users SET email = ? WHERE username = ?",
                    (new_email, username)
                )
                conn.commit()
                st.success("✅ Email updated successfully!")
                time.sleep(1)
                st.rerun()
            elif new_email:
                st.error("❌ Please enter a valid email address")
            else:
                st.error("❌ Please enter an email address")
    
    st.markdown("---")
    
    # System Information
    st.markdown("##### System Information")
    
    # Database statistics
    cursor.execute("SELECT COUNT(*) FROM admin_users WHERE is_active = 1")
    active_admins = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM students WHERE is_active = 1")
    total_students = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM videos WHERE is_published = 1")
    total_videos = cursor.fetchone()[0]
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Active Admins", active_admins)
    with col2:
        st.metric("Total Students", total_students)
    with col3:
        st.metric("Published Videos", total_videos)
    with col4:
        st.metric("Database Tables", len(tables))
    
    # Backup/Export Option (placeholder for future enhancement)
    st.markdown("##### Database Management")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📊 Export Analytics", help="Export system analytics data"):
            st.info("📋 Analytics export functionality coming soon...")
    
    with col2:
        if st.button("🔄 System Status", help="Check system health"):
            st.success("✅ System is running normally")
            st.info(f"📅 Current server time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Security Settings
    st.markdown("---")
    st.markdown("##### Security Settings")
    
    # Session timeout setting
    current_timeout = APP_CONFIG.get('auto_logout_time', 1800)
    
    with st.form("security_settings_form"):
        st.write("**Session Timeout Settings**")
        timeout_minutes = st.slider(
            "Auto-logout after (minutes)", 
            min_value=15, 
            max_value=120, 
            value=current_timeout//60,
            help="Users will be automatically logged out after this period of inactivity"
        )
        
        if st.form_submit_button("⚙️ Update Security Settings"):
            # Update the timeout (in a real application, this would be saved to a config file)
            APP_CONFIG['auto_logout_time'] = timeout_minutes * 60
            st.success(f"✅ Session timeout updated to {timeout_minutes} minutes")
            st.info("ℹ️ Note: This setting will reset when the application restarts")
    
    conn.close()

#===========================================================================


# =============================================================================
# STUDENT INTERFACE
# =============================================================================

def show_student_interface():
    """Display student interface with video library and progress"""
    if check_session_timeout():
        return
    
    update_activity()
    
    student_name = st.session_state.user_data.get('name', 'Student')
    st.markdown(f"### Welcome, {student_name}!")
    
    # Logout button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col3:
        if st.button("🚪 Logout", type="secondary"):
            if st.session_state.get('confirm_logout', False):
                logout_user()
                st.success("Logged out successfully!")
                st.rerun()
            else:
                st.session_state.confirm_logout = True
                st.rerun()
    
    if st.session_state.get('confirm_logout', False):
        st.warning("Are you sure you want to logout?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, Logout"):
                logout_user()
                st.success("Logged out successfully!")
                st.rerun()
        with col2:
            if st.button("Cancel"):
                st.session_state.confirm_logout = False
                st.rerun()
        return
    
    # Navigation tabs
    tab_labels = [
        "📚 Video Library", 
        "▶️ Video Player", 
        "📊 My Progress", 
        "👤 Profile"
    ]
    active_tab = st.session_state.get('active_tab', 0)
    tabs = st.tabs(tab_labels)
    
    with tabs[0]:
        show_video_library()
    with tabs[1]:
        show_video_player()
    with tabs[2]:
        show_my_progress()
    with tabs[3]:
        show_student_profile()
    
    # After watching or selecting a video, set active_tab to 1 (Video Player)
    if st.session_state.get('current_video') and active_tab != 1:
        st.session_state.active_tab = 1
        st.rerun()
#=================================================================

def show_video_library():
    """Show video library for students (filtered by stream and class) with Watch button"""
    st.markdown("#### Video Library")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT stream_id, class_id FROM students WHERE student_id = ?",
        (st.session_state.user_id,)
    )
    student_info = cursor.fetchone()
    if not student_info:
        st.error("Student information not found.")
        return
    student_stream, student_class = student_info

    videos_df = pd.read_sql_query("""
        SELECT v.video_id, v.title, v.description, v.content_description, subm.subject_name, chm.chapter_name, v.video_link
        FROM videos v
        JOIN subject_master subm ON v.subject_id = subm.subject_id
        JOIN chapter_master chm ON v.chapter_id = chm.chapter_id
        WHERE v.stream_id = ? AND v.class_id = ? AND v.is_published = 1
        ORDER BY v.created_at DESC
    """, conn, params=(student_stream, student_class))

    if not videos_df.empty:
        st.markdown(f"**Found {len(videos_df)} videos for your Stream and Class**")
        for idx, row in videos_df.iterrows():
            col1, col2, col3, col4 = st.columns([2,2,2,2])
            with col1:
                st.write(f"**Subject:** {row['subject_name']}")
            with col2:
                st.write(f"**Chapter:** {row['chapter_name']}")
            with col3:
                st.write(f"**Title:** {row['title']}")
            with col4:
                if st.button("▶️ Watch", key=f"watch_{row['video_id']}"):
                    st.session_state.current_video = {
                        "video_id": row['video_id'],
                        "title": row['title'],
                        "description": row['description'],
                        "content_description": row['content_description'],
                        "subject_name": row['subject_name'],
                        "chapter_name": row['chapter_name'],
                        "video_link": row['video_link']
                    }
                    st.session_state.screen = 'student_interface'
                    st.session_state.active_tab = 1  # Set to Video Player tab
                    st.rerun()
    else:
        st.info("No videos found for your stream and class.")
    conn.close()

#==========================================================

def show_video_player():
    """Show video player interface"""
    st.markdown("#### Video Player")
    
    if st.session_state.current_video is None:
        st.info("Please select a video from the Video Library to start watching.")
        return
    
    video = st.session_state.current_video
    
    # Video details
    st.markdown(f"### {video['title']}")
    st.markdown(f"**Subject:** {video['subject_name']} | **Chapter:** {video['chapter_name']}")
    
    if video['description']:
        with st.expander("📖 Description"):
            st.markdown(video['description'])
    
    if video['content_description']:
        with st.expander("📝 Content Details"):
            st.markdown(video['content_description'])
    
    # Video player
    video_url = video['video_link']
    
    # Extract video ID for YouTube/Vimeo embedding
    if "youtube.com" in video_url or "youtu.be" in video_url:
        if "youtu.be" in video_url:
            video_id = video_url.split("/")[-1].split("?")[0]
        else:
            video_id = video_url.split("v=")[1].split("&")[0]
        
        embed_url = f"https://www.youtube.com/embed/{video_id}"
        st.markdown(f"""
            <iframe width="100%" height="500" src="{embed_url}" 
            frameborder="0" allowfullscreen></iframe>
        """, unsafe_allow_html=True)
    
    elif "vimeo.com" in video_url:
        video_id = video_url.split("/")[-1]
        embed_url = f"https://player.vimeo.com/video/{video_id}"
        st.markdown(f"""
            <iframe width="100%" height="500" src="{embed_url}" 
            frameborder="0" allowfullscreen></iframe>
        """, unsafe_allow_html=True)
    
    else:
        st.video(video_url)
    
    # Progress tracking
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("✅ Mark as Completed"):
            update_video_progress(video['video_id'], 100, True)
            st.success("Video marked as completed!")
            st.rerun()
    
    with col2:
        progress = st.slider("Set Progress", 0, 100, 
                           value=int(video.get('completion_percentage', 0)))
        if st.button("💾 Save Progress"):
            is_completed = progress == 100
            update_video_progress(video['video_id'], progress, is_completed)
            st.success(f"Progress saved: {progress}%")
            st.rerun()
    
    with col3:
        if st.button("⬅️ Back to Library"):
            st.session_state.current_video = None
            st.rerun()

def update_video_progress(video_id: str, completion_percentage: float, is_completed: bool):
    """Update video progress in database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if progress record exists
    cursor.execute(
        "SELECT id FROM user_progress WHERE student_id = ? AND video_id = ?",
        (st.session_state.user_id, video_id)
    )
    
    if cursor.fetchone():
        # Update existing record
        cursor.execute("""
            UPDATE user_progress 
            SET completion_percentage = ?, is_completed = ?, 
                last_watched = CURRENT_TIMESTAMP, watch_count = watch_count + 1
            WHERE student_id = ? AND video_id = ?
        """, (completion_percentage, is_completed, st.session_state.user_id, video_id))
    else:
        # Create new record
        cursor.execute("""
            INSERT INTO user_progress 
            (student_id, video_id, completion_percentage, is_completed, watch_count)
            VALUES (?, ?, ?, ?, 1)
        """, (st.session_state.user_id, video_id, completion_percentage, is_completed))
    
    conn.commit()
    conn.close()

def show_my_progress():
    """Show student's learning progress"""
    st.markdown("#### My Progress")
    
    conn = sqlite3.connect(DB_FILE)
    
    # Overall statistics
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM user_progress WHERE student_id = ?",
        (st.session_state.user_id,)
    )
    videos_watched = cursor.fetchone()[0]
    
    cursor.execute(
        "SELECT COUNT(*) FROM user_progress WHERE student_id = ? AND is_completed = 1",
        (st.session_state.user_id,)
    )
    videos_completed = cursor.fetchone()[0]
    
    cursor.execute(
        "SELECT AVG(completion_percentage) FROM user_progress WHERE student_id = ?",
        (st.session_state.user_id,)
    )
    avg_completion = cursor.fetchone()[0] or 0
    
    cursor.execute(
        "SELECT SUM(watched_duration) FROM user_progress WHERE student_id = ?",
        (st.session_state.user_id,)
    )
    total_watch_time = cursor.fetchone()[0] or 0
    
    # Display statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Videos Watched", videos_watched)
    
    with col2:
        st.metric("Completed", videos_completed)
    
    with col3:
        st.metric("Average Progress", f"{avg_completion:.1f}%")
    
    with col4:
        st.metric("Total Watch Time", f"{total_watch_time//60}m")
    
    # Recent progress
    st.markdown("##### Recent Activity")
    recent_progress = pd.read_sql_query("""
        SELECT v.title, v.subject_name, v.chapter_name, up.completion_percentage,
               up.is_completed, up.last_watched, up.watch_count
        FROM user_progress up
        JOIN (
            SELECT v.*, subm.subject_name, chm.chapter_name
            FROM videos v
            JOIN subject_master subm ON v.subject_id = subm.subject_id
            JOIN chapter_master chm ON v.chapter_id = chm.chapter_id
        ) v ON up.video_id = v.video_id
        WHERE up.student_id = ?
        ORDER BY up.last_watched DESC
        LIMIT 10
    """, conn, params=(st.session_state.user_id,))
    
    if not recent_progress.empty:
        #======================================================
        st.dataframe(
            recent_progress,
            column_config={
                "title": "Video Title",
                "subject_name": "Subject",
                "chapter_name": "Chapter",
                "completion_percentage": st.column_config.ProgressColumn(
                    "Progress",
                    min_value=0,
                    max_value=100,
                    format="%.1f%%"
                ),
                "is_completed": st.column_config.CheckboxColumn("Completed"),
                "watch_count": st.column_config.NumberColumn("Views"),
                "last_watched": st.column_config.TextColumn("Last Watched")  # Changed from DatetimeColumn
            },
            hide_index=True,
            use_container_width=True
        )

        #================================================================

    else:
        st.info("No progress data available. Start watching videos to see your progress!")
    
    # Subject-wise progress
    st.markdown("##### Subject-wise Progress")
    subject_progress = pd.read_sql_query("""
        SELECT subm.subject_name, 
               COUNT(up.video_id) as videos_watched,
               AVG(up.completion_percentage) as avg_progress,
               SUM(CASE WHEN up.is_completed = 1 THEN 1 ELSE 0 END) as completed_videos
        FROM user_progress up
        JOIN videos v ON up.video_id = v.video_id
        JOIN subject_master subm ON v.subject_id = subm.subject_id
        WHERE up.student_id = ?
        GROUP BY v.subject_id
        ORDER BY avg_progress DESC
    """, conn, params=(st.session_state.user_id,))
    
    if not subject_progress.empty:
        st.bar_chart(subject_progress.set_index('subject_name')['avg_progress'])
        
        st.dataframe(
            subject_progress,
            column_config={
                "subject_name": "Subject",
                "videos_watched": st.column_config.NumberColumn("Videos Watched"),
                "avg_progress": st.column_config.NumberColumn("Average Progress %", format="%.1f"),
                "completed_videos": st.column_config.NumberColumn("Completed Videos")
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No subject progress available yet.")
    
    conn.close()

def show_student_profile():
    """Show and edit student profile"""
    st.markdown("#### My Profile")
    
    # Get student information
    conn = sqlite3.connect(DB_FILE)
    student_df = pd.read_sql_query("""
        SELECT s.*, sm.stream_name, cm.class_name
        FROM students s
        LEFT JOIN stream_master sm ON s.stream_id = sm.stream_id
        LEFT JOIN class_master cm ON s.class_id = cm.class_id
        WHERE s.student_id = ?
    """, conn, params=(st.session_state.user_id,))
    
    if student_df.empty:
        st.error("Profile information not found.")
        return
    
    student = student_df.iloc[0]
    
    # Display profile information
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### Personal Information")
        st.write(f"**Name:** {student['name']}")
        st.write(f"**Mobile:** {student['mobile_no']}")
        st.write(f"**Date of Birth:** {student.get('dob', 'Not provided')}")
        st.write(f"**City:** {student.get('city', 'Not provided')}")
        st.write(f"**State:** {student.get('state', 'Not provided')}")
    
    with col2:
        st.markdown("##### Academic Information")
        st.write(f"**Stream:** {student.get('stream_name', 'Not assigned')}")
        st.write(f"**Class:** {student.get('class_name', 'Not assigned')}")
        st.write(f"**College:** {student.get('college_name', 'Not provided')}")
        st.write(f"**Registration Date:** {student['created_at'][:10]}")
        st.write(f"**Last Login:** {student.get('last_login', 'Never')}")
    
    # Address information
    if any([student.get('address_1'), student.get('address_2'), 
            student.get('address_3'), student.get('address_4')]):
        st.markdown("##### Address")
        address_parts = [
            student.get('address_1', ''),
            student.get('address_2', ''),
            student.get('address_3', ''),
            student.get('address_4', ''),
            student.get('city', ''),
            student.get('state', ''),
            student.get('pin_code', '')
        ]
        address = ', '.join([part for part in address_parts if part])
        st.write(address)
    
    # Account status
    st.markdown("##### Account Status")
    status_col1, status_col2 = st.columns(2)
    with status_col1:
        if student['is_active']:
            st.success("✅ Account Active")
        else:
            st.error("❌ Account Inactive")
    
    with status_col2:
        if student['video_enabled']:
            st.success("✅ Video Access Enabled")
        else:
            st.error("❌ Video Access Disabled")
    
    conn.close()

# =============================================================================
# MAIN APPLICATION CONTROLLER
# =============================================================================

def main():
    """Main application controller"""
    #=====================================================
# Add this code to your main() function in tutorial_video_app.py
# Place it right after your function definition, before any other Streamlit code


    # Mobile-responsive CSS - Add this at the very beginning of your main() function
    st.markdown("""
        <style>
        /* Mobile responsiveness */
        @media (max-width: 768px) {
            .main > div {
                padding: 0.5rem;
            }
            .stButton > button {
                height: 3rem;
                font-size: 1.1rem;
            }
            .welcome-title {
                font-size: 2rem !important;
            }
        }
       
        /* Better mobile navigation */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.2rem;
        }
       
        .stTabs [data-baseweb="tab"] {
            padding: 0.5rem 1rem;
            font-size: 0.9rem;
        }
       
        /* Mobile form optimization */
        .stTextInput > div > div > input {
            font-size: 1rem;
        }
       
        /* Better mobile tables */
        .dataframe {
            font-size: 0.8rem;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Your existing code continues here...
    # (Keep all your current app code below this CSS section)

    #=====================================================
    st.set_page_config(
        page_title=APP_CONFIG['app_name'],
        page_icon="📚",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Initialize database and session
    init_database()
    initialize_session()
    
    # Custom CSS for better styling
    st.markdown("""
        <style>
        .main > div {
            padding: 1rem;
        }
        .stButton > button {
            width: 100%;
        }
        .metric-container {
            background: #f0f2f6;
            padding: 1rem;
            border-radius: 0.5rem;
            margin: 0.5rem 0;
        }
        .video-card {
            border: 1px solid #e0e0e0;
            border-radius: 0.5rem;
            padding: 1rem;
            margin: 0.5rem 0;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Route to appropriate screen
    if st.session_state.screen == 'welcome':
        show_welcome_screen()
    
    elif st.session_state.screen == 'login_selection':
        show_login_selection()
    
    elif st.session_state.screen == 'admin_login':
        show_admin_login()
    
    elif st.session_state.screen == 'student_login':
        show_student_login()
    
    elif st.session_state.screen == 'admin_dashboard':
        if st.session_state.is_authenticated and st.session_state.user_type == 'admin':
            show_admin_dashboard()
        else:
            st.error("Unauthorized access. Please login first.")
            st.session_state.screen = 'welcome'
            st.rerun()
    
    elif st.session_state.screen == 'student_interface':
        if st.session_state.is_authenticated and st.session_state.user_type == 'student':
            show_student_interface()
        else:
            st.error("Unauthorized access. Please login first.")
            st.session_state.screen = 'welcome'
            st.rerun()
    elif st.session_state.screen == 'student_registration':
        show_student_registration()

    else:
        st.session_state.screen = 'welcome'
        st.rerun()

# =============================================================================
# APPLICATION RUNNER
# =============================================================================

if __name__ == "__main__":
    main()