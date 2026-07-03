import os
import sys
import time
import sqlite3
import json
import argparse
import requests
from datetime import datetime

# Configuration Defaults
TOKENS = {
    "new": os.getenv("LICHESS_API_TOKEN", ""),
    "old": os.getenv("LICHESS_API_TOKEN_OLD", "")
}
DEFAULT_TOKEN_NAME = "new"
API_TOKEN = TOKENS[DEFAULT_TOKEN_NAME]

DEFAULT_DB_PATH = "lichess_players.db"
DEFAULT_LOG_PATH = "download.log"
DEFAULT_TARGET_PROFILES = 100000
DEFAULT_BATCH_SIZE = 300
NORMAL_DELAY = 0.5  # Seconds of sleep between successful requests
MAX_RETRIES = 5
RETRY_DELAY_429 = 60  # Lichess guideline: wait 1 minute on 429
TEAM_ID = "lichess-swiss"


def build_headers(token_value=None):
    headers = {"Accept": "application/json"}
    if token_value:
        headers["Authorization"] = f"Bearer {token_value}"
    return headers


# Setup headers (will be updated in main)
HEADERS = build_headers(API_TOKEN)

# Global config variables updated in main
DB_PATH = DEFAULT_DB_PATH
LOG_PATH = DEFAULT_LOG_PATH
TARGET_PROFILES = DEFAULT_TARGET_PROFILES
BATCH_SIZE = DEFAULT_BATCH_SIZE

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    print(formatted)
    sys.stdout.flush()
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception as e:
        print(f"Error writing to log file {LOG_PATH}: {e}")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Queue table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS players (
        username_id TEXT PRIMARY KEY,
        display_name TEXT,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Profiles table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        username_id TEXT PRIMARY KEY,
        display_name TEXT,
        createdAt INTEGER,
        seenAt INTEGER,
        playTime_total INTEGER,
        bullet_rating INTEGER, bullet_rd INTEGER, bullet_games INTEGER,
        blitz_rating INTEGER, blitz_rd INTEGER, blitz_games INTEGER,
        rapid_rating INTEGER, rapid_rd INTEGER, rapid_games INTEGER,
        classical_rating INTEGER, classical_rd INTEGER, classical_games INTEGER,
        puzzle_rating INTEGER, puzzle_rd INTEGER, puzzle_games INTEGER,
        raw_json TEXT,
        downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_status ON players(status)")
    
    conn.commit()
    return conn

def populate_usernames(conn, all_usernames=False, skip_count=0):
    cursor = conn.cursor()
    
    # Check if we already have usernames in queue
    cursor.execute("SELECT COUNT(*) FROM players")
    total_in_db = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM players WHERE status = 'completed'")
    completed_in_db = cursor.fetchone()[0]
    
    limit_usernames = int(TARGET_PROFILES * 1.3)
    skip_limit = 500000 if all_usernames else TARGET_PROFILES * 1.2
    
    if total_in_db >= TARGET_PROFILES:
        log(f"Database already contains {total_in_db} players in queue (target is {TARGET_PROFILES}). Skipping Phase 1.")
        return
        
    log(f"Starting Phase 1: Fetching usernames from team '{TEAM_ID}' (all_usernames={all_usernames}, skip={skip_count})...")
    url = f"https://lichess.org/api/team/{TEAM_ID}/users"
    
    retries = 0
    response = None
    while retries < MAX_RETRIES:
        try:
            response = requests.get(url, headers=HEADERS, stream=True, timeout=30)
            if response.status_code == 200:
                break
            elif response.status_code == 429:
                log(f"HTTP 429 Too Many Requests in Phase 1. Waiting {RETRY_DELAY_429} seconds...")
                time.sleep(RETRY_DELAY_429)
                retries += 1
            else:
                log(f"HTTP {response.status_code} error in Phase 1: {response.text}. Retrying in 10 seconds...")
                time.sleep(10)
                retries += 1
        except Exception as e:
            log(f"Connection error in Phase 1: {e}. Retrying in 10 seconds...")
            time.sleep(10)
            retries += 1
            
    if not response or response.status_code != 200:
        log(f"Failed to fetch team members after {MAX_RETRIES} retries. Phase 1 aborted.")
        return
        
    # Lichess team members stream
    try:
        buffer = []
        count_added = 0
        stream_count = 0
        skipped = 0
        
        if skip_count > 0:
            log(f"Skipping first {skip_count} entries from the stream...")
        
        for line in response.iter_lines():
            if not line:
                continue
            
            stream_count += 1
            
            # Skip first N entries
            if stream_count <= skip_count:
                if stream_count % 10000 == 0:
                    log(f"Skipped {stream_count}/{skip_count} entries...")
                continue
                
            try:
                user_data = json.loads(line.decode('utf-8'))
                username_id = user_data.get('id')
                display_name = user_data.get('name')
                
                if username_id and display_name:
                    buffer.append((username_id, display_name, 'pending'))
                    
                if len(buffer) >= 10000:
                    cursor.executemany(
                        "INSERT OR IGNORE INTO players (username_id, display_name, status) VALUES (?, ?, ?)",
                        buffer
                    )
                    conn.commit()
                    count_added += len(buffer)
                    
                    # Check current total
                    cursor.execute("SELECT COUNT(*) FROM players")
                    current_total = cursor.fetchone()[0]
                    log(f"Queued {current_total} players...")
                    
                    buffer = []
                    
                    if not all_usernames and current_total >= limit_usernames:
                        log("Reached sufficient username pool buffer size.")
                        break
            except Exception as e:
                log(f"Error parsing line: {e}")
                
        if buffer:
            cursor.executemany(
                "INSERT OR IGNORE INTO players (username_id, display_name, status) VALUES (?, ?, ?)",
                buffer
            )
            conn.commit()
            cursor.execute("SELECT COUNT(*) FROM players")
            current_total = cursor.fetchone()[0]
            log(f"Finished loading usernames. Total queued: {current_total}")
            
    except Exception as e:
        log(f"Exception during Phase 1: {e}")

def get_perf_data(perfs, perf_name):
    perf = perfs.get(perf_name, {})
    return (
        perf.get('rating'),
        perf.get('rd'),
        perf.get('games')
    )

def download_profiles(conn):
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM profiles")
    initial_completed = cursor.fetchone()[0]
    log(f"Starting Phase 2: Downloading user profiles. Currently completed: {initial_completed}/{TARGET_PROFILES}")
    
    if initial_completed >= TARGET_PROFILES:
        log("Goal already achieved! Required profiles downloaded.")
        return
        
    start_time = time.time()
    batch_times = []
    
    current_delay = 1.5  # Start with a safer delay of 1.5 seconds
    consecutive_successes = 0
    
    while True:
        # Check current count of completed profiles
        cursor.execute("SELECT COUNT(*) FROM profiles")
        completed = cursor.fetchone()[0]
        
        if completed >= TARGET_PROFILES:
            log(f"Successfully reached target of {TARGET_PROFILES} profiles!")
            break
            
        # Get next batch of pending users
        cursor.execute(
            "SELECT username_id, display_name FROM players WHERE status = 'pending' LIMIT ?",
            (BATCH_SIZE,)
        )
        batch = cursor.fetchall()
        
        if not batch:
            # Check if we have failed ones we can retry
            cursor.execute(
                "SELECT username_id, display_name FROM players WHERE status = 'failed' LIMIT ?",
                (BATCH_SIZE,)
            )
            batch = cursor.fetchall()
            if not batch:
                log("No more pending or failed players in the queue. Fetching more usernames...")
                populate_usernames(conn)
                cursor.execute(
                    "SELECT username_id, display_name FROM players WHERE status = 'pending' LIMIT ?",
                    (BATCH_SIZE,)
                )
                batch = cursor.fetchall()
                if not batch:
                    log("Unable to find or fetch more usernames. Stopping.")
                    break
        
        usernames_map = {row[0]: row[1] for row in batch}
        usernames_list = list(usernames_map.keys())
        
        # Mark as processing
        placeholders = ",".join(["?"] * len(usernames_list))
        cursor.execute(
            f"UPDATE players SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE username_id IN ({placeholders})",
            usernames_list
        )
        conn.commit()
        
        # Prepare the POST body
        body = ",".join(usernames_list)
        
        # Fetch profiles with retry logic
        url = "https://lichess.org/api/users"
        response_data = None
        retries = 0
        consecutive_429s = 0
        
        batch_start = time.time()
        
        while retries < MAX_RETRIES:
            try:
                # Content-Type must be text/plain or empty
                res = requests.post(url, data=body, headers=HEADERS, timeout=30)
                
                if res.status_code == 200:
                    response_data = res.json()
                    consecutive_429s = 0
                    consecutive_successes += 1
                    if consecutive_successes >= 10:
                        old_delay = current_delay
                        current_delay = max(0.5, current_delay - 0.1)
                        if old_delay != current_delay:
                            log(f"Reducing normal delay to {current_delay:.2f} seconds after 10 consecutive successes.")
                        consecutive_successes = 0
                    break
                elif res.status_code == 429:
                    consecutive_429s += 1
                    consecutive_successes = 0
                    old_delay = current_delay
                    current_delay = min(5.0, current_delay + 0.5)
                    log(f"HTTP 429 Too Many Requests. Increasing normal delay to {current_delay:.2f} seconds.")
                    
                    wait_time = RETRY_DELAY_429 * consecutive_429s
                    log(f"Waiting {wait_time} seconds before retry (429 count: {consecutive_429s})...")
                    time.sleep(wait_time)
                    retries += 1
                elif res.status_code in (500, 502, 503, 504):
                    backoff = 5 * (2 ** retries)
                    log(f"HTTP {res.status_code} server error. Retrying in {backoff} seconds...")
                    time.sleep(backoff)
                    retries += 1
                else:
                    log(f"HTTP {res.status_code} error: {res.text}. Retrying in 10 seconds...")
                    time.sleep(10)
                    retries += 1
            except Exception as e:
                backoff = 5 * (2 ** retries)
                log(f"Connection error: {e}. Retrying in {backoff} seconds...")
                time.sleep(backoff)
                retries += 1
                
        if response_data is None:
            log(f"Failed to fetch batch after {MAX_RETRIES} retries. Marking batch as failed.")
            cursor.execute(
                f"UPDATE players SET status = 'failed', error_message = 'Failed to fetch batch after retries', updated_at = CURRENT_TIMESTAMP WHERE username_id IN ({placeholders})",
                usernames_list
            )
            conn.commit()
            time.sleep(5)
            continue
            
        # Process results
        fetched_ids = set()
        profiles_to_insert = []
        
        for profile in response_data:
            uid = profile.get('id')
            if not uid:
                continue
                
            fetched_ids.add(uid)
            display_name = profile.get('username')
            createdAt = profile.get('createdAt')
            seenAt = profile.get('seenAt')
            playTime_total = profile.get('playTime', {}).get('total')
            
            perfs = profile.get('perfs', {})
            
            bullet_rating, bullet_rd, bullet_games = get_perf_data(perfs, 'bullet')
            blitz_rating, blitz_rd, blitz_games = get_perf_data(perfs, 'blitz')
            rapid_rating, rapid_rd, rapid_games = get_perf_data(perfs, 'rapid')
            classical_rating, classical_rd, classical_games = get_perf_data(perfs, 'classical')
            puzzle_rating, puzzle_rd, puzzle_games = get_perf_data(perfs, 'puzzle')
            
            raw_json = json.dumps(profile)
            
            profiles_to_insert.append((
                uid, display_name, createdAt, seenAt, playTime_total,
                bullet_rating, bullet_rd, bullet_games,
                blitz_rating, blitz_rd, blitz_games,
                rapid_rating, rapid_rd, rapid_games,
                classical_rating, classical_rd, classical_games,
                puzzle_rating, puzzle_rd, puzzle_games,
                raw_json
            ))
            
        # Write to SQLite
        if profiles_to_insert:
            cursor.executemany(
                """
                INSERT OR REPLACE INTO profiles (
                    username_id, display_name, createdAt, seenAt, playTime_total,
                    bullet_rating, bullet_rd, bullet_games,
                    blitz_rating, blitz_rd, blitz_games,
                    rapid_rating, rapid_rd, rapid_games,
                    classical_rating, classical_rd, classical_games,
                    puzzle_rating, puzzle_rd, puzzle_games,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                profiles_to_insert
            )
            
        # Update queue status
        # Completed
        if fetched_ids:
            completed_placeholders = ",".join(["?"] * len(fetched_ids))
            cursor.execute(
                f"UPDATE players SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE username_id IN ({completed_placeholders})",
                list(fetched_ids)
            )
            
        # Not found (requested but not in response)
        not_found_ids = set(usernames_list) - fetched_ids
        if not_found_ids:
            nf_placeholders = ",".join(["?"] * len(not_found_ids))
            cursor.execute(
                f"UPDATE players SET status = 'not_found', updated_at = CURRENT_TIMESTAMP WHERE username_id IN ({nf_placeholders})",
                list(not_found_ids)
            )
            
        conn.commit()
        
        batch_end = time.time()
        elapsed = batch_end - batch_start
        batch_times.append(elapsed)
        if len(batch_times) > 50:
            batch_times.pop(0)
            
        avg_batch_time = sum(batch_times) / len(batch_times)
        profiles_per_sec = len(usernames_list) / avg_batch_time
        
        # Calculate ETA
        remaining = TARGET_PROFILES - (completed + len(fetched_ids))
        if remaining > 0:
            eta_sec = remaining / profiles_per_sec
            eta_hours = eta_sec / 3600
            eta_str = f"{eta_hours:.2f} hours"
        else:
            eta_str = "0 hours"
            
        log(
            f"Batch processed. Fetched: {len(fetched_ids)}/{len(usernames_list)}. "
            f"Total Completed: {completed + len(fetched_ids)}/{TARGET_PROFILES} ({(completed + len(fetched_ids))/TARGET_PROFILES*100:.2f}%). "
            f"Speed: {profiles_per_sec * 60:.1f} profiles/min. "
            f"ETA: {eta_str}."
        )
        
        # Small delay between batches to respect rate limits
        time.sleep(current_delay)

def main():
    global DB_PATH, LOG_PATH, TARGET_PROFILES, BATCH_SIZE, HEADERS, API_TOKEN
    
    parser = argparse.ArgumentParser(description="Lichess Player Data Downloader")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET_PROFILES, help="Target number of profiles to download")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size for fetching profiles")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help="Path to the SQLite database file")
    parser.add_argument("--log", type=str, default=DEFAULT_LOG_PATH, help="Path to the log file")
    parser.add_argument("--all-usernames", action="store_true", help="Download all usernames from the team without stopping early")
    parser.add_argument("--only-usernames", action="store_true", help="Only run Phase 1 (username collection) and then exit")
    parser.add_argument("--skip", type=int, default=0, help="Skip the first N usernames from the team stream (use when they are already in the DB)")
    parser.add_argument("--token", type=str, default=DEFAULT_TOKEN_NAME, help="Token to use: 'new', 'old', or direct token string")
    
    args = parser.parse_args()
    
    DB_PATH = args.db
    LOG_PATH = args.log
    TARGET_PROFILES = args.target
    BATCH_SIZE = args.batch
    
    # Configure token
    if args.token in TOKENS:
        token_val = TOKENS[args.token] or os.getenv("LICHESS_API_TOKEN", "")
    else:
        token_val = args.token or os.getenv("LICHESS_API_TOKEN", "")

    API_TOKEN = token_val
    HEADERS = build_headers(API_TOKEN)

    masked_token = API_TOKEN[:6] + "..." + API_TOKEN[-6:] if API_TOKEN and len(API_TOKEN) > 12 else "redacted"

    log(f"Initializing Lichess Data Downloader with DB: {DB_PATH}, Log: {LOG_PATH}, Target: {TARGET_PROFILES}, Batch: {BATCH_SIZE}, Skip: {args.skip}, Token: {args.token} ({masked_token})...")
    conn = init_db()
    
    try:
        # Phase 1: Populate usernames
        populate_usernames(conn, all_usernames=args.all_usernames, skip_count=args.skip)
        
        # Phase 2: Download profile details
        if not args.only_usernames:
            download_profiles(conn)
        else:
            log("Skipping Phase 2 because --only-usernames was specified.")
            
        log("Execution completed successfully.")
    except KeyboardInterrupt:
        log("Execution interrupted by user.")
    except Exception as e:
        log(f"Fatal exception: {e}")
        import traceback
        log(traceback.format_exc())
    finally:
        conn.close()
        log("Database connection closed.")

if __name__ == "__main__":
    main()
