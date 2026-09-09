from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BASES_DIR = ROOT_DIR / "basesdedados"

import sqlite3
import re

# Connect to original
conn_orig = sqlite3.connect(BASES_DIR / 'hinario_app.db')
cur_orig = conn_orig.cursor()

# Get all data
cur_orig.execute("SELECT * FROM hinos")
hinos_raw = cur_orig.fetchall()

# Columns: "Número", "Título", "Temas Relacionados", "Textos Relacionados", "Link do Vídeo", "Texto Base", "Categoria", "Subcategoria", "Autor da Letra", "Autor da Música", "letra"

# Create new DB
conn_new = sqlite3.connect(BASES_DIR / 'hinario_normalizado.db')
cur_new = conn_new.cursor()

# Create tables
cur_new.executescript("""
CREATE TABLE hino (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT,
    titulo TEXT,
    letra TEXT,
    autor_letra TEXT,
    autor_musica TEXT,
    texto_base TEXT,
    categoria TEXT,
    subcategoria TEXT,
    link_video TEXT
);

CREATE TABLE tema (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT UNIQUE
);

CREATE TABLE hino_tema (
    hino_id INTEGER,
    tema_id INTEGER,
    FOREIGN KEY(hino_id) REFERENCES hino(id),
    FOREIGN KEY(tema_id) REFERENCES tema(id),
    PRIMARY KEY(hino_id, tema_id)
);

CREATE TABLE texto_biblico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referencia TEXT UNIQUE
);

CREATE TABLE hino_texto (
    hino_id INTEGER,
    texto_id INTEGER,
    FOREIGN KEY(hino_id) REFERENCES hino(id),
    FOREIGN KEY(texto_id) REFERENCES texto_biblico(id),
    PRIMARY KEY(hino_id, texto_id)
);

-- Tabelas propostas para as funcionalidades do app (vazias por enquanto)
CREATE TABLE favorito (
    hino_id INTEGER PRIMARY KEY,
    data_favoritado DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(hino_id) REFERENCES hino(id)
);

CREATE TABLE historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hino_id INTEGER,
    data_acesso DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(hino_id) REFERENCES hino(id)
);

CREATE TABLE lista_culto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_gerador TEXT,
    data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE item_lista_culto (
    lista_id INTEGER,
    hino_id INTEGER,
    ordem_execucao INTEGER,
    FOREIGN KEY(lista_id) REFERENCES lista_culto(id),
    FOREIGN KEY(hino_id) REFERENCES hino(id),
    PRIMARY KEY(lista_id, hino_id)
);
""")

# Dictionaries to keep track of inserted themes and texts
temas_dict = {}
textos_dict = {}

for row in hinos_raw:
    numero = str(row[0]) if row[0] else ""
    titulo = row[1]
    temas_raw = row[2] if row[2] else ""
    textos_raw = row[3] if row[3] else ""
    link = row[4]
    texto_base = row[5]
    categoria = row[6]
    subcat = row[7]
    aut_letra = row[8]
    aut_musica = row[9]
    letra = row[10]
    
    # Insert Hino
    cur_new.execute("""
        INSERT INTO hino (numero, titulo, letra, autor_letra, autor_musica, texto_base, categoria, subcategoria, link_video)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (numero, titulo, letra, aut_letra, aut_musica, texto_base, categoria, subcat, link))
    hino_id = cur_new.lastrowid
    
    # Process Themes
    temas = [t.strip() for t in temas_raw.split('|') if t.strip()]
    for t in temas:
        if t not in temas_dict:
            cur_new.execute("INSERT OR IGNORE INTO tema (nome) VALUES (?)", (t,))
            cur_new.execute("SELECT id FROM tema WHERE nome = ?", (t,))
            temas_dict[t] = cur_new.fetchone()[0]
        tema_id = temas_dict[t]
        cur_new.execute("INSERT OR IGNORE INTO hino_tema (hino_id, tema_id) VALUES (?, ?)", (hino_id, tema_id))
        
    # Process Texts
    textos = [txt.strip() for txt in textos_raw.split('|') if txt.strip()]
    for txt in textos:
        if txt not in textos_dict:
            cur_new.execute("INSERT OR IGNORE INTO texto_biblico (referencia) VALUES (?)", (txt,))
            cur_new.execute("SELECT id FROM texto_biblico WHERE referencia = ?", (txt,))
            textos_dict[txt] = cur_new.fetchone()[0]
        texto_id = textos_dict[txt]
        cur_new.execute("INSERT OR IGNORE INTO hino_texto (hino_id, texto_id) VALUES (?, ?)", (hino_id, texto_id))

conn_new.commit()
conn_orig.close()
conn_new.close()

import os
print("Database migrated successfully. Path:", os.path.abspath('hinario_normalizado.db'))