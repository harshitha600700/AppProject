# 🎮 Gamified Habit Tracker

An interactive, gamified habit tracking application built with Streamlit that helps you build and maintain good habits while discouraging bad ones.

## Features

### 🎯 Gamification System
- **XP System**: Earn 10 XP per hour for good habits, lose 10 XP per hour for social media
- **Leveling**: Progress through 10 levels with increasing XP requirements
- **Badges**: Unlock achievements for streaks, levels, and milestones
- **Progress Tracking**: Visual progress bars showing XP toward next level

### 📊 Interactive UI
- **Modern Streamlit Interface**: Beautiful, responsive design with gradient styling
- **5 Main Pages**:
  - 📝 **Log Entry**: Quick daily logging with visual feedback
  - ➕ **Add Habit**: Create new habits to track
  - 📊 **Dashboard**: Overview with statistics
  - 🔥 **Streaks**: Visual streak display with fire emojis
  - 📈 **Analytics**: Interactive charts and visualizations

### 🎨 Visual Enhancements
- **Plotly Charts**: Interactive charts (replacing static matplotlib)
- **Color-coded Streaks**: Fire emojis for long streaks
- **Progress Indicators**: Real-time metrics and progress bars
- **Achievement Notifications**: Confetti animations when unlocking achievements

### 🗄️ Database Compatibility
- **SQLite Database**: Same database structure as original
- **Same Stack**: pandas, matplotlib, seaborn (preserved)
- **Gamification Table**: New table for XP and badges
- **All Original Functions**: Preserved and adapted for UI

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/harshitha600700/AppProject.git
   cd AppProject
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   streamlit run app.py
   ```

The app will open in your browser automatically at `http://localhost:8501`

## Usage

1. **Add Habits**: Use the "➕ Add Habit" page to create new habits
2. **Log Daily Entries**: Use "📝 Log Entry" to log your daily habits
3. **Track Progress**: View your XP, level, and streaks on the dashboard
4. **View Analytics**: Check the "📈 Analytics" page for visual insights
5. **Maintain Streaks**: Keep logging daily to build and maintain streaks

## How It Works

- **Good Habits**: Earn 10 XP per hour logged
- **Social Media**: Lose 10 XP per hour (discourages excessive usage)
- **Streak Bonuses**: Earn bonus XP for maintaining streaks (max 7 days per habit)
- **Leveling**: Progress through levels as you earn XP
- **Achievements**: Unlock badges for milestones and consistency

## Requirements

- Python 3.7+
- Streamlit
- pandas
- matplotlib
- seaborn
- plotly

See `requirements.txt` for specific versions.

## Platform Support

✅ **Windows** - Fully supported  
✅ **macOS** - Fully supported  
✅ **Linux** - Fully supported

## License

This project is open source and available for personal use.

## Contributing

Feel free to fork this project and submit pull requests for any improvements!
