import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

DB_NAME = "habits.db"
CSV_NAME = "habit_log.csv"

# Gamification constants
XP_PER_HOUR = 10
STREAK_BONUS = 5
LEVEL_UP_XP = [0, 100, 250, 500, 1000, 2000, 3500, 5000, 7500, 10000]  # XP needed for each level

def connect():
    conn = sqlite3.connect(DB_NAME, timeout=10.0, check_same_thread=False)
    # Try to enable WAL mode, but don't fail if database is locked
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
    except sqlite3.OperationalError:
        # If WAL can't be set, continue with default mode
        pass
    return conn

def create_table():
    conn = connect()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS habit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                social_media REAL DEFAULT 0
            );
        """)

        # Create gamification table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gamification (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_xp INTEGER DEFAULT 0,
                current_level INTEGER DEFAULT 1,
                badges TEXT DEFAULT '',
                last_updated TEXT
            );
        """)
        
        # Initialize gamification if empty
        cursor.execute("SELECT COUNT(*) FROM gamification")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO gamification (total_xp, current_level, badges, last_updated) VALUES (0, 1, '', ?)", 
                          (datetime.now().strftime("%Y-%m-%d"),))

        conn.commit()
    finally:
        conn.close()

def update_csv():
    conn = connect()
    try:
        df = pd.read_sql_query("SELECT * FROM habit_log ORDER BY date", conn)
    finally:
        conn.close()
    df.to_csv(CSV_NAME, index=False)

def add_habit(habit_name):
    habit = habit_name.strip().replace(" ", "_")

    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(f"ALTER TABLE habit_log ADD COLUMN {habit} REAL DEFAULT 0;")
        conn.commit()
        update_csv()
        return True, f"🎉 Habit '{habit}' added!"
    except sqlite3.OperationalError:
        return False, "⚠️ Habit already exists or invalid name."
    finally:
        conn.close()

def add_entry(date_str, habit_values):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return False, "❗ Invalid date format."

    conn = connect()
    cursor = conn.cursor()
    
    try:
        cursor.execute("PRAGMA table_info(habit_log);")
        columns = [col[1] for col in cursor.fetchall() if col[1] != "id"]

        # Check if entry exists for this date
        cursor.execute("SELECT 1 FROM habit_log WHERE date=?", (date_str,))
        entry_exists = cursor.fetchone() is not None

        if entry_exists:
            # For updates: only update habits with values > 0, keep others as they were
            # First, get existing values
            cursor.execute(f"SELECT * FROM habit_log WHERE date=?", (date_str,))
            existing_row = cursor.fetchone()
            existing_dict = {}
            if existing_row:
                for i, col in enumerate(columns):
                    existing_dict[col] = existing_row[i + 1]  # +1 to skip id column
            
            # Build update statement - update habits that have new values
            # For social_media, always update if provided (even if 0) to track and penalize usage
            # For other habits, only update if value > 0
            update_parts = []
            update_values = []
            for col in columns:
                if col == "date":
                    continue
                if col in habit_values:
                    if col == "social_media":
                        # Always update social_media if provided (to track any usage, even small amounts)
                        update_parts.append(f"{col} = ?")
                        update_values.append(habit_values[col])
                    elif habit_values[col] > 0:
                        # For other habits, only update if value > 0
                        update_parts.append(f"{col} = ?")
                        update_values.append(habit_values[col])
                # If habit not in habit_values or value is 0 (for non-social_media), keep existing value
            
            if update_parts:
                update_values.append(date_str)
                cursor.execute(f"UPDATE habit_log SET {', '.join(update_parts)} WHERE date = ?", update_values)
                message = f"✅ Entry updated for {date_str}!"
            else:
                message = f"ℹ️ Entry for {date_str} exists. No new values to update."
        else:
            # Insert new entry - use provided values or 0
            values = {"date": date_str}
            for col in columns:
                if col == "date":
                    continue
                values[col] = habit_values.get(col, 0.0)
            
            col_names = ", ".join(values.keys())
            placeholders = ", ".join(["?"] * len(values))
            cursor.execute(f"INSERT INTO habit_log ({col_names}) VALUES ({placeholders})", list(values.values()))
            message = f"✅ Entry added for {date_str}!"

        conn.commit()
    finally:
        conn.close()

    # Calculate and update XP (after closing the connection)
    # Use habit_values directly - these are the values the user entered and were just saved
    
    # Good habits add XP, social_media reduces XP (from 0 hours, any value > 0 reduces XP)
    good_habits_hours = sum(v for k, v in habit_values.items() if k != "social_media" and v > 0)
    # Get social_media hours - use the value from habit_values if provided, otherwise 0
    social_media_hours = habit_values.get("social_media", 0)
    
    # Calculate XP - social media reduces XP for ANY hours > 0 (even 0.1 hours = 1 XP lost)
    # Use round() to handle fractional hours properly
    xp_from_good_habits = round(good_habits_hours * XP_PER_HOUR)
    xp_lost_from_social_media = round(social_media_hours * XP_PER_HOUR) if social_media_hours > 0 else 0
    
    # Calculate base XP (good habits minus social media penalty)
    xp_earned = xp_from_good_habits - xp_lost_from_social_media
    
    # Add streak bonus ONLY for good habits that were actually logged in this entry
    # Only count streaks for habits that have hours > 0 in this entry
    if good_habits_hours > 0:
        streaks = calculate_streaks_dict()
        # Only get streak bonus for habits that were logged in this entry
        logged_habits = [k for k, v in habit_values.items() if k != "social_media" and v > 0]
        streak_bonus = 0
        for habit in logged_habits:
            if habit in streaks and streaks[habit] > 0:
                # Add bonus based on streak length (max 7 days = 35 bonus XP per habit)
                streak_bonus += min(streaks[habit], 7) * STREAK_BONUS
        xp_earned += streak_bonus
    
    # Update XP (separate connection) - can be positive or negative
    # Always update if there's any XP change OR if social media was used (even if net is 0)
    if xp_earned != 0:
        update_xp(xp_earned)
        if xp_earned > 0:
            message += f" Earned {xp_earned} XP! 🎮"
        else:
            message += f" Lost {abs(xp_earned)} XP from social media 😔"
    elif social_media_hours > 0:
        # Social media was used but net XP is 0 (good habits canceled it out)
        # Still update to record the entry, and show the loss
        update_xp(xp_earned)  # This will be 0, but we still update to record
        if xp_from_good_habits > 0:
            message += f" Social media canceled out {xp_lost_from_social_media} XP 😔"
        else:
            message += f" Lost {xp_lost_from_social_media} XP from social media 😔"
    
    # Update CSV
    update_csv()

    return True, message

def get_habits():
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(habit_log);")
        columns = [col[1] for col in cursor.fetchall() if col[1] not in ("id", "date")]
        return columns
    finally:
        conn.close()

def view_table():
    conn = connect()
    try:
        df = pd.read_sql_query("SELECT * FROM habit_log ORDER BY date", conn)
        return df
    finally:
        conn.close()

def calculate_streaks_dict():
    conn = connect()
    try:
        df = pd.read_sql_query("SELECT * FROM habit_log ORDER BY date", conn)
    finally:
        conn.close()

    if df.empty:
        return {}

    df["date"] = pd.to_datetime(df["date"])

    streaks = {}
    # Exclude social_media from streaks as it's not a good habit
    habit_cols = [c for c in df.columns if c not in ("id", "date", "social_media")]

    for habit in habit_cols:
        habit_df = df[["date", habit]].sort_values("date", ascending=False)
        streak = 0
        if len(habit_df) > 0:
            expected = habit_df.iloc[0]["date"]

            for _, row in habit_df.iterrows():
                if row["date"] == expected and row[habit] > 0:
                    streak += 1
                    expected -= timedelta(days=1)
                else:
                    break

        streaks[habit] = streak

    return streaks

def update_xp(xp_earned):
    conn = connect()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT total_xp, current_level FROM gamification ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
        
        if result:
            current_xp, current_level = result
            new_xp = max(0, current_xp + xp_earned)  # Ensure XP doesn't go below 0
            
            # Calculate new level based on XP (can go down if XP decreases)
            new_level = 1
            for i, xp_threshold in enumerate(LEVEL_UP_XP):
                if new_xp >= xp_threshold:
                    new_level = i + 1
                else:
                    break
            
            cursor.execute("""
                UPDATE gamification 
                SET total_xp = ?, current_level = ?, last_updated = ?
                WHERE id = (SELECT MAX(id) FROM gamification)
            """, (new_xp, new_level, datetime.now().strftime("%Y-%m-%d")))
            
            conn.commit()
    finally:
        conn.close()

def get_gamification_stats():
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT total_xp, current_level, badges FROM gamification ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
    finally:
        conn.close()
    
    if result:
        total_xp, level, badges = result
        # Calculate XP for current level and next level
        current_level_xp = LEVEL_UP_XP[level - 1] if level > 0 else 0
        next_level_xp = LEVEL_UP_XP[level] if level < len(LEVEL_UP_XP) else LEVEL_UP_XP[-1]
        xp_progress = total_xp - current_level_xp
        xp_needed = next_level_xp - current_level_xp
        
        return {
            "total_xp": total_xp,
            "level": level,
            "badges": badges.split(",") if badges else [],
            "xp_progress": xp_progress,
            "xp_needed": xp_needed,
            "progress_percent": min(100, (xp_progress / xp_needed * 100) if xp_needed > 0 else 100)
        }
    return {
        "total_xp": 0,
        "level": 1,
        "badges": [],
        "xp_progress": 0,
        "xp_needed": 100,
        "progress_percent": 0
    }

def check_achievements():
    """Check and award achievements based on user progress"""
    conn = connect()
    try:
        df = pd.read_sql_query("SELECT * FROM habit_log", conn)
    finally:
        conn.close()
    
    if df.empty:
        return []
    
    achievements = []
    streaks = calculate_streaks_dict()
    stats = get_gamification_stats()
    
    # Streak achievements (only for good habits, not social_media)
    good_habit_streaks = {k: v for k, v in streaks.items() if k != "social_media"}
    max_streak = max(good_habit_streaks.values()) if good_habit_streaks else 0
    if max_streak >= 7 and "🔥 7-Day Streak" not in stats["badges"]:
        achievements.append("🔥 7-Day Streak")
    if max_streak >= 30 and "💪 30-Day Streak" not in stats["badges"]:
        achievements.append("💪 30-Day Streak")
    if max_streak >= 100 and "👑 100-Day Streak" not in stats["badges"]:
        achievements.append("👑 100-Day Streak")
    
    # Level achievements
    if stats["level"] >= 5 and "⭐ Level 5" not in stats["badges"]:
        achievements.append("⭐ Level 5")
    if stats["level"] >= 10 and "🌟 Level 10" not in stats["badges"]:
        achievements.append("🌟 Level 10")
    
    # Total hours achievements (only for good habits, not social_media)
    good_habit_cols = [c for c in df.columns if c not in ("id", "date", "social_media")]
    total_good_hours = df[good_habit_cols].sum().sum() if good_habit_cols else 0
    if total_good_hours >= 100 and "📚 100 Hours" not in stats["badges"]:
        achievements.append("📚 100 Hours")
    if total_good_hours >= 500 and "🎓 500 Hours" not in stats["badges"]:
        achievements.append("🎓 500 Hours")
    
    # Update badges if new achievements
    if achievements:
        conn = connect()
        try:
            cursor = conn.cursor()
            current_badges = stats["badges"]
            all_badges = list(set(current_badges + achievements))
            cursor.execute("""
                UPDATE gamification 
                SET badges = ?
                WHERE id = (SELECT MAX(id) FROM gamification)
            """, (",".join(all_badges),))
            conn.commit()
        finally:
            conn.close()
    
    return achievements

def create_pie_chart():
    conn = connect()
    try:
        df = pd.read_sql_query("SELECT * FROM habit_log", conn)
    finally:
        conn.close()

    if df.empty:
        return None

    habit_cols = [c for c in df.columns if c not in ("id", "date")]
    totals = df[habit_cols].sum()
    
    fig = px.pie(values=totals.values, names=totals.index, 
                 title="🎯 Total Time Breakdown Across Habits",
                 color_discrete_sequence=px.colors.qualitative.Set3)
    return fig

def create_bar_chart(habit):
    conn = connect()
    try:
        df = pd.read_sql_query("SELECT * FROM habit_log ORDER BY date", conn)
    finally:
        conn.close()

    if habit not in df.columns:
        return None

    df["date"] = pd.to_datetime(df["date"])
    
    fig = px.bar(df, x="date", y=habit, 
                 title=f"📊 Time Spent on {habit} Over Time",
                 labels={"date": "Date", habit: "Hours"},
                 color=habit,
                 color_continuous_scale="Viridis")
    fig.update_layout(xaxis_tickangle=-45)
    return fig

def create_comparison_chart():
    conn = connect()
    try:
        df = pd.read_sql_query("SELECT * FROM habit_log", conn)
    finally:
        conn.close()

    if df.empty:
        return None

    df["date"] = pd.to_datetime(df["date"])
    habit_cols = [c for c in df.columns if c not in ("id", "date", "social_media")]
    df['total_habit_time'] = df[habit_cols].sum(axis=1)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['date'], y=df['total_habit_time'], 
                        name='Total Habit Time', marker_color='#2ecc71'))
    fig.add_trace(go.Bar(x=df['date'], y=df['social_media'], 
                        name='Social Media', marker_color='#e74c3c', opacity=0.7))
    
    fig.update_layout(title="⚖️ Daily Habit Time vs Social Media Usage",
                     xaxis_title="Date",
                     yaxis_title="Hours",
                     xaxis_tickangle=-45,
                     barmode='group')
    return fig

# Streamlit UI
def main():
    st.set_page_config(
        page_title="🎮 Gamified Habit Tracker",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS for gamification
    st.markdown("""
    <style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
    }
    .xp-display {
        font-size: 1.5rem;
        font-weight: bold;
        color: #f39c12;
    }
    .level-badge {
        display: inline-block;
        padding: 0.5rem 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 20px;
        font-weight: bold;
        font-size: 1.2rem;
    }
    .streak-fire {
        color: #ff6b6b;
        font-size: 1.5rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    create_table()
    
    # Header
    st.markdown('<h1 class="main-header">🎮 Gamified Habit Tracker</h1>', unsafe_allow_html=True)
    
    # Get gamification stats
    stats = get_gamification_stats()
    achievements = check_achievements()
    
    # Show new achievements
    if achievements:
        st.success(f"🎉 New Achievement Unlocked: {', '.join(achievements)}")
    
    # Top bar with XP and Level
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f'<div class="level-badge">Level {stats["level"]}</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown(f'<div class="xp-display">⭐ {stats["total_xp"]} XP</div>', unsafe_allow_html=True)
    
    with col3:
        progress = stats["progress_percent"] / 100
        st.progress(progress, text=f"Progress to Level {stats['level'] + 1}: {stats['xp_progress']}/{stats['xp_needed']} XP")
    
    with col4:
        if stats["badges"]:
            st.markdown("**🏆 Badges:**")
            st.markdown(" ".join(stats["badges"]))
    
    st.divider()
    
    # Sidebar
    with st.sidebar:
        st.header("🎯 Navigation")
        page = st.radio("Choose a page:", 
                       ["📝 Log Entry", "➕ Add Habit", "📊 Dashboard", "🔥 Streaks", "📈 Analytics"])
    
    # Main content based on page selection
    if page == "📝 Log Entry":
        st.header("📝 Log Your Daily Habits")
        
        habits = get_habits()
        if not habits:
            st.warning("⚠️ No habits found. Add a habit first!")
        else:
            col1, col2 = st.columns(2)
            
            with col1:
                selected_date = st.date_input("📅 Select Date", value=datetime.now())
                date_str = selected_date.strftime("%Y-%m-%d")
            
            with col2:
                st.info("💡 Tip: Logging daily earns you XP and maintains your streaks!")
            
            habit_values = {}
            st.subheader("⏰ Enter Hours for Each Habit")
            
            cols = st.columns(3)
            for i, habit in enumerate(habits):
                with cols[i % 3]:
                    habit_values[habit] = st.number_input(
                        f"{habit.replace('_', ' ').title()}",
                        min_value=0.0,
                        max_value=24.0,
                        value=0.0,
                        step=0.5,
                        key=f"habit_{habit}"
                    )
            
            if st.button("💾 Save Entry", type="primary", use_container_width=True):
                success, message = add_entry(date_str, habit_values)
                if success:
                    st.success(message)
                    st.balloons()
                    st.rerun()
                else:
                    st.error(message)
    
    elif page == "➕ Add Habit":
        st.header("➕ Add New Habit")
        
        habit_name = st.text_input("Enter habit name:", placeholder="e.g., Exercise, Reading, Meditation")
        
        if st.button("✨ Create Habit", type="primary"):
            if habit_name:
                success, message = add_habit(habit_name)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.warning("Please enter a habit name!")
    
    elif page == "📊 Dashboard":
        st.header("📊 Your Habit Dashboard")
        
        df = view_table()
        if df.empty:
            st.info("📝 No entries yet. Start logging your habits!")
        else:
            # Display table
            st.subheader("📋 All Entries")
            display_df = df.drop(columns=["id"] if "id" in df.columns else [])
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Quick stats
            st.subheader("📈 Quick Statistics")
            habit_cols = [c for c in df.columns if c not in ("id", "date")]
            
            if habit_cols:
                col1, col2, col3, col4 = st.columns(4)
                
                total_hours = df[habit_cols].sum().sum()
                total_days = len(df)
                avg_daily = total_hours / total_days if total_days > 0 else 0
                active_habits = sum(1 for col in habit_cols if df[col].sum() > 0)
                
                with col1:
                    st.metric("📚 Total Hours", f"{total_hours:.1f}")
                with col2:
                    st.metric("📅 Days Logged", total_days)
                with col3:
                    st.metric("📊 Avg Daily Hours", f"{avg_daily:.1f}")
                with col4:
                    st.metric("🎯 Active Habits", active_habits)
    
    elif page == "🔥 Streaks":
        st.header("🔥 Your Streaks")
        
        streaks = calculate_streaks_dict()
        
        if not streaks:
            st.info("📝 No streaks yet. Start logging to build your streaks!")
        else:
            # Display streaks with visual indicators
            cols = st.columns(3)
            for i, (habit, streak) in enumerate(sorted(streaks.items(), key=lambda x: x[1], reverse=True)):
                with cols[i % 3]:
                    # Fire emoji based on streak length
                    if streak >= 30:
                        emoji = "👑"
                        color = "#f1c40f"
                    elif streak >= 7:
                        emoji = "🔥"
                        color = "#e74c3c"
                    elif streak >= 3:
                        emoji = "⭐"
                        color = "#3498db"
                    else:
                        emoji = "🌱"
                        color = "#2ecc71"
                    
                    st.markdown(f"""
                    <div style="padding: 1rem; border-radius: 10px; background: linear-gradient(135deg, {color}15 0%, {color}05 100%); border: 2px solid {color};">
                        <h3>{emoji} {habit.replace('_', ' ').title()}</h3>
                        <h2 style="color: {color}; margin: 0;">{streak} days</h2>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Streak chart
            st.subheader("📊 Streak Visualization")
            streak_df = pd.DataFrame(list(streaks.items()), columns=["Habit", "Streak"])
            streak_df = streak_df.sort_values("Streak", ascending=True)
            
            fig = px.bar(streak_df, x="Streak", y="Habit", orientation="h",
                        title="🔥 Current Streaks",
                        color="Streak",
                        color_continuous_scale="Reds")
            st.plotly_chart(fig, use_container_width=True)
    
    elif page == "📈 Analytics":
        st.header("📈 Analytics & Visualizations")
        
        df = view_table()
        if df.empty:
            st.info("📝 No data available for analytics. Start logging your habits!")
        else:
            # Pie chart
            st.subheader("🎯 Time Distribution")
            pie_fig = create_pie_chart()
            if pie_fig:
                st.plotly_chart(pie_fig, use_container_width=True)
            
            # Habit selection for bar chart
            habits = get_habits()
            if habits:
                st.subheader("📊 Individual Habit Progress")
                selected_habit = st.selectbox("Select a habit to view:", habits)
                bar_fig = create_bar_chart(selected_habit)
                if bar_fig:
                    st.plotly_chart(bar_fig, use_container_width=True)
            
            # Comparison chart
            if "social_media" in df.columns:
                st.subheader("⚖️ Habit Time vs Social Media")
                comp_fig = create_comparison_chart()
                if comp_fig:
                    st.plotly_chart(comp_fig, use_container_width=True)

if __name__ == "__main__":
    main()

