# ♟️ Lichess Correlation Analyzer

Анализ взаимосвязи между рейтингами головоломок (**Puzzle Storm**, **Puzzle Streak**, **Puzzle Rating**) и рейтингами в игровых контролях (**Blitz**, **Bullet**, **Rapid**, **Classical**) на основе реальных данных игроков [Lichess](https://lichess.org).

Проект собирает профили игроков через публичный Lichess API, сохраняет их в локальную базу SQLite, а затем считает корреляции (Пирсон/Спирмен), строит графики и позволяет интерактивно предсказывать рейтинг по результатам решения головоломок.

---

## 📦 Возможности

- 📥 **Сбор данных** — загрузка профилей игроков Lichess (`download_lichess_data.py`) с поддержкой ретраев, ограничения скорости запросов и возобновления процесса.
- 🔬 **Корреляционный анализ** — вычисление корреляций Пирсона и Спирмена между рейтингами задач и игровыми рейтингами с попарной фильтрацией выбросов (`analyze_correlations.py`).
- 🎨 **Визуализация** — тепловая карта корреляций, диаграммы рассеяния, гексагональная плотность, распределения рейтингов (папка `plots/`).
- 🔮 **Интерактивное предсказание** — консольная утилита для оценки игрового рейтинга по результатам Storm/Streak (`interactive_predict.py`).

## 📁 Структура репозитория

```
.
├── download_lichess_data.py   # Загрузка профилей игроков через Lichess API в SQLite
├── analyze_correlations.py    # Анализ корреляций и построение графиков
├── interactive_predict.py     # Интерактивное предсказание рейтинга по модели
├── rating_predictor_boost.html# Интерактивный HTML-отчёт/дашборд с результатами
├── plots/                     # Сгенерированные графики и таблица корреляций
│   ├── correlation_heatmap.png
│   ├── scatter_grid_main.png
│   ├── scatter_grid_bonus.png
│   ├── rating_distributions.png
│   ├── hexbin_density.png
│   ├── feature_importance.png
│   ├── regression_predicted_vs_actual.png
│   └── correlation_results.csv
├── requirements.txt
└── LICENSE
```

## 🚀 Установка

```bash
git clone https://github.com/NEXTOR001/lichess-correlation-analyzer.git
cd lichess-correlation-analyzer
pip install -r requirements.txt
```

Требуется Python 3.8+.

## 🔧 Использование

### 1. Загрузка данных с Lichess

Скрипт скачивает список игроков команды и подгружает их публичные профили (рейтинги, RD, статистику по головоломкам) в SQLite-базу.

```bash
export LICHESS_API_TOKEN=your_token_here   # опционально, повышает лимиты API
python download_lichess_data.py --target 10000 --batch 300 --db lichess_players.db
```

Основные параметры:

| Флаг | Описание | По умолчанию |
|---|---|---|
| `--target` | Целевое число профилей для загрузки | `100000` |
| `--batch` | Размер пакета при запросе профилей | `300` |
| `--db` | Путь к файлу SQLite базы | `lichess_players.db` |
| `--log` | Путь к лог-файлу | `download.log` |
| `--all-usernames` | Собрать все имена пользователей команды, не останавливаясь раньше времени | `False` |
| `--only-usernames` | Выполнить только сбор имён пользователей (фаза 1) и выйти | `False` |
| `--skip` | Пропустить первые N имён пользователей (если уже есть в базе) | `0` |
| `--token` | Использовать токен `new`, `old` или указать токен напрямую | `new` |

### 2. Анализ корреляций и построение графиков

```bash
python analyze_correlations.py
```

Скрипт загружает данные из `lichess_players.db`, фильтрует их по надёжности рейтинга (RD) и количеству попыток, считает корреляции и сохраняет:

- таблицу корреляций в `plots/correlation_results.csv`;
- набор графиков в папку `plots/`.

### 3. Интерактивное предсказание рейтинга

```bash
python interactive_predict.py
```

Скрипт использует параметры регрессионной модели из `model_params.json` (генерируется отдельно) и позволяет ввести собственные результаты Storm/Streak, чтобы получить предсказанный игровой рейтинг.

## 📊 Результаты

Результаты анализа доступны в виде графиков в папке [`plots/`](./plots) и в виде интерактивного дашборда — [`rating_predictor_boost.html`](./rating_predictor_boost.html).

Дашборд также опубликован через GitHub Pages: [https://nextor001.github.io/lichess-correlation-analyzer/](https://nextor001.github.io/lichess-correlation-analyzer/) (страница `index.html` автоматически перенаправляет на `rating_predictor_boost.html`).

> ℹ️ Чтобы публикация заработала, в репозитории нужно один раз включить GitHub Pages: **Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: `main` / `(root)`**.

## 🛠️ Технологии

- Python, SQLite
- pandas, numpy, scipy — обработка данных и статистика
- matplotlib, seaborn — визуализация
- requests — работа с Lichess API

## 📄 Лицензия

Проект распространяется под лицензией [MIT](./LICENSE).
