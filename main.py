"""
Life Gamification System - v3 Full Rewrite
Запуск: streamlit run main.py
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import json
import plotly.express as px
import base64

# ============= CONFIG =============
DB_PATH = Path.home() / ".gamify" / "xp.db"
IMAGES_PATH = Path.home() / ".gamify" / "shop_images"
NIKOCOIN_PATH = Path.home() / ".gamify" / "nikocoin.png"
DB_PATH.parent.mkdir(exist_ok=True)
IMAGES_PATH.mkdir(exist_ok=True)

def get_nikocoin_icon():
    """Возвращает иконку валюты - либо кастомную, либо эмодзи"""
    if NIKOCOIN_PATH.exists():
        return f'<img src="data:image/png;base64,{get_image_base64(NIKOCOIN_PATH)}" width="40" style="vertical-align: middle;">'
    return "🪙"

def get_image_base64(image_path):
    """Конвертирует изображение в base64 для встраивания в HTML"""
    import base64
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ============= DATABASE =============
def get_connection():
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)

def init_database():
    conn = get_connection()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS fronts (
        id INTEGER PRIMARY KEY,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        coef REAL NOT NULL DEFAULT 1.0,
        weight REAL NOT NULL DEFAULT 1.0,
        tier_daily REAL DEFAULT 1.0,
        tier_weekly REAL DEFAULT 1.2,
        tier_sprint REAL DEFAULT 1.5,
        tier_campaign REAL DEFAULT 2.0,
        diff_1 REAL DEFAULT 0.5,
        diff_2 REAL DEFAULT 1.0,
        diff_3 REAL DEFAULT 1.5,
        diff_4 REAL DEFAULT 2.0,
        diff_5 REAL DEFAULT 3.0
    )''')

    # Миграция: добавляем новые колонки если их нет
    try:
        c.execute("SELECT tier_daily FROM fronts LIMIT 1")
    except sqlite3.OperationalError:
        for col in ['tier_daily', 'tier_weekly', 'tier_sprint', 'tier_campaign',
                    'diff_1', 'diff_2', 'diff_3', 'diff_4', 'diff_5']:
            try:
                default_val = {'tier_daily': 1.0, 'tier_weekly': 1.2, 'tier_sprint': 1.5,
                              'tier_campaign': 2.0, 'diff_1': 0.5, 'diff_2': 1.0,
                              'diff_3': 1.5, 'diff_4': 2.0, 'diff_5': 3.0}[col]
                c.execute(f"ALTER TABLE fronts ADD COLUMN {col} REAL DEFAULT {default_val}")
            except sqlite3.OperationalError:
                pass
        conn.commit()

    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY,
        date TEXT NOT NULL,
        front_code TEXT NOT NULL,
        tier TEXT NOT NULL,
        piece_type TEXT NOT NULL,
        note TEXT,
        minutes INTEGER DEFAULT 0,
        difficulty INTEGER DEFAULT 2,
        status TEXT NOT NULL,
        total_xp REAL DEFAULT 0,
        coins_earned REAL DEFAULT 0
    )''')

    # Миграция: добавляем coins_earned если его нет
    try:
        c.execute("SELECT coins_earned FROM tasks LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE tasks ADD COLUMN coins_earned REAL DEFAULT 0")
        conn.commit()

    c.execute('''CREATE TABLE IF NOT EXISTS level_thresholds (
        level INTEGER PRIMARY KEY,
        xp_threshold INTEGER NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS piece_types (
        id INTEGER PRIMARY KEY,
        front_code TEXT NOT NULL,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        tier TEXT NOT NULL,
        base_xp REAL NOT NULL
    )''')

    # Миграция: добавляем tier если его нет
    try:
        c.execute("SELECT tier FROM piece_types LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE piece_types ADD COLUMN tier TEXT DEFAULT 'Daily'")
        conn.commit()

    c.execute('''CREATE TABLE IF NOT EXISTS rewards (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        cost_coins INTEGER NOT NULL,
        image_path TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY,
        date TEXT NOT NULL,
        reward_id INTEGER NOT NULL,
        coins_spent INTEGER NOT NULL,
        FOREIGN KEY(reward_id) REFERENCES rewards(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS user_prefs (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''')

    # Никоины (отдельная таблица для отслеживания бонусов)
    c.execute('''CREATE TABLE IF NOT EXISTS coins_log (
        id INTEGER PRIMARY KEY,
        date TEXT NOT NULL,
        source TEXT NOT NULL,
        amount REAL NOT NULL,
        description TEXT
    )''')

    conn.commit()
    return conn

def seed_data(conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM fronts")
    if c.fetchone()[0] > 0:
        return

    # Fronts с индивидуальными множителями
    fronts = [
        ('guitar', 'Гитара', 0.9, 0.9, 1.0, 1.2, 1.5, 2.0, 0.5, 1.0, 1.5, 2.0, 3.0),
        ('english', 'Английский', 1.1, 1.1, 1.0, 1.2, 1.5, 2.0, 0.5, 1.0, 1.5, 2.0, 3.0),
        ('sport', 'Спорт', 1.0, 1.0, 1.0, 1.2, 1.5, 2.0, 0.5, 1.0, 1.5, 2.0, 3.0),
        ('business', 'Новый бизнес', 1.4, 1.4, 1.0, 1.2, 1.5, 2.0, 0.5, 1.0, 1.5, 2.0, 3.0),
        ('books', 'Книги', 0.8, 0.8, 1.0, 1.2, 1.5, 2.0, 0.5, 1.0, 1.5, 2.0, 3.0),
        ('brain', 'Когнитивка', 1.2, 1.2, 1.0, 1.2, 1.5, 2.0, 0.5, 1.0, 1.5, 2.0, 3.0),
    ]
    c.executemany("""INSERT INTO fronts (code, name, coef, weight, tier_daily, tier_weekly, tier_sprint, tier_campaign,
                     diff_1, diff_2, diff_3, diff_4, diff_5) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", fronts)

    # Полные списки задач из ТЗ
    pieces = [
        # Гитара
        ('guitar', 'GuitarWarmup', 'Разминка 10-15 мин', 'Daily', 5),
        ('guitar', 'GuitarChunk', 'Кусок песни (риф/куплет)', 'Daily', 10),
        ('guitar', 'GuitarBlend', 'Сведение кусков', 'Daily', 15),
        ('guitar', 'GuitarPart', 'Цельная часть (куплет/припев)', 'Weekly', 50),
        ('guitar', 'GuitarRecording', 'Запись 30-60 сек', 'Weekly', 20),
        ('guitar', 'GuitarReviewPlan', 'Разбор ошибок + план', 'Weekly', 10),
        ('guitar', 'GuitarFullSong', 'Песня целиком без остановки', 'Sprint', 200),
        ('guitar', 'GuitarTempo10', 'Темп +10 BPM', 'Sprint', 50),
        ('guitar', 'GuitarSet2', 'Сет из 2 песен', 'Campaign', 400),
        ('guitar', 'GuitarSet3', 'Сет из 3 песен', 'Campaign', 600),
        ('guitar', 'GuitarDemo', 'Демка 5-7 мин', 'Campaign', 300),
        ('guitar', 'GuitarLive', 'Выступление/стрим', 'Campaign', 500),

        # Английский
        ('english', 'EngVocab10', '10-15 новых слов', 'Daily', 10),
        ('english', 'EngRead10', '10 мин чтение', 'Daily', 8),
        ('english', 'EngListen10', 'Сериал с субами 10 мин', 'Daily', 6),
        ('english', 'EngSpeak5', '5-10 мин разговор', 'Daily', 12),
        ('english', 'EngReadOrig10', '10 стр сложной книги', 'Daily', 15),
        ('english', 'EngReadOrig20', '20 стр сложной книги', 'Daily', 30),
        ('english', 'EngWordPack50', '50 слов закреплено (90%+)', 'Weekly', 50),
        ('english', 'EngListeningTest', '30 мин без субов', 'Weekly', 40),
        ('english', 'EngSpeakingDrill', 'Монолог 2-3 мин', 'Weekly', 60),
        ('english', 'EngEssay200', 'Эссе 150-200 слов', 'Weekly', 80),
        ('english', 'EngBookChapter', 'Глава + пересказ', 'Sprint', 150),
        ('english', 'EngInterviewSim', 'Интервью 5-7 мин', 'Sprint', 200),
        ('english', 'EngEssay3Pack', '3 эссе по 200-250 слов', 'Sprint', 250),
        ('english', 'EngTestSim', 'Пробный тест C1', 'Sprint', 300),
        ('english', 'EngBookOrigChapter', 'Глава сложной книги', 'Sprint', 200),
        ('english', 'EngBigRead', 'Книга 200+ стр', 'Campaign', 600),
        ('english', 'EngBigTalk', 'Разговор 30-40 мин с носителем', 'Campaign', 800),
        ('english', 'EngBigWrite', '3-5 эссе с разбором', 'Campaign', 500),
        ('english', 'EngSeriesFull', 'Сезон 10+ серий', 'Campaign', 700),
        ('english', 'EngBookOrigFull', 'Полная книга в оригинале', 'Campaign', 800),

        # Спорт
        ('sport', 'SportWarmup', 'Разминка 10-15 мин', 'Daily', 5),
        ('sport', 'SportStrength', 'Силовая 40-60 мин', 'Daily', 40),
        ('sport', 'SportConditioning', 'Функционал 20-30 мин', 'Daily', 50),
        ('sport', 'SportMobility', 'Растяжка/йога 10 мин', 'Daily', 8),
        ('sport', 'SportRecovery', 'Активное восстановление 20 мин', 'Daily', 10),
        ('sport', 'SportWeek3', '2 силовые + 1 функционал', 'Weekly', 50),
        ('sport', 'SportProgressTest', 'Тест веса/повторов', 'Weekly', 30),
        ('sport', 'SportCardioChallenge', '+10% дистанции/интервал', 'Weekly', 40),
        ('sport', 'SportStrengthProgress', '+2.5-5 кг или +2-3 повтора', 'Sprint', 200),
        ('sport', 'SportConditioningNew', 'Новый комплекс без остановки', 'Sprint', 150),
        ('sport', 'SportEndurance', '30-40 мин кардио', 'Sprint', 180),
        ('sport', 'SportNoSkip', 'Спринт без пропусков', 'Sprint', 100),
        ('sport', 'SportStrengthGoal', 'Цель: жим 100/присед 120/подтяг 15', 'Campaign', 600),
        ('sport', 'SportConditioningGoal', '5 км ≤25 мин / 200 бёрпи', 'Campaign', 500),
        ('sport', 'SportBodyMeasures', 'Фото/замеры vs старт', 'Campaign', 300),
        ('sport', 'SportTestDay', 'Силовой + функционал + кардио', 'Campaign', 800),

        # Бизнес
        ('business', 'BizLeadHandled', 'Обработка лида', 'Daily', 15),
        ('business', 'BizCRMUpdate', 'Фиксация этапов', 'Daily', 5),
        ('business', 'BizTeamCheckin', 'Чекин с командой', 'Daily', 10),
        ('business', 'BizOutput1', 'Output: бот/фича/настройка', 'Daily', 20),
        ('business', 'BizDeal1-2', '1-2 сделки или демо', 'Weekly', 100),
        ('business', 'BizCoderDelivery', 'Проггер сдал модуль', 'Weekly', 80),
        ('business', 'BizPromptBot', 'Промптер сдал бота', 'Weekly', 150),
        ('business', 'BizSales20', '20+ касаний', 'Weekly', 60),
        ('business', 'BizMarketingReport', 'Отчёт по лидам', 'Weekly', 40),
        ('business', 'BizFinanceWeekly', 'Недельная сводка', 'Weekly', 30),
        ('business', 'BizClients5-7', '+5-7 платных клиентов', 'Sprint', 400),
        ('business', 'BizROIBreakeven', 'Реклама в 0', 'Sprint', 300),
        ('business', 'BizTechPipeline', 'Стабильный процесс 1-2 бота/нед', 'Sprint', 250),
        ('business', 'BizTeamAutonomy', 'Команда без микроменеджмента', 'Sprint', 200),
        ('business', 'BizRevenue15k', '$15k+ за 3 мес', 'Campaign', 1000),
        ('business', 'BizOfficeOpen', 'Офис запущен', 'Campaign', 600),
        ('business', 'BizClients15-20', '15-20 контрактов', 'Campaign', 800),
        ('business', 'BizProcessStable', 'Клиенты получают бота в срок', 'Campaign', 500),
        ('business', 'BizLeadFlow5+', 'Стабильные 5+ лидов/день', 'Campaign', 400),

        # Книги
        ('books', 'BooksRead10-20', '10-20 стр', 'Daily', 8),
        ('books', 'BooksNote1-2', '1-2 заметки идей', 'Daily', 5),
        ('books', 'BooksChapter', 'Глава + конспект', 'Weekly', 50),
        ('books', 'BooksApplyIdea', 'Внедрил идею', 'Weekly', 30),
        ('books', 'BooksFullBook', 'Книга 200-300 стр', 'Sprint', 200),
        ('books', 'BooksMindmap', 'Mind map', 'Sprint', 80),
        ('books', 'BooksActions3', '3 практических действия', 'Sprint', 60),
        ('books', 'Books3-4', '3-4 книги', 'Campaign', 600),
        ('books', 'BooksReviewEach', 'Обзор/эссе на каждую', 'Campaign', 300),
        ('books', 'BooksIntegrationProof', 'Идея из каждой внедрена', 'Campaign', 400),
        ('books', 'BooksPresentation', 'Мини-презентация', 'Campaign', 500),

        # Когнитивка
        ('brain', 'BrainMathDrill', '3 задачи логика/алгебра', 'Daily', 12),
        ('brain', 'BrainMemoryTrain', '10-15 слов/чисел', 'Daily', 10),
        ('brain', 'BrainSpeedRead', 'Статья → пересказ', 'Daily', 8),
        ('brain', 'BrainWrite20', '20 идей за 10 мин', 'Daily', 15),
        ('brain', 'BrainPuzzlePack', '1-2 головоломки', 'Weekly', 40),
        ('brain', 'BrainStrategyGame', 'Шахматы с анализом', 'Weekly', 50),
        ('brain', 'BrainCognitiveEssay', '300 слов: что понял', 'Weekly', 60),
        ('brain', 'BrainCodingMini', 'Скрипт/алгоритм', 'Weekly', 70),
        ('brain', 'BrainCourseChunk', 'Модуль курса', 'Sprint', 200),
        ('brain', 'BrainMemoryProject', '50 фактов/100 слов', 'Sprint', 150),
        ('brain', 'BrainCreativeOutput', 'Рассказ/эссе/проект', 'Sprint', 180),
        ('brain', 'BrainCompetitive', 'Турнир/викторина', 'Sprint', 220),
        ('brain', 'BrainHardSkill', 'Новое направление', 'Campaign', 800),
        ('brain', 'BrainPublicResult', 'Статья 2000+ слов', 'Campaign', 600),
        ('brain', 'BrainBenchmark', 'Тест IQ/когнитивки', 'Campaign', 400),
        ('brain', 'BrainPresentation', 'Доклад 15-20 мин', 'Campaign', 700),
    ]
    c.executemany("INSERT INTO piece_types (front_code, code, name, tier, base_xp) VALUES (?, ?, ?, ?, ?)", pieces)

    # Thresholds
    thresholds = [(1, 100)]
    for i in range(2, 51):
        thresholds.append((i, round(thresholds[-1][1] * 1.5)))
    c.executemany("INSERT INTO level_thresholds (level, xp_threshold) VALUES (?, ?)", thresholds)

    # Rewards
    rewards = [
        ('Ночной сериал', 200, None),
        ('Свободный день', 2500, None),
        ('Мелкая покупка', 4000, None),
        ('Тиндер-сессия', 300, None),
    ]
    c.executemany("INSERT INTO rewards (name, cost_coins, image_path) VALUES (?, ?, ?)", rewards)

    conn.commit()

# ============= XP & COINS ENGINE =============
def get_tier_mult(conn, front_code, tier):
    c = conn.cursor()
    col = f"tier_{tier.lower()}"
    c.execute(f"SELECT {col} FROM fronts WHERE code=?", (front_code,))
    row = c.fetchone()
    return row[0] if row else 1.0

def get_diff_mult(conn, front_code, difficulty):
    c = conn.cursor()
    col = f"diff_{difficulty}"
    c.execute(f"SELECT {col} FROM fronts WHERE code=?", (front_code,))
    row = c.fetchone()
    return row[0] if row else 1.0

def calc_task_xp(task, conn):
    if task['status'] not in ['Done', 'Failed', 'Skipped']:
        return 0.0

    c = conn.cursor()
    c.execute("SELECT base_xp FROM piece_types WHERE code=?", (task['piece_type'],))
    row = c.fetchone()
    base_xp = row[0] if row else (task['minutes'] // 10) * 10

    tier_mult = get_tier_mult(conn, task['front_code'], task['tier'])
    diff_mult = get_diff_mult(conn, task['front_code'], task['difficulty'])

    total_xp = base_xp * tier_mult * diff_mult

    if task['status'] in ['Failed', 'Skipped']:
        total_xp = -total_xp * 0.5

    return round(total_xp, 1)

def get_level(xp, conn):
    c = conn.cursor()
    c.execute("SELECT level FROM level_thresholds WHERE xp_threshold <= ? ORDER BY level DESC LIMIT 1", (xp,))
    row = c.fetchone()
    return row[0] if row else 1

def get_next_threshold(level, conn):
    c = conn.cursor()
    c.execute("SELECT xp_threshold FROM level_thresholds WHERE level=?", (level + 1,))
    row = c.fetchone()
    return row[0] if row else 999999

def get_total_coins(conn):
    c = conn.cursor()
    c.execute("SELECT SUM(coins_earned) FROM tasks")
    earned = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM coins_log")
    bonuses = c.fetchone()[0] or 0
    c.execute("SELECT SUM(coins_spent) FROM purchases")
    spent = c.fetchone()[0] or 0
    return earned + bonuses - spent

def check_levelup_bonus(conn, old_level, new_level):
    """Начисляет бонус 100% за levelup"""
    if new_level > old_level:
        c = conn.cursor()
        c.execute("SELECT xp_threshold FROM level_thresholds WHERE level=?", (old_level,))
        row = c.fetchone()
        if row:
            bonus = row[0]
            c.execute("INSERT INTO coins_log (date, source, amount, description) VALUES (?, ?, ?, ?)",
                     (datetime.now().strftime('%Y-%m-%d'), 'levelup', bonus,
                      f'Бонус за достижение уровня {new_level}'))
            conn.commit()
            return bonus
    return 0

def get_user_pref(conn, key, default=''):
    c = conn.cursor()
    c.execute("SELECT value FROM user_prefs WHERE key=?", (key,))
    row = c.fetchone()
    return row[0] if row else default

def set_user_pref(conn, key, value):
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO user_prefs (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

# ============= PAGES =============
def dashboard_page(conn):
    st.title("Дашборд")

    c = conn.cursor()

    # Общая XP (взвешенная)
    c.execute("SELECT SUM(t.total_xp * f.weight) FROM tasks t JOIN fronts f ON t.front_code = f.code")
    overall_xp = c.fetchone()[0] or 0
    overall_level = get_level(overall_xp, conn)
    next_threshold = get_next_threshold(overall_level, conn)

    # Текущий порог
    if overall_level == 1:
        current_threshold = 0
    else:
        c.execute("SELECT xp_threshold FROM level_thresholds WHERE level=?", (overall_level,))
        row = c.fetchone()
        current_threshold = row[0] if row else 0

    if next_threshold > current_threshold:
        progress = max(0, min(100, (overall_xp - current_threshold) / (next_threshold - current_threshold) * 100))
    else:
        progress = 0

    # Никоины
    total_coins = get_total_coins(conn)
    nikocoin_icon = get_nikocoin_icon()

    # Сегодня (взвешенная XP)
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT SUM(t.total_xp * f.weight) FROM tasks t JOIN fronts f ON t.front_code = f.code WHERE t.date=?", (today,))
    today_xp = c.fetchone()[0] or 0

    # Средняя за неделю (взвешенная XP)
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    c.execute("""
        SELECT AVG(daily_xp) FROM (
            SELECT SUM(t.total_xp * f.weight) as daily_xp 
            FROM tasks t
            JOIN fronts f ON t.front_code = f.code
            WHERE t.date >= ? 
            GROUP BY t.date
        )
    """, (week_ago,))
    week_avg = c.fetchone()[0] or 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Сегодня XP", f"{today_xp:.0f}")
    col2.metric("Средняя/неделя", f"{week_avg:.0f}")
    col3.metric("Уровень", overall_level)
    col4.markdown(f"**Никоинов:** {nikocoin_icon} {total_coins:.0f}", unsafe_allow_html=True)

    st.write(f"**Прогресс до уровня {overall_level + 1}:** {overall_xp:.0f} / {next_threshold}")
    st.progress(progress / 100.0)

    st.divider()

    st.subheader("Фронты")
    c.execute("""
        SELECT f.name, f.code, COALESCE(SUM(t.total_xp), 0) as total
        FROM fronts f
        LEFT JOIN tasks t ON f.code = t.front_code
        GROUP BY f.code
        ORDER BY total DESC
    """)

    for fname, fcode, fxp in c.fetchall():
        flvl = get_level(fxp, conn)
        st.metric(fname, f"Level {flvl}", f"{fxp:.0f} XP")

def front_detail_page(conn, front_code):
    c = conn.cursor()
    c.execute("SELECT name FROM fronts WHERE code=?", (front_code,))
    row = c.fetchone()
    if not row:
        st.error("Фронт не найден")
        return

    front_name = row[0]
    st.title(front_name)

    # XP фронта
    c.execute("SELECT COALESCE(SUM(total_xp), 0) FROM tasks WHERE front_code=?", (front_code,))
    front_xp = c.fetchone()[0]
    front_level = get_level(front_xp, conn)
    next_threshold = get_next_threshold(front_level, conn)

    # Текущий порог = порог ДЛЯ текущего уровня (не ОТ)
    if front_level == 1:
        current_threshold = 0
    else:
        c.execute("SELECT xp_threshold FROM level_thresholds WHERE level=?", (front_level,))
        row = c.fetchone()
        current_threshold = row[0] if row else 0

    # Расчёт прогресса
    if next_threshold > current_threshold:
        progress = (front_xp - current_threshold) / (next_threshold - current_threshold) * 100
        progress = max(0, min(100, progress))
    else:
        progress = 0

    # DEBUG
    st.caption(f"DEBUG: front_xp={front_xp:.1f}, current={current_threshold}, next={next_threshold}, progress={progress:.1f}%")

    col1, col2 = st.columns(2)
    col1.metric("Уровень", front_level)
    col2.metric("XP", f"{front_xp:.0f}")

    # Бонус за следующий levelup (100% от порога текущего уровня)
    c.execute("SELECT xp_threshold FROM level_thresholds WHERE level=?", (front_level,))
    levelup_bonus_row = c.fetchone()
    levelup_bonus = levelup_bonus_row[0] if levelup_bonus_row else 100
    nikocoin_icon = get_nikocoin_icon()

    col_left, col_right = st.columns([4, 1])
    with col_left:
        st.write(f"**Прогресс до уровня {front_level + 1}:** {front_xp:.0f} / {next_threshold}")
        # Простой HTML-бар
        bar_width = max(2, progress)  # Минимум 2% для видимости
        st.markdown(f"""
        <div style="background-color: #ddd; border-radius: 5px; height: 25px; width: 100%; position: relative;">
            <div style="background-color: #4CAF50; width: {bar_width}%; height: 100%; border-radius: 5px; 
                        display: flex; align-items: center; justify-content: center; color: white; font-weight: bold;">
                {progress:.1f}%
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_right:
        st.write(f"**→ Lvl {front_level + 1}**")
        st.markdown(f"*+{levelup_bonus:.0f} {nikocoin_icon}*", unsafe_allow_html=True)

    st.divider()

    # Быстрое логирование по тирам
    st.subheader("Быстрое логирование")

    # Табы по тирам
    tab1, tab2, tab3, tab4 = st.tabs(["Daily", "Weekly", "Sprint", "Campaign"])

    # Последние предпочтения
    last_diff = int(get_user_pref(conn, f"{front_code}_diff", "2"))

    difficulty = st.slider("Сложность (влияет на XP: x0.5 до x3)", 1, 5, last_diff)
    set_user_pref(conn, f"{front_code}_diff", str(difficulty))

    for tier, tab in [("Daily", tab1), ("Weekly", tab2), ("Sprint", tab3), ("Campaign", tab4)]:
        with tab:
            c.execute("SELECT code, name, base_xp FROM piece_types WHERE front_code=? AND tier=? ORDER BY base_xp",
                     (front_code, tier))
            tasks = c.fetchall()

            if not tasks:
                st.info(f"Нет задач типа {tier}")
                continue

            for task_code, task_name, base_xp in tasks:
                col1, col2, col3 = st.columns([3, 1, 1])
                col1.write(f"**{task_name}** ({base_xp} XP)")
                minutes = col2.number_input("Минуты", 0, 300, 0, 10, key=f"min_{task_code}", label_visibility="collapsed")

                if col3.button("✓", key=f"do_{task_code}"):
                    task = {
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'front_code': front_code,
                        'tier': tier,
                        'piece_type': task_code,
                        'note': '',
                        'minutes': minutes,
                        'difficulty': difficulty,
                        'status': 'Done'
                    }

                    # Старый уровень
                    old_overall_xp = c.execute("SELECT SUM(t.total_xp * f.weight) FROM tasks t JOIN fronts f ON t.front_code = f.code").fetchone()[0] or 0
                    old_level = get_level(old_overall_xp, conn)

                    total_xp = calc_task_xp(task, conn)
                    coins = total_xp  # 1:1

                    c.execute("""
                        INSERT INTO tasks (date, front_code, tier, piece_type, note, minutes, difficulty, status, total_xp, coins_earned)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (task['date'], task['front_code'], task['tier'], task['piece_type'],
                          task['note'], task['minutes'], task['difficulty'], task['status'], total_xp, coins))

                    conn.commit()

                    # Новый уровень
                    new_overall_xp = c.execute("SELECT SUM(t.total_xp * f.weight) FROM tasks t JOIN fronts f ON t.front_code = f.code").fetchone()[0] or 0
                    new_level = get_level(new_overall_xp, conn)

                    # Бонус за levelup
                    bonus = check_levelup_bonus(conn, old_level, new_level)

                    if bonus > 0:
                        st.success(f"+{total_xp:.0f} XP | +{coins:.0f} Ni-Coins | LEVEL UP! Бонус: +{bonus:.0f} Ni-Coins!")
                        st.balloons()
                    else:
                        st.success(f"+{total_xp:.0f} XP | +{coins:.0f} Ni-Coins")

                    st.rerun()

    st.divider()

    # Диаграмма
    st.subheader("Распределение XP по задачам")
    c.execute("""
        SELECT pt.name, SUM(t.total_xp) as total
        FROM tasks t
        JOIN piece_types pt ON t.piece_type = pt.code
        WHERE t.front_code = ?
        GROUP BY pt.code
        HAVING total > 0
        ORDER BY total DESC
    """, (front_code,))

    chart_data = c.fetchall()

    if chart_data:
        df = pd.DataFrame(chart_data, columns=['Задача', 'XP'])
        fig = px.pie(df, values='XP', names='Задача', hole=0.3)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # История с кнопкой удаления
    st.subheader("История")
    c.execute("""
        SELECT t.id, t.date, pt.name, t.status, t.total_xp
        FROM tasks t
        LEFT JOIN piece_types pt ON t.piece_type = pt.code
        WHERE t.front_code = ?
        ORDER BY t.date DESC, t.id DESC
        LIMIT 20
    """, (front_code,))

    history = c.fetchall()
    if history:
        for tid, tdate, tname, tstatus, txp in history:
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
            col1.write(tdate)
            col2.write(tname)
            col3.write(tstatus)
            col4.write(f"{txp:.0f} XP")
            if col5.button("🗑️", key=f"del_{tid}"):
                c.execute("DELETE FROM tasks WHERE id=?", (tid,))
                conn.commit()
                st.rerun()

def shop_page(conn):
    st.title("🛒 Магазин")

    c = conn.cursor()
    total_coins = get_total_coins(conn)
    nikocoin_icon = get_nikocoin_icon()

    st.markdown(f"**Доступно:** {nikocoin_icon} {total_coins:.0f}", unsafe_allow_html=True)

    st.divider()

    tab1, tab2, tab3 = st.tabs(["Товары", "Управление", "История"])

    with tab1:
        st.subheader("Доступные товары")
        c.execute("SELECT id, name, cost_coins, image_path FROM rewards ORDER BY cost_coins")
        rewards = c.fetchall()

        if not rewards:
            st.info("Магазин пуст. Добавьте товары во вкладке 'Управление'")

        for rid, rname, rcost, rimg in rewards:
            col1, col2, col3 = st.columns([2, 1, 1])

            if rimg and Path(rimg).exists():
                col1.image(str(rimg), width=100)

            col1.write(f"**{rname}**")
            col2.markdown(f"{nikocoin_icon} {rcost}", unsafe_allow_html=True)

            if col3.button("Купить", key=f"buy_{rid}", disabled=(total_coins < rcost)):
                c.execute("INSERT INTO purchases (date, reward_id, coins_spent) VALUES (?, ?, ?)",
                         (datetime.now().strftime('%Y-%m-%d'), rid, rcost))
                conn.commit()
                st.success(f"Куплено: {rname}")
                st.balloons()
                st.rerun()

    with tab2:
        st.subheader("Управление товарами")

        c.execute("SELECT id, name, cost_coins, image_path FROM rewards ORDER BY name")
        rewards = c.fetchall()

        for rid, rname, rcost, rimg in rewards:
            with st.expander(f"{rname} ({nikocoin_icon} {rcost})", expanded=False):
                new_name = st.text_input("Название", rname, key=f"rname_{rid}")
                new_cost = st.number_input(f"Цена ({nikocoin_icon})", 0, 100000, rcost, 50, key=f"rcost_{rid}")

                # Загрузка картинки
                uploaded_file = st.file_uploader("Загрузить картинку", type=['png', 'jpg', 'jpeg'], key=f"rimg_{rid}")
                if uploaded_file:
                    img_path = IMAGES_PATH / f"reward_{rid}_{uploaded_file.name}"
                    with open(img_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    new_img = str(img_path)
                    st.success(f"Картинка загружена: {img_path.name}")
                else:
                    new_img = rimg

                if rimg and Path(rimg).exists():
                    st.image(str(rimg), width=150, caption="Текущая картинка")

                col1, col2 = st.columns(2)
                if col1.button("Сохранить", key=f"rsave_{rid}"):
                    c.execute("UPDATE rewards SET name=?, cost_coins=?, image_path=? WHERE id=?",
                             (new_name, new_cost, new_img, rid))
                    conn.commit()
                    st.success("Обновлено")
                    st.rerun()

                if col2.button("Удалить", key=f"rdel_{rid}", type="secondary"):
                    c.execute("DELETE FROM rewards WHERE id=?", (rid,))
                    if rimg and Path(rimg).exists():
                        Path(rimg).unlink()
                    conn.commit()
                    st.success("Удалено")
                    st.rerun()

        st.divider()
        st.subheader("Добавить товар")

        new_name = st.text_input("Название товара")
        new_cost = st.number_input(f"Цена ({nikocoin_icon})", 0, 100000, 100, 50)
        new_img_file = st.file_uploader("Картинка (опционально)", type=['png', 'jpg', 'jpeg'])

        if st.button("Создать товар"):
            if new_name:
                c.execute("INSERT INTO rewards (name, cost_coins, image_path) VALUES (?, ?, ?)",
                         (new_name, new_cost, None))
                conn.commit()

                new_rid = c.lastrowid

                if new_img_file:
                    img_path = IMAGES_PATH / f"reward_{new_rid}_{new_img_file.name}"
                    with open(img_path, "wb") as f:
                        f.write(new_img_file.getbuffer())
                    c.execute("UPDATE rewards SET image_path=? WHERE id=?", (str(img_path), new_rid))
                    conn.commit()

                st.success("Товар создан")
                st.rerun()

    with tab3:
        st.subheader("История покупок")
        c.execute("""
            SELECT p.date, r.name, p.coins_spent
            FROM purchases p
            JOIN rewards r ON p.reward_id = r.id
            ORDER BY p.id DESC
            LIMIT 50
        """)
        purchases = c.fetchall()

        if purchases:
            df = pd.DataFrame(purchases, columns=['Дата', 'Товар', 'Потрачено'])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Покупок пока нет")

def settings_page(conn):
    st.title("Настройки")

    tab1, tab2 = st.tabs(["Фронты", "Ni-Coin иконка"])

    with tab2:
        st.subheader("Иконка Ni-Coin")

        if NIKOCOIN_PATH.exists():
            st.image(str(NIKOCOIN_PATH), width=100, caption="Текущая иконка")
            if st.button("Удалить иконку"):
                NIKOCOIN_PATH.unlink()
                st.success("Иконка удалена, будет использоваться эмодзи")
                st.rerun()
        else:
            st.info("Иконка не загружена. Будет использоваться эмодзи 🪙")

        uploaded_icon = st.file_uploader("Загрузить иконку Ni-Coin (PNG, круглое фото)", type=['png', 'jpg', 'jpeg'])

        if uploaded_icon and st.button("Сохранить иконку"):
            with open(NIKOCOIN_PATH, "wb") as f:
                f.write(uploaded_icon.getbuffer())
            st.success("Иконка загружена!")
            st.rerun()

    with tab1:
        c = conn.cursor()
        c.execute("SELECT code, name FROM fronts ORDER BY name")
        fronts = {row[1]: row[0] for row in c.fetchall()}

        selected_front_name = st.selectbox("Выберите фронт", list(fronts.keys()))
        front_code = fronts[selected_front_name]

    st.divider()

    # Общие настройки фронта
    c.execute("SELECT name, coef, weight FROM fronts WHERE code=?", (front_code,))
    fname, fcoef, fweight = c.fetchone()

    st.subheader("Общие настройки")
    new_fname = st.text_input("Название", fname)
    col1, col2 = st.columns(2)
    new_fcoef = col1.number_input("Коэффициент", 0.1, 5.0, fcoef, 0.1)
    new_fweight = col2.number_input("Вес", 0.1, 5.0, fweight, 0.1)

    if st.button("Сохранить общие настройки"):
        c.execute("UPDATE fronts SET name=?, coef=?, weight=? WHERE code=?",
                 (new_fname, new_fcoef, new_fweight, front_code))
        conn.commit()
        st.success("Обновлено")

    if st.button("Удалить фронт", type="secondary"):
        c.execute("DELETE FROM fronts WHERE code=?", (front_code,))
        c.execute("DELETE FROM piece_types WHERE front_code=?", (front_code,))
        c.execute("DELETE FROM tasks WHERE front_code=?", (front_code,))
        conn.commit()
        st.success("Фронт удалён")
        st.rerun()

    st.divider()

    # Множители
    st.subheader("Множители")
    c.execute("""SELECT tier_daily, tier_weekly, tier_sprint, tier_campaign, 
                 diff_1, diff_2, diff_3, diff_4, diff_5 FROM fronts WHERE code=?""", (front_code,))
    row = c.fetchone()

    st.write("**Тиры:**")
    col1, col2, col3, col4 = st.columns(4)
    t_daily = col1.number_input("Daily", 0.1, 5.0, row[0], 0.1)
    t_weekly = col2.number_input("Weekly", 0.1, 5.0, row[1], 0.1)
    t_sprint = col3.number_input("Sprint", 0.1, 5.0, row[2], 0.1)
    t_campaign = col4.number_input("Campaign", 0.1, 5.0, row[3], 0.1)

    st.write("**Сложность:**")
    col1, col2, col3, col4, col5 = st.columns(5)
    d1 = col1.number_input("1", 0.1, 5.0, row[4], 0.1)
    d2 = col2.number_input("2", 0.1, 5.0, row[5], 0.1)
    d3 = col3.number_input("3", 0.1, 5.0, row[6], 0.1)
    d4 = col4.number_input("4", 0.1, 5.0, row[7], 0.1)
    d5 = col5.number_input("5", 0.1, 5.0, row[8], 0.1)

    if st.button("Сохранить множители"):
        c.execute("""UPDATE fronts SET tier_daily=?, tier_weekly=?, tier_sprint=?, tier_campaign=?,
                     diff_1=?, diff_2=?, diff_3=?, diff_4=?, diff_5=? WHERE code=?""",
                 (t_daily, t_weekly, t_sprint, t_campaign, d1, d2, d3, d4, d5, front_code))
        conn.commit()
        st.success("Множители обновлены")

    st.divider()

    # Задачи по тирам
    st.subheader("Задачи")

    for tier in ['Daily', 'Weekly', 'Sprint', 'Campaign']:
        with st.expander(f"{tier} задачи"):
            c.execute("SELECT code, name, base_xp FROM piece_types WHERE front_code=? AND tier=? ORDER BY name",
                     (front_code, tier))
            tasks = c.fetchall()

            for tcode, tname, txp in tasks:
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                col1.write(f"**{tname}**")
                new_xp = col2.number_input("XP", 0, 10000, int(txp), 10, key=f"xp_{tcode}", label_visibility="collapsed")

                if col3.button("💾", key=f"save_{tcode}"):
                    c.execute("UPDATE piece_types SET base_xp=? WHERE code=?", (new_xp, tcode))
                    conn.commit()
                    st.success("✓")

                if col4.button("🗑️", key=f"del_{tcode}"):
                    c.execute("DELETE FROM piece_types WHERE code=?", (tcode,))
                    conn.commit()
                    st.rerun()

            st.write("**Добавить задачу:**")
            col1, col2, col3 = st.columns(3)
            new_code = col1.text_input("Код", "", key=f"newcode_{tier}")
            new_name = col2.text_input("Название", "", key=f"newname_{tier}")
            new_xp = col3.number_input("XP", 0, 10000, 10, 10, key=f"newxp_{tier}")

            if st.button("Создать", key=f"create_{tier}"):
                if new_code and new_name:
                    try:
                        c.execute("INSERT INTO piece_types (front_code, code, name, tier, base_xp) VALUES (?, ?, ?, ?, ?)",
                                 (front_code, new_code, new_name, tier, new_xp))
                        conn.commit()
                        st.success("Создано")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Код уже существует")

# ============= MAIN APP =============
st.set_page_config(page_title="Life Gamification", layout="wide", initial_sidebar_state="expanded")

conn = init_database()
seed_data(conn)

# Session state
if 'active_front' not in st.session_state:
    st.session_state['active_front'] = None
if 'active_page' not in st.session_state:
    st.session_state['active_page'] = 'dashboard'

# Sidebar
st.sidebar.title("Life Gamification")

# Постоянные кнопки навигации
if st.sidebar.button("🏠 Дашборд", use_container_width=True):
    st.session_state['active_page'] = 'dashboard'
    st.session_state['active_front'] = None
    st.rerun()

if st.sidebar.button("⚙️ Настройки", use_container_width=True):
    st.session_state['active_page'] = 'settings'
    st.session_state['active_front'] = None
    st.rerun()

if st.sidebar.button("🛒 Магазин", use_container_width=True):
    st.session_state['active_page'] = 'shop'
    st.session_state['active_front'] = None
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("Фронты")

c = conn.cursor()
c.execute("SELECT code, name FROM fronts ORDER BY name")
for fcode, fname in c.fetchall():
    if st.sidebar.button(fname, key=f"nav_{fcode}", use_container_width=True):
        st.session_state['active_front'] = fcode
        st.session_state['active_page'] = 'front'
        st.rerun()

# Роутинг
if st.session_state['active_front'] and st.session_state['active_page'] == 'front':
    front_detail_page(conn, st.session_state['active_front'])
elif st.session_state['active_page'] == 'dashboard':
    dashboard_page(conn)
elif st.session_state['active_page'] == 'settings':
    settings_page(conn)
elif st.session_state['active_page'] == 'shop':
    shop_page(conn)