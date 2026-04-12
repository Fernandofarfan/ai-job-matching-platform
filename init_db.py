import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

host = os.getenv('DB_HOST', '127.0.0.1')
user = os.getenv('DB_USER', 'root')
password = os.getenv('DB_PASSWORD', '2306')

print(f"Connecting to {host} as {user}...")

try:
    # Connect without specifying database to create it
    cnx = mysql.connector.connect(
        host=host,
        user=user,
        password=password
    )
    cursor = cnx.cursor()
    
    with open('setup_database.sql', 'r', encoding='utf-8') as f:
        sql_script = f.read()
        
    # Split by semicolon and execute
    for statement in sql_script.split(';'):
        stmt = statement.strip()
        if stmt:
            try:
                cursor.execute(stmt)
                # Consume all results
                for _ in cursor:
                    pass
                print(f"Executed: {stmt[:50]}...")
            except Exception as e:
                print(f"Error executing statement: {e}")
                
    cnx.commit()
    cursor.close()
    cnx.close()
    print("Database initialized successfully!")
except Exception as e:
    print(f"Connection failed: {e}")
