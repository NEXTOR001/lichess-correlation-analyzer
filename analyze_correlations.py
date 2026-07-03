import sys
sys.stdout.reconfigure(encoding='utf-8')

"""
Lichess Correlation Analyzer
=============================
Анализ корреляций между рейтингами задач (Puzzle Storm, Puzzle Streak, Puzzle Rating)
и рейтингами в игровых контролях (Blitz, Bullet, Rapid, Classical).

Использует попарную фильтрацию: для каждой пары корреляций фильтры применяются
только к задействованным метрикам.
"""

import sqlite3
import json
import os
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
os.environ['PYTHONUTF8'] = '1'
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

warnings.filterwarnings('ignore')

# ============================================================================
# Конфигурация
# ============================================================================

DB_PATH = 'lichess_players.db'
PLOTS_DIR = 'plots'

# Пороги фильтрации
GAME_RD_THRESHOLD = 75      # Максимальное отклонение RD для игровых контролей
PUZZLE_RD_THRESHOLD = 100    # Максимальное отклонение RD для рейтинга задач
STORM_MIN_RUNS = 10          # Минимальное количество попыток Storm
STREAK_MIN_RUNS = 10         # Минимальное количество попыток Streak
STORM_MAX_RUNS = 300         # Максимальное количество попыток Storm
STREAK_MAX_RUNS = 300        # Максимальное количество попыток Streak

# Цветовая палитра
COLORS = {
    'storm': '#FF6B6B',
    'streak': '#4ECDC4',
    'puzzle': '#45B7D1',
    'blitz': '#FFA07A',
    'bullet': '#FFD700',
    'rapid': '#98D8C8',
    'classical': '#C9B1FF',
    'playtime': '#F7DC6F',
    'accent': '#FF6B6B',
    'bg': '#1a1a2e',
    'card': '#16213e',
    'text': '#e0e0e0',
    'grid': '#2a2a4a',
}

# ============================================================================
# Загрузка и подготовка данных
# ============================================================================

def load_data(db_path: str) -> pd.DataFrame:
    """Загружает данные из SQLite и парсит raw_json в плоский DataFrame."""
    print("📥 Загрузка данных из базы...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT raw_json FROM profiles")
    rows = cursor.fetchall()
    conn.close()
    
    records = []
    for row in rows:
        try:
            data = json.loads(row[0])
            perfs = data.get('perfs', {})
            
            storm = perfs.get('storm', {})
            streak = perfs.get('streak', {})
            racer = perfs.get('racer', {})
            puzzle = perfs.get('puzzle', {})
            blitz = perfs.get('blitz', {})
            bullet = perfs.get('bullet', {})
            rapid = perfs.get('rapid', {})
            classical = perfs.get('classical', {})
            
            records.append({
                'username': data.get('id', ''),
                # Puzzle modes
                'storm_score': storm.get('score'),
                'storm_runs': storm.get('runs', 0),
                'streak_score': streak.get('score'),
                'streak_runs': streak.get('runs', 0),
                'racer_score': racer.get('score'),
                'racer_runs': racer.get('runs', 0),
                'puzzle_rating': puzzle.get('rating'),
                'puzzle_rd': puzzle.get('rd'),
                'puzzle_games': puzzle.get('games', 0),
                # Game modes
                'blitz_rating': blitz.get('rating'),
                'blitz_rd': blitz.get('rd'),
                'blitz_games': blitz.get('games', 0),
                'bullet_rating': bullet.get('rating'),
                'bullet_rd': bullet.get('rd'),
                'bullet_games': bullet.get('games', 0),
                'rapid_rating': rapid.get('rating'),
                'rapid_rd': rapid.get('rd'),
                'rapid_games': rapid.get('games', 0),
                'classical_rating': classical.get('rating'),
                'classical_rd': classical.get('rd'),
                'classical_games': classical.get('games', 0),
                # Playtime
                'playtime_hours': (data.get('playTime', {}).get('total', 0) or 0) / 3600.0,
            })
        except Exception:
            continue
    
    df = pd.DataFrame(records)
    print(f"   ✅ Загружено {len(df)} профилей")
    return df


def apply_pair_filter(df: pd.DataFrame, 
                      puzzle_col: str, 
                      game_col: str) -> pd.DataFrame:
    """
    Попарная фильтрация: фильтрует только по метрикам, 
    задействованным в данной паре корреляции.
    """
    mask = pd.Series(True, index=df.index)
    
    # Фильтр для puzzle-метрик
    if puzzle_col == 'storm_score':
        mask &= df['storm_runs'] >= STORM_MIN_RUNS
        mask &= df['storm_runs'] <= STORM_MAX_RUNS
        mask &= df['storm_score'].notna()
    elif puzzle_col == 'streak_score':
        mask &= df['streak_runs'] >= STREAK_MIN_RUNS
        mask &= df['streak_runs'] <= STREAK_MAX_RUNS
        mask &= df['streak_score'].notna()
    elif puzzle_col == 'puzzle_rating':
        mask &= df['puzzle_rd'].notna()
        mask &= df['puzzle_rd'] <= PUZZLE_RD_THRESHOLD
        mask &= df['puzzle_rating'].notna()
    elif puzzle_col == 'racer_score':
        mask &= df['racer_runs'] >= 10
        mask &= df['racer_score'].notna()
    elif puzzle_col == 'playtime_hours':
        mask &= df['playtime_hours'] > 1  # Минимум 1 час общего времени
    elif puzzle_col == 'puzzle_games':
        mask &= df['puzzle_games'] > 0
        mask &= df['puzzle_rating'].notna()
        mask &= df['puzzle_rd'].notna()
        mask &= df['puzzle_rd'] <= PUZZLE_RD_THRESHOLD
    
    # Фильтр для game-метрик
    if game_col.endswith('_rating'):
        mode = game_col.replace('_rating', '')
        rd_col = f'{mode}_rd'
        if rd_col in df.columns:
            mask &= df[rd_col].notna()
            mask &= df[rd_col] <= GAME_RD_THRESHOLD
            mask &= df[game_col].notna()
    elif game_col == 'puzzle_rating':
        mask &= df['puzzle_rd'].notna()
        mask &= df['puzzle_rd'] <= PUZZLE_RD_THRESHOLD
        mask &= df['puzzle_rating'].notna()
    elif game_col in ('storm_score', 'streak_score'):
        if game_col == 'storm_score':
            mask &= df['storm_runs'] >= STORM_MIN_RUNS
            mask &= df['storm_runs'] <= STORM_MAX_RUNS
            mask &= df['storm_score'].notna()
        else:
            mask &= df['streak_runs'] >= STREAK_MIN_RUNS
            mask &= df['streak_runs'] <= STREAK_MAX_RUNS
            mask &= df['streak_score'].notna()
    
    return df[mask].copy()


# ============================================================================
# Вычисление корреляций
# ============================================================================

def compute_correlations(df: pd.DataFrame) -> pd.DataFrame:
    """Вычисляет корреляции Pearson и Spearman для всех интересных пар."""
    
    # Определяем все пары для анализа
    pairs = [
        # Puzzle Storm vs игровые контроли
        ('storm_score', 'blitz_rating', 'Puzzle Storm', 'Blitz'),
        ('storm_score', 'bullet_rating', 'Puzzle Storm', 'Bullet'),
        ('storm_score', 'rapid_rating', 'Puzzle Storm', 'Rapid'),
        ('storm_score', 'classical_rating', 'Puzzle Storm', 'Classical'),
        
        # Puzzle Streak vs игровые контроли
        ('streak_score', 'blitz_rating', 'Puzzle Streak', 'Blitz'),
        ('streak_score', 'bullet_rating', 'Puzzle Streak', 'Bullet'),
        ('streak_score', 'rapid_rating', 'Puzzle Streak', 'Rapid'),
        ('streak_score', 'classical_rating', 'Puzzle Streak', 'Classical'),
        
        # Puzzle Rating vs игровые контроли
        ('puzzle_rating', 'blitz_rating', 'Puzzle Rating', 'Blitz'),
        ('puzzle_rating', 'bullet_rating', 'Puzzle Rating', 'Bullet'),
        ('puzzle_rating', 'rapid_rating', 'Puzzle Rating', 'Rapid'),
        ('puzzle_rating', 'classical_rating', 'Puzzle Rating', 'Classical'),
        
        # Внутри задач
        ('storm_score', 'puzzle_rating', 'Puzzle Storm', 'Puzzle Rating'),
        ('streak_score', 'puzzle_rating', 'Puzzle Streak', 'Puzzle Rating'),
        ('storm_score', 'streak_score', 'Puzzle Storm', 'Puzzle Streak'),
        
        # Между игровыми контролями
        ('blitz_rating', 'bullet_rating', 'Blitz', 'Bullet'),
        ('blitz_rating', 'rapid_rating', 'Blitz', 'Rapid'),
        ('bullet_rating', 'rapid_rating', 'Bullet', 'Rapid'),
        
        # Время игры
        ('playtime_hours', 'blitz_rating', 'Play Time', 'Blitz'),
        ('playtime_hours', 'bullet_rating', 'Play Time', 'Bullet'),
        ('playtime_hours', 'rapid_rating', 'Play Time', 'Rapid'),
        ('playtime_hours', 'puzzle_rating', 'Play Time', 'Puzzle Rating'),
        
        # Количество задач vs рейтинг задач
        ('puzzle_games', 'puzzle_rating', 'Puzzles Solved', 'Puzzle Rating'),
    ]
    
    results = []
    for col_x, col_y, label_x, label_y in pairs:
        filtered = apply_pair_filter(df, col_x, col_y)
        n = len(filtered)
        
        if n < 10:
            results.append({
                'X': label_x, 'Y': label_y,
                'N': n,
                'Pearson_r': None, 'Pearson_p': None,
                'Spearman_r': None, 'Spearman_p': None,
                'col_x': col_x, 'col_y': col_y,
            })
            continue
        
        x = filtered[col_x].values.astype(float)
        y = filtered[col_y].values.astype(float)
        
        pearson_r, pearson_p = stats.pearsonr(x, y)
        spearman_r, spearman_p = stats.spearmanr(x, y)
        
        results.append({
            'X': label_x, 'Y': label_y,
            'N': n,
            'Pearson_r': round(pearson_r, 4),
            'Pearson_p': pearson_p,
            'Spearman_r': round(spearman_r, 4),
            'Spearman_p': spearman_p,
            'col_x': col_x, 'col_y': col_y,
        })
    
    return pd.DataFrame(results)


# ============================================================================
# Визуализация
# ============================================================================

def setup_style():
    """Настройка стиля matplotlib для красивых графиков."""
    plt.style.use('dark_background')
    plt.rcParams.update({
        'figure.facecolor': COLORS['bg'],
        'axes.facecolor': COLORS['card'],
        'axes.edgecolor': COLORS['grid'],
        'axes.labelcolor': COLORS['text'],
        'text.color': COLORS['text'],
        'xtick.color': COLORS['text'],
        'ytick.color': COLORS['text'],
        'grid.color': COLORS['grid'],
        'grid.alpha': 0.3,
        'font.family': 'sans-serif',
        'font.size': 11,
        'axes.titlesize': 14,
        'axes.labelsize': 12,
    })


def plot_correlation_heatmap(corr_df: pd.DataFrame):
    """Строит тепловую карту корреляций."""
    print("📊 Строю тепловую карту корреляций...")
    
    # Формируем матрицу корреляций
    metrics = ['storm_score', 'streak_score', 'puzzle_rating',
               'blitz_rating', 'bullet_rating', 'rapid_rating', 'classical_rating',
               'playtime_hours']
    labels = ['Storm', 'Streak', 'Puzzle\nRating', 
              'Blitz', 'Bullet', 'Rapid', 'Classical',
              'Play\nTime']
    
    n = len(metrics)
    matrix = np.full((n, n), np.nan)
    n_samples = np.full((n, n), 0, dtype=int)
    
    for _, row in corr_df.iterrows():
        col_x = row['col_x']
        col_y = row['col_y']
        if col_x in metrics and col_y in metrics:
            i = metrics.index(col_x)
            j = metrics.index(col_y)
            if row['Pearson_r'] is not None:
                matrix[i, j] = row['Pearson_r']
                matrix[j, i] = row['Pearson_r']
                n_samples[i, j] = row['N']
                n_samples[j, i] = row['N']
    
    # Диагональ = 1
    for i in range(n):
        matrix[i, i] = 1.0
    
    fig, ax = plt.subplots(figsize=(12, 10))
    fig.patch.set_facecolor(COLORS['bg'])
    
    mask = np.isnan(matrix)
    
    cmap = sns.diverging_palette(220, 20, as_cmap=True)
    
    sns.heatmap(matrix, 
                mask=mask,
                annot=True, 
                fmt='.2f',
                cmap=cmap,
                center=0,
                vmin=-1, vmax=1,
                xticklabels=labels,
                yticklabels=labels,
                square=True,
                linewidths=1,
                linecolor=COLORS['grid'],
                cbar_kws={'label': 'Pearson r', 'shrink': 0.8},
                annot_kws={'size': 11, 'weight': 'bold'},
                ax=ax)
    
    # Добавляем N в каждую ячейку (маленьким шрифтом)
    for i in range(n):
        for j in range(n):
            if not mask[i, j] and i != j and n_samples[i, j] > 0:
                ax.text(j + 0.5, i + 0.75, f'n={n_samples[i, j]}',
                       ha='center', va='center', fontsize=7,
                       color='#888888', style='italic')
    
    ax.set_title('Матрица корреляций Pearson\nLichess: Задачи vs Игровые контроли',
                fontsize=16, fontweight='bold', pad=20, color='white')
    
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'correlation_heatmap.png'), 
                dpi=200, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close()
    print("   ✅ Сохранено: plots/correlation_heatmap.png")


def plot_scatter_grid(df: pd.DataFrame, corr_df: pd.DataFrame):
    """Строит сетку scatter-плотов для ключевых пар корреляций."""
    print("📊 Строю scatter-плоты с регрессиями...")
    
    key_pairs = [
        ('storm_score', 'blitz_rating', 'Puzzle Storm', 'Blitz Rating', COLORS['storm']),
        ('storm_score', 'bullet_rating', 'Puzzle Storm', 'Bullet Rating', COLORS['storm']),
        ('storm_score', 'rapid_rating', 'Puzzle Storm', 'Rapid Rating', COLORS['storm']),
        ('streak_score', 'blitz_rating', 'Puzzle Streak', 'Blitz Rating', COLORS['streak']),
        ('streak_score', 'bullet_rating', 'Puzzle Streak', 'Bullet Rating', COLORS['streak']),
        ('streak_score', 'rapid_rating', 'Puzzle Streak', 'Rapid Rating', COLORS['streak']),
        ('puzzle_rating', 'blitz_rating', 'Puzzle Rating', 'Blitz Rating', COLORS['puzzle']),
        ('puzzle_rating', 'bullet_rating', 'Puzzle Rating', 'Bullet Rating', COLORS['puzzle']),
        ('puzzle_rating', 'rapid_rating', 'Puzzle Rating', 'Rapid Rating', COLORS['puzzle']),
    ]
    
    fig, axes = plt.subplots(3, 3, figsize=(20, 18))
    fig.patch.set_facecolor(COLORS['bg'])
    
    for idx, (col_x, col_y, label_x, label_y, color) in enumerate(key_pairs):
        ax = axes[idx // 3, idx % 3]
        
        filtered = apply_pair_filter(df, col_x, col_y)
        
        if len(filtered) < 10:
            ax.text(0.5, 0.5, f'Недостаточно данных\n(n={len(filtered)})',
                   ha='center', va='center', transform=ax.transAxes,
                   fontsize=12, color='#888888')
            ax.set_title(f'{label_x} vs {label_y}', fontsize=12)
            continue
        
        x = filtered[col_x].values.astype(float)
        y = filtered[col_y].values.astype(float)
        
        # Scatter с прозрачностью
        ax.scatter(x, y, alpha=0.35, s=18, color=color, edgecolors='none')
        
        # Линия регрессии
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        x_sorted = np.sort(x)
        ax.plot(x_sorted, p(x_sorted), color='white', linewidth=2, alpha=0.8, linestyle='--')
        
        # Корреляция в заголовке
        r, p_val = stats.pearsonr(x, y)
        sig = '***' if p_val < 0.001 else '**' if p_val < 0.01 else '*' if p_val < 0.05 else 'ns'
        ax.set_title(f'{label_x} vs {label_y}\nr={r:.3f} {sig}  (n={len(filtered)})',
                    fontsize=11, fontweight='bold')
        
        ax.set_xlabel(label_x, fontsize=10)
        ax.set_ylabel(label_y, fontsize=10)
        ax.grid(True, alpha=0.2)
    
    fig.suptitle('Корреляции: Puzzle Storm / Streak / Rating vs Игровые контроли',
                fontsize=18, fontweight='bold', y=1.01, color='white')
    
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'scatter_grid_main.png'),
                dpi=200, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close()
    print("   ✅ Сохранено: plots/scatter_grid_main.png")


def plot_bonus_correlations(df: pd.DataFrame):
    """Дополнительные интересные scatter-плоты."""
    print("📊 Строю дополнительные scatter-плоты...")
    
    bonus_pairs = [
        ('storm_score', 'streak_score', 'Puzzle Storm', 'Puzzle Streak', '#FF6B6B'),
        ('storm_score', 'puzzle_rating', 'Puzzle Storm', 'Puzzle Rating', '#4ECDC4'),
        ('streak_score', 'puzzle_rating', 'Puzzle Streak', 'Puzzle Rating', '#45B7D1'),
        ('playtime_hours', 'blitz_rating', 'Время игры (часы)', 'Blitz Rating', '#F7DC6F'),
        ('playtime_hours', 'puzzle_rating', 'Время игры (часы)', 'Puzzle Rating', '#C9B1FF'),
        ('puzzle_games', 'puzzle_rating', 'Решённые задачи', 'Puzzle Rating', '#98D8C8'),
        ('blitz_rating', 'bullet_rating', 'Blitz Rating', 'Bullet Rating', '#FFA07A'),
        ('blitz_rating', 'rapid_rating', 'Blitz Rating', 'Rapid Rating', '#FFD700'),
        ('bullet_rating', 'rapid_rating', 'Bullet Rating', 'Rapid Rating', '#FF8C94'),
    ]
    
    fig, axes = plt.subplots(3, 3, figsize=(20, 18))
    fig.patch.set_facecolor(COLORS['bg'])
    
    for idx, (col_x, col_y, label_x, label_y, color) in enumerate(bonus_pairs):
        ax = axes[idx // 3, idx % 3]
        
        filtered = apply_pair_filter(df, col_x, col_y)
        
        if col_x == 'playtime_hours':
            # Ограничиваем playtime для визуализации (до 99 перцентиля)
            cap = filtered['playtime_hours'].quantile(0.99)
            filtered = filtered[filtered['playtime_hours'] <= cap]
        
        if len(filtered) < 10:
            ax.text(0.5, 0.5, f'Недостаточно данных\n(n={len(filtered)})',
                   ha='center', va='center', transform=ax.transAxes,
                   fontsize=12, color='#888888')
            ax.set_title(f'{label_x} vs {label_y}', fontsize=12)
            continue
        
        x = filtered[col_x].values.astype(float)
        y = filtered[col_y].values.astype(float)
        
        ax.scatter(x, y, alpha=0.25, s=12, color=color, edgecolors='none')
        
        # Линия регрессии
        z = np.polyfit(x, y, 1)
        p_fn = np.poly1d(z)
        x_sorted = np.sort(x)
        ax.plot(x_sorted, p_fn(x_sorted), color='white', linewidth=2, alpha=0.8, linestyle='--')
        
        r, p_val = stats.pearsonr(x, y)
        sig = '***' if p_val < 0.001 else '**' if p_val < 0.01 else '*' if p_val < 0.05 else 'ns'
        ax.set_title(f'{label_x} vs {label_y}\nr={r:.3f} {sig}  (n={len(filtered)})',
                    fontsize=11, fontweight='bold')
        
        ax.set_xlabel(label_x, fontsize=10)
        ax.set_ylabel(label_y, fontsize=10)
        ax.grid(True, alpha=0.2)
    
    fig.suptitle('Дополнительные корреляции: Время, Задачи, Между контролями',
                fontsize=18, fontweight='bold', y=1.01, color='white')
    
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'scatter_grid_bonus.png'),
                dpi=200, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close()
    print("   ✅ Сохранено: plots/scatter_grid_bonus.png")


def plot_rating_distributions(df: pd.DataFrame):
    """Строит распределения рейтингов в виде violin plots."""
    print("📊 Строю распределения рейтингов...")
    
    fig, axes = plt.subplots(2, 1, figsize=(16, 12))
    fig.patch.set_facecolor(COLORS['bg'])
    
    # --- Распределения игровых рейтингов ---
    ax = axes[0]
    game_data = []
    game_labels = []
    game_colors = []
    
    for mode, color, label in [
        ('blitz', COLORS['blitz'], 'Blitz'),
        ('bullet', COLORS['bullet'], 'Bullet'),
        ('rapid', COLORS['rapid'], 'Rapid'),
        ('classical', COLORS['classical'], 'Classical')
    ]:
        col = f'{mode}_rating'
        rd_col = f'{mode}_rd'
        filtered = df[(df[rd_col].notna()) & (df[rd_col] <= GAME_RD_THRESHOLD) & (df[col].notna())]
        if len(filtered) > 50:
            game_data.append(filtered[col].values)
            game_labels.append(f'{label}\n(n={len(filtered)})')
            game_colors.append(color)
    
    parts = ax.violinplot(game_data, positions=range(len(game_data)), 
                          showmeans=True, showmedians=True)
    
    for i, pc in enumerate(parts['bodies']):
        pc.set_facecolor(game_colors[i])
        pc.set_alpha(0.6)
    
    parts['cmeans'].set_color('white')
    parts['cmedians'].set_color('#FF6B6B')
    parts['cmins'].set_color(COLORS['text'])
    parts['cmaxes'].set_color(COLORS['text'])
    parts['cbars'].set_color(COLORS['text'])
    
    ax.set_xticks(range(len(game_data)))
    ax.set_xticklabels(game_labels)
    ax.set_ylabel('Rating')
    ax.set_title('Распределение рейтингов по игровым контролям (RD ≤ 75)',
                fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.2, axis='y')
    
    # --- Распределение Puzzle Storm и Streak ---
    ax2 = axes[1]
    puzzle_data = []
    puzzle_labels = []
    puzzle_colors = []
    
    # Storm scores
    storm_f = df[(df['storm_runs'] >= STORM_MIN_RUNS) & 
                 (df['storm_runs'] <= STORM_MAX_RUNS) & 
                 (df['storm_score'].notna())]
    if len(storm_f) > 10:
        puzzle_data.append(storm_f['storm_score'].values)
        puzzle_labels.append(f'Storm Score\n(n={len(storm_f)})')
        puzzle_colors.append(COLORS['storm'])
    
    # Streak scores
    streak_f = df[(df['streak_runs'] >= STREAK_MIN_RUNS) & 
                  (df['streak_runs'] <= STREAK_MAX_RUNS) & 
                  (df['streak_score'].notna())]
    if len(streak_f) > 10:
        puzzle_data.append(streak_f['streak_score'].values)
        puzzle_labels.append(f'Streak Score\n(n={len(streak_f)})')
        puzzle_colors.append(COLORS['streak'])
    
    # Puzzle rating (масштабируем для отображения)
    puzzle_f = df[(df['puzzle_rd'].notna()) & 
                  (df['puzzle_rd'] <= PUZZLE_RD_THRESHOLD) & 
                  (df['puzzle_rating'].notna())]
    if len(puzzle_f) > 10:
        puzzle_data.append(puzzle_f['puzzle_rating'].values / 100.0)
        puzzle_labels.append(f'Puzzle Rating / 100\n(n={len(puzzle_f)})')
        puzzle_colors.append(COLORS['puzzle'])
    
    if puzzle_data:
        parts2 = ax2.violinplot(puzzle_data, positions=range(len(puzzle_data)),
                                showmeans=True, showmedians=True)
        
        for i, pc in enumerate(parts2['bodies']):
            pc.set_facecolor(puzzle_colors[i])
            pc.set_alpha(0.6)
        
        parts2['cmeans'].set_color('white')
        parts2['cmedians'].set_color('#FF6B6B')
        parts2['cmins'].set_color(COLORS['text'])
        parts2['cmaxes'].set_color(COLORS['text'])
        parts2['cbars'].set_color(COLORS['text'])
        
        ax2.set_xticks(range(len(puzzle_data)))
        ax2.set_xticklabels(puzzle_labels)
        ax2.set_ylabel('Score / (Rating / 100)')
        ax2.set_title('Распределение результатов задач (Storm, Streak, Puzzle Rating)',
                      fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.2, axis='y')
    
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'rating_distributions.png'),
                dpi=200, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close()
    print("   ✅ Сохранено: plots/rating_distributions.png")


def plot_hexbin_density(df: pd.DataFrame):
    """Строит hexbin плоты для плотности для ключевых пар."""
    print("📊 Строю hexbin-плоты плотности...")
    
    pairs = [
        ('puzzle_rating', 'blitz_rating', 'Puzzle Rating', 'Blitz Rating'),
        ('puzzle_rating', 'rapid_rating', 'Puzzle Rating', 'Rapid Rating'),
        ('storm_score', 'blitz_rating', 'Puzzle Storm', 'Blitz Rating'),
    ]
    
    fig, axes = plt.subplots(1, 3, figsize=(22, 7))
    fig.patch.set_facecolor(COLORS['bg'])
    
    for idx, (col_x, col_y, label_x, label_y) in enumerate(pairs):
        ax = axes[idx]
        
        filtered = apply_pair_filter(df, col_x, col_y)
        
        if len(filtered) < 30:
            ax.text(0.5, 0.5, f'Недостаточно данных (n={len(filtered)})',
                   ha='center', va='center', transform=ax.transAxes)
            continue
        
        x = filtered[col_x].values.astype(float)
        y = filtered[col_y].values.astype(float)
        
        hb = ax.hexbin(x, y, gridsize=25, cmap='magma', mincnt=1, alpha=0.9)
        
        # Линия регрессии
        z = np.polyfit(x, y, 1)
        p_fn = np.poly1d(z)
        x_sorted = np.sort(x)
        ax.plot(x_sorted, p_fn(x_sorted), color='#4ECDC4', linewidth=2.5, alpha=0.9, linestyle='--')
        
        r, p_val = stats.pearsonr(x, y)
        sig = '***' if p_val < 0.001 else '**' if p_val < 0.01 else '*' if p_val < 0.05 else 'ns'
        
        ax.set_title(f'{label_x} vs {label_y}\nr={r:.3f} {sig}  (n={len(filtered)})',
                    fontsize=13, fontweight='bold')
        ax.set_xlabel(label_x)
        ax.set_ylabel(label_y)
        
        plt.colorbar(hb, ax=ax, label='Количество игроков')
    
    fig.suptitle('Плотность распределения ключевых пар',
                fontsize=16, fontweight='bold', y=1.02, color='white')
    
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'hexbin_density.png'),
                dpi=200, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close()
    print("   ✅ Сохранено: plots/hexbin_density.png")


def print_results_table(corr_df: pd.DataFrame):
    """Красивый вывод таблицы корреляций в консоль."""
    
    print("\n" + "=" * 95)
    print("                     ТАБЛИЦА КОРРЕЛЯЦИЙ — Lichess Correlation Analyzer")
    print("=" * 95)
    print(f"{'X':<18} {'Y':<18} {'N':>6}  {'Pearson r':>10}  {'p-value':>10}  {'Spearman r':>10}  {'Сила':<12}")
    print("-" * 95)
    
    for _, row in corr_df.iterrows():
        if row['Pearson_r'] is None:
            print(f"{row['X']:<18} {row['Y']:<18} {row['N']:>6}  {'N/A':>10}  {'N/A':>10}  {'N/A':>10}  {'⚠ мало данных':<12}")
            continue
        
        r = abs(row['Pearson_r'])
        if r >= 0.7:
            strength = '🔴 Сильная'
        elif r >= 0.5:
            strength = '🟡 Средняя'
        elif r >= 0.3:
            strength = '🟢 Слабая'
        else:
            strength = '⚪ Очень слаб.'
        
        p_str = f"{row['Pearson_p']:.2e}" if row['Pearson_p'] is not None else 'N/A'
        
        print(f"{row['X']:<18} {row['Y']:<18} {row['N']:>6}  "
              f"{row['Pearson_r']:>10.4f}  {p_str:>10}  "
              f"{row['Spearman_r']:>10.4f}  {strength:<12}")
    
    print("=" * 95)
    print("\nУровни значимости: *** p<0.001, ** p<0.01, * p<0.05, ns — незначимо")
    print(f"Фильтры: Game RD ≤ {GAME_RD_THRESHOLD}, Puzzle RD ≤ {PUZZLE_RD_THRESHOLD}, "
          f"Storm/Streak runs: {STORM_MIN_RUNS}–{STORM_MAX_RUNS}")


def save_results_csv(corr_df: pd.DataFrame):
    """Сохраняет таблицу корреляций в CSV."""
    output_path = os.path.join(PLOTS_DIR, 'correlation_results.csv')
    corr_df[['X', 'Y', 'N', 'Pearson_r', 'Pearson_p', 'Spearman_r', 'Spearman_p']].to_csv(
        output_path, index=False, encoding='utf-8-sig'
    )
    print(f"\n📄 Таблица корреляций сохранена: {output_path}")


# ============================================================================
# Главная функция
# ============================================================================

def main():
    os.makedirs(PLOTS_DIR, exist_ok=True)
    
    setup_style()
    
    # 1. Загрузка данных
    df = load_data(DB_PATH)
    
    # 2. Статистика по данным
    print("\n📊 Статистика по данным:")
    print(f"   Всего профилей: {len(df)}")
    print(f"   Имеют Storm данные: {(df['storm_runs'] > 0).sum()}")
    print(f"   Имеют Streak данные: {(df['streak_runs'] > 0).sum()}")
    print(f"   Storm runs 10–300: {((df['storm_runs'] >= STORM_MIN_RUNS) & (df['storm_runs'] <= STORM_MAX_RUNS)).sum()}")
    print(f"   Streak runs 10–300: {((df['streak_runs'] >= STREAK_MIN_RUNS) & (df['streak_runs'] <= STREAK_MAX_RUNS)).sum()}")
    print(f"   Blitz RD ≤ {GAME_RD_THRESHOLD}: {(df['blitz_rd'] <= GAME_RD_THRESHOLD).sum()}")
    print(f"   Bullet RD ≤ {GAME_RD_THRESHOLD}: {(df['bullet_rd'] <= GAME_RD_THRESHOLD).sum()}")
    print(f"   Rapid RD ≤ {GAME_RD_THRESHOLD}: {(df['rapid_rd'] <= GAME_RD_THRESHOLD).sum()}")
    print(f"   Puzzle RD ≤ {PUZZLE_RD_THRESHOLD}: {(df['puzzle_rd'] <= PUZZLE_RD_THRESHOLD).sum()}")
    
    # 3. Вычисление корреляций
    print("\n🔬 Вычисление корреляций...")
    corr_df = compute_correlations(df)
    
    # 4. Вывод результатов
    print_results_table(corr_df)
    save_results_csv(corr_df)
    
    # 5. Визуализация
    print("\n🎨 Генерация графиков...")
    plot_correlation_heatmap(corr_df)
    plot_scatter_grid(df, corr_df)
    plot_bonus_correlations(df)
    plot_rating_distributions(df)
    plot_hexbin_density(df)
    
    print("\n✅ Анализ завершён! Все графики сохранены в папке plots/")


if __name__ == '__main__':
    main()
