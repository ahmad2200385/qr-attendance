from app import app, DB, init_db
import os

if not os.path.exists(DB):
    init_db()
