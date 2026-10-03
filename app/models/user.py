"""User storage backed by the configured database."""
import sqlite3
from database import connect_database

DEFAULT_AVATAR = "blue"

def connect_db():
    connection = connect_database()
    db_cursor = connection.cursor()
    return connection, db_cursor

def create_users_table():
    connection, cursor = connect_db()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT,
                last_login TEXT,
                email TEXT UNIQUE,
                avatar TEXT NOT NULL DEFAULT 'blue')"""
        )

        # Keep databases created before avatars were introduced compatible.
        cursor.execute("PRAGMA table_info(users)")
        columns = {column[1] for column in cursor.fetchall()}
        if "avatar" not in columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN avatar TEXT NOT NULL DEFAULT 'blue'"
            )
        connection.commit()
    finally:
        connection.close()

def drop_table(table_name):   
    connection, cursor = connect_db()
    try:
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        connection.commit()
    finally:
        connection.close()

def create_user(username, pasword_hash, created_at=None, last_login=None, email=None):
    connection, cursor = connect_db()
    try:
        cursor.execute("""
            INSERT INTO users 
            (username, password_hash, created_at, last_login, email)
            VALUES (?, ?, ?, ?, ?)""", 
            [username, pasword_hash, created_at, last_login, email])
        connection.commit()
    except sqlite3.IntegrityError as error:
        error_msg = str(error)
        return f"Account not created. Retry. Databse integrity error: {error_msg}"
    finally:    
        connection.close()

def get_user(username=None, email=None, user_id=None):
    connection, cursor = connect_db()
    try:
        if username:
            cursor.execute("SELECT * FROM users WHERE username = ?", [username])
            user_row = cursor.fetchone()
        elif email:
            cursor.execute("SELECT * FROM users WHERE email = ?", [email])
            user_row = cursor.fetchone()
        elif user_id is not None:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", [user_id])
            user_row = cursor.fetchone()
        else:
            return None
    finally:
        connection.close()

    return user_row
    

def update_last_login(last_login, user_id):
    connection, cursor = connect_db()
    try:
        cursor.execute(
            """UPDATE users 
            SET last_login = ? 
            WHERE user_id = ?""", [last_login, user_id])
        connection.commit()
    finally:
        connection.close()


def update_avatar(avatar, user_id):
    connection, cursor = connect_db()
    try:
        cursor.execute(
            "UPDATE users SET avatar = ? WHERE user_id = ?",
            [avatar, user_id]
        )
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


