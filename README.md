import tkinter as tk
from tkinter import messagebox
import sqlite3

# Connexion base de données
conn = sqlite3.connect("traduction.db")
cursor = conn.cursor()

# Création table
cursor.execute("""
CREATE TABLE IF NOT EXISTS dictionnaire (
    francais TEXT PRIMARY KEY,
    anglais TEXT
)
""")

conn.commit()


ce projet consiste à créer un traducteur(une application capable de traduire les mots français en anglais)
