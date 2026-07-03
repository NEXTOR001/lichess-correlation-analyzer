"""
interactive_predict.py — Интерактивный консольный скрипт для предсказания рейтингов.
Позволяет пользователю вводить свои результаты задач и получать предсказания рейтингов.
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import json
import numpy as np

PARAMS_FILE = 'model_params.json'

def load_model_params():
    """Загружает параметры модели из JSON-файла."""
    if not os.path.exists(PARAMS_FILE):
        print(f"❌ Ошибка: Файл параметров {PARAMS_FILE} не найден.")
        print("Пожалуйста, сначала запустите export_model.py или убедитесь, что файл сгенерирован.")
        sys.exit(1)
        
    with open(PARAMS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def predict(mode_params, features):
    """Вычисляет предсказание по формуле Ridge-регрессии с использованием скейлера."""
    intercept = mode_params['intercept']
    coefs = mode_params['coefs']
    mean = mode_params['scaler_mean']
    std = mode_params['scaler_std']
    
    # Масштабируем признаки: (x - mean) / std
    scaled_features = []
    for x, m, s in zip(features, mean, std):
        scaled_features.append((x - m) / s)
        
    # Скалярное произведение коэффициентов и масштабированных признаков + intercept
    pred = intercept + sum(c * val for c, val in zip(coefs, scaled_features))
    return int(round(pred))

def get_float_input(prompt, default, min_val=0.0, max_val=100000.0):
    """Безопасный ввод вещественного числа с клавиатуры."""
    while True:
        try:
            val_str = input(f"{prompt} [{default}]: ").strip()
            if not val_str:
                return default
            val = float(val_str)
            if min_val <= val <= max_val:
                return val
            else:
                print(f"⚠️ Число должно быть в диапазоне от {min_val} до {max_val}.")
        except ValueError:
            print("⚠️ Неверный формат ввода. Введите число.")

def get_int_input(prompt, default, min_val=0, max_val=1000000):
    """Безопасный ввод целого числа с клавиатуры."""
    while True:
        try:
            val_str = input(f"{prompt} [{default}]: ").strip()
            if not val_str:
                return default
            val = int(val_str)
            if min_val <= val <= max_val:
                return val
            else:
                print(f"⚠️ Число должно быть в диапазоне от {min_val} до {max_val}.")
        except ValueError:
            print("⚠️ Неверный формат ввода. Введите целое число.")

def main():
    params = load_model_params()
    
    print("=" * 70)
    print(" ♟   LICHESS RATING PREDICTOR — ИНТЕРАКТИВНЫЙ КОНСОЛЬНЫЙ ПОМОЩНИК   ♟")
    print("=" * 70)
    print("Этот скрипт предсказывает ваши рейтинги Blitz, Bullet и Rapid на основе")
    print("вашей шахматной активности и результатов решения задач.")
    print("Обучено на данных 3,400+ сильнейших шахматистов клуба Lichess Titled Arena.")
    print("=" * 70)
    
    # Значения по умолчанию (медианы из обучающей выборки)
    default_storm = 30
    default_streak = 25
    default_rating = 1800
    default_storm_runs = 50
    default_streak_runs = 50
    default_puzzle_games = 1500
    default_playtime = 200
    
    while True:
        print("\n📥 Введите ваши показатели (нажмите Enter для значений по умолчанию):")
        
        storm = get_float_input("⚡ Лучший результат Puzzle Storm", default_storm, 1, 100)
        streak = get_float_input("🔥 Лучший результат Puzzle Streak", default_streak, 1, 150)
        rating = get_float_input("🧩 Текущий рейтинг задач (Puzzle Rating)", default_rating, 600, 3500)
        
        # Спрашиваем, хочет ли пользователь ввести дополнительные параметры
        use_advanced = input("🔧 Ввести дополнительные параметры (кол-во попыток, время игры)? [y/N]: ").strip().lower()
        
        if use_advanced == 'y':
            storm_runs = get_int_input("   Количество попыток Puzzle Storm", default_storm_runs, 1, 50000)
            streak_runs = get_int_input("   Количество попыток Puzzle Streak", default_streak_runs, 1, 50000)
            puzzle_games = get_int_input("   Всего решено обычных задач", default_puzzle_games, 1, 500000)
            playtime = get_float_input("   Общее сыгранное время на Lichess (в часах)", default_playtime, 1, 100000)
        else:
            storm_runs = default_storm_runs
            streak_runs = default_streak_runs
            puzzle_games = default_puzzle_games
            playtime = default_playtime
            
        features = [storm, streak, rating, storm_runs, streak_runs, puzzle_games, playtime]
        
        print("\n" + "-" * 45)
        print("📊 РЕЗУЛЬТАТЫ ПРЕДСКАЗАНИЯ:")
        print("-" * 45)
        
        for mode in ['blitz', 'bullet', 'rapid']:
            pred_rating = predict(params[mode], features)
            n_samples = params[mode]['n_samples']
            print(f"  {mode.upper():<6} Rating:  ~{pred_rating:<4}  (точность MAE: ±{int(round(pred_rating * 0.08)):>3} pts, N={n_samples})")
            
        print("-" * 45)
        
        # Сохраняем введенные значения как новые дефолты для удобства следующего ввода
        default_storm = storm
        default_streak = streak
        default_rating = rating
        default_storm_runs = storm_runs
        default_streak_runs = streak_runs
        default_puzzle_games = puzzle_games
        default_playtime = playtime
        
        again = input("\n🔄 Хотите сделать ещё одно предсказание? [Y/n]: ").strip().lower()
        if again == 'n':
            print("\n👋 Спасибо за использование! Удачи в партиях на Lichess!")
            break

if __name__ == '__main__':
    # Сначала скопируем файл model_params.json в текущую директорию проекта, если скрипт запускается там
    if not os.path.exists('model_params.json'):
        import shutil
        artifact_path = r'C:\Users\123\.gemini\antigravity\brain\204866c8-cdca-4b03-9bc5-f2f03d99d6a0\model_params.json'
        if os.path.exists(artifact_path):
            shutil.copy(artifact_path, 'model_params.json')
            
    main()
