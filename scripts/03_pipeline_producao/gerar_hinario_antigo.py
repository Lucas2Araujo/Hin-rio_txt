#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de Banco de Dados SQLite do Hinário Antigo (hinario_antigo.db)
=====================================================================
Padronizado 100% com a arquitetura relacional e FTS5 do hinario.db para
aplicativos Flet de alta performance.

Tabelas Criadas:
- hino: Tabela principal com dados estruturados (id, numero, titulo, letra,
        letra_json, autor_letra, autor_musica, autores, texto_base, categoria,
        subcategoria, link_video).
- hino_fts: Tabela virtual FTS5 para busca em tempo real sem acentos.
- tema & hino_tema: Tabelas relacionais para categorias e temas.
- texto_biblico & hino_texto: Tabelas relacionais para referências bíblicas.
- favorito, historico, lista_culto, item_lista_culto, preferencias:
  Tabelas de estado e gerenciamento do app Flet.
- hinos, metadados, v_hinos_completos: Camada de compatibilidade.
"""

import os
import re
import json
import sqlite3
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Tuple, Optional
from bs4 import BeautifulSoup

# Configuração de Logging elegante
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("HinarioAntigoETL")


def normalize_text_for_comparison(text: str) -> str:
    """
    Normaliza texto removendo pontuações, aspas e espaços extras
    para comparação segura e resiliente entre fontes XML e HTML.
    """
    if not text:
        return ""
    return re.sub(r"[^a-zA-Z0-9áéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]", "", text.lower())


def resolve_file_path(base_dir: str, candidate_paths: List[str]) -> str:
    """
    Busca o primeiro caminho existente a partir de uma lista de candidatos relativos/absolutos.
    """
    for rel_path in candidate_paths:
        full_path = os.path.join(base_dir, rel_path) if not os.path.isabs(rel_path) else rel_path
        if os.path.exists(full_path):
            return full_path
    raise FileNotFoundError(f"Nenhum dos caminhos candidatos foi encontrado: {candidate_paths}")


def carregar_categorias(xml_path: str) -> Dict[int, Dict[str, str]]:
    """
    Lê o XML de categorias (category.xml / categorias.xml) e cria o mapa:
    numero_hino -> {"categoria": "...", "subcategoria": "..."}
    """
    logger.info(f"Carregando categorias a partir de: {xml_path}")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    mapa_categorias: Dict[int, Dict[str, str]] = {}

    for main_cat in root.findall("category"):
        main_name = (main_cat.get("name") or "").strip()
        subcats = main_cat.findall("category")

        if subcats:
            for sub_cat in subcats:
                sub_name = (sub_cat.get("name") or "").strip()
                for hymn_tag in sub_cat.findall("hymn"):
                    h_text = (hymn_tag.text or "").strip()
                    if h_text.isdigit():
                        h_num = int(h_text)
                        mapa_categorias[h_num] = {
                            "categoria": main_name,
                            "subcategoria": sub_name
                        }
        else:
            for hymn_tag in main_cat.findall("hymn"):
                h_text = (hymn_tag.text or "").strip()
                if h_text.isdigit():
                    h_num = int(h_text)
                    mapa_categorias[h_num] = {
                        "categoria": main_name,
                        "subcategoria": ""
                    }

    logger.info(f"Categorias carregadas para {len(mapa_categorias)} hinos.")
    return mapa_categorias


def carregar_metadados(xml_path: str) -> Dict[int, Dict[str, Any]]:
    """
    Lê o XML de metadados (hymn_detail.xml / hymns.xml) e cria o mapa:
    numero_hino -> {
        "original": "...",
        "verse_ref": "...",
        "history": "...",
        "authors": [name1, name2, ...]
    }
    """
    logger.info(f"Carregando metadados de hinos a partir de: {xml_path}")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    mapa_metadados: Dict[int, Dict[str, Any]] = {}

    for hymn_node in root.findall("hymn"):
        num_str = (hymn_node.get("number") or "").strip()
        if not num_str.isdigit():
            continue
        h_num = int(num_str)

        orig_elem = hymn_node.find("original")
        original_title = (orig_elem.text or "").strip() if orig_elem is not None else ""

        verse_elem = hymn_node.find("verse")
        verse_ref = (verse_elem.get("reference") or "").strip() if verse_elem is not None else ""

        hist_elem = hymn_node.find("history")
        history = (hist_elem.text or "").strip() if hist_elem is not None else ""

        authors: List[str] = []
        authors_elem = hymn_node.find("authors")
        if authors_elem is not None:
            for auth in authors_elem.findall("author"):
                name = (auth.get("name") or "").strip()
                if name:
                    authors.append(name)

        mapa_metadados[h_num] = {
            "original": original_title,
            "verse_ref": verse_ref,
            "history": history,
            "authors": authors
        }

    logger.info(f"Metadados carregados para {len(mapa_metadados)} hinos.")
    return mapa_metadados


def resolver_autores(
    legend_author: str,
    detail_authors: List[str]
) -> Tuple[str, str, str]:
    """
    Determina autor_letra, autor_musica e a string formatada autores:
    Retorna (autor_letra, autor_musica, autores_formatado).
    """
    autor_letra = ""
    autor_musica = ""

    # Se detail_authors possui 2 ou mais autores
    if len(detail_authors) >= 2:
        autor_letra = detail_authors[0]
        autor_musica = detail_authors[1]
    elif len(detail_authors) == 1:
        autor_letra = detail_authors[0]
        # Se legend_author tiver divisão com '|', extrai a música de lá
        if "|" in legend_author:
            parts = [p.strip() for p in legend_author.split("|") if p.strip()]
            if len(parts) > 1:
                autor_musica = parts[1]
    elif legend_author:
        if "|" in legend_author:
            parts = [p.strip() for p in legend_author.split("|") if p.strip()]
            autor_letra = parts[0] if parts else ""
            autor_musica = parts[1] if len(parts) > 1 else ""
        else:
            autor_letra = legend_author

    # Formatação padronizada da string legível
    if autor_letra and autor_musica:
        autores_str = f"Letra: {autor_letra} | Música: {autor_musica}"
    elif autor_letra:
        autores_str = autor_letra
    elif autor_musica:
        autores_str = f"Música: {autor_musica}"
    else:
        autores_str = ""

    return autor_letra, autor_musica, autores_str


def extrair_letra_hino(
    xml_path: str,
    html_path: str
) -> Tuple[str, str, str, str, List[Dict[str, Any]]]:
    """
    Processa h{i}.xml e {i}.html:
    Retorna (titulo, versiculo_ref_xml, author_xml, letra_plano, letra_array).
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    titulo = (root.get("title") or "").strip()
    versiculo_ref_xml = (root.get("verse") or "").strip()
    author_xml = (root.get("author") or "").strip()
    xml_text_nodes = root.findall("text")

    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    p_tags = soup.find_all("p")

    # Mapeia refrões do HTML
    html_chorus_normalized: List[str] = []
    for p in p_tags:
        classes = p.get("class", [])
        if isinstance(classes, str):
            classes = [classes]
        if any(c in ["chorus", "chorusFirst"] for c in classes):
            norm_p = normalize_text_for_comparison(p.get_text())
            if norm_p:
                html_chorus_normalized.append(norm_p)

    letra_array: List[Dict[str, Any]] = []
    estrofes_plano: List[str] = []

    for idx, text_node in enumerate(xml_text_nodes):
        raw_cdata = text_node.text or ""
        lines = [line.strip() for line in raw_cdata.split("\n") if line.strip()]
        if not lines:
            continue

        norm_block = normalize_text_for_comparison(raw_cdata)
        is_italic = (text_node.get("italic") == "true")
        matches_html_chorus = any(
            norm_block and (norm_block in hct or hct in norm_block)
            for hct in html_chorus_normalized
        )

        zip_chorus = False
        if len(xml_text_nodes) == len(p_tags) and idx < len(p_tags):
            p_classes = p_tags[idx].get("class", [])
            if isinstance(p_classes, str):
                p_classes = [p_classes]
            zip_chorus = any(c in ["chorus", "chorusFirst"] for c in p_classes)

        is_chorus = is_italic or matches_html_chorus or zip_chorus
        image_val = text_node.get("image") or ""

        letra_array.append({
            "order": len(letra_array) + 1,
            "chorus": bool(is_chorus),
            "image": image_val,
            "strophe": lines
        })
        estrofes_plano.append("\n".join(lines))

    letra_plano = "\n\n".join(estrofes_plano)
    return titulo, versiculo_ref_xml, author_xml, letra_plano, letra_array


def criar_esquema_banco(conn: sqlite3.Connection):
    """
    Cria a estrutura completa de tabelas relacionais, FTS5, índices e views
    no mesmo padrão exato do hinario.db.
    """
    cursor = conn.cursor()

    # Pragmas para máxima performance
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA temp_store = MEMORY;")
    cursor.execute("PRAGMA cache_size = -64000;")  # 64MB Cache
    cursor.execute("PRAGMA mmap_size = 268435456;")  # 256MB Mmap

    cursor.executescript("""
    -- 1. Tabela Principal Padronizada de Hinos
    CREATE TABLE IF NOT EXISTS hino (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero TEXT NOT NULL UNIQUE,
        titulo TEXT NOT NULL,
        letra TEXT,
        letra_json TEXT,
        autor_letra TEXT,
        autor_musica TEXT,
        autores TEXT,
        texto_base TEXT,
        categoria TEXT,
        subcategoria TEXT,
        link_video TEXT
    );

    -- 2. Tabela Virtual FTS5 para Busca Ultrarrápida no App
    CREATE VIRTUAL TABLE IF NOT EXISTS hino_fts USING fts5(
        numero,
        titulo,
        letra,
        categoria,
        subcategoria,
        texto_base,
        autor_letra,
        autor_musica,
        temas,
        textos,
        tokenize="unicode61 remove_diacritics 2"
    );

    -- 3. Tabelas de Temas / Categorias (N:N)
    CREATE TABLE IF NOT EXISTS tema (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS hino_tema (
        hino_id INTEGER NOT NULL,
        tema_id INTEGER NOT NULL,
        PRIMARY KEY (hino_id, tema_id),
        FOREIGN KEY (hino_id) REFERENCES hino(id) ON DELETE CASCADE,
        FOREIGN KEY (tema_id) REFERENCES tema(id) ON DELETE CASCADE
    );

    -- 4. Tabelas de Textos Bíblicos de Referência (N:N)
    CREATE TABLE IF NOT EXISTS texto_biblico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referencia TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS hino_texto (
        hino_id INTEGER NOT NULL,
        texto_id INTEGER NOT NULL,
        PRIMARY KEY (hino_id, texto_id),
        FOREIGN KEY (hino_id) REFERENCES hino(id) ON DELETE CASCADE,
        FOREIGN KEY (texto_id) REFERENCES texto_biblico(id) ON DELETE CASCADE
    );

    -- 5. Tabelas de Gerenciamento do App Flet
    CREATE TABLE IF NOT EXISTS favorito (
        hino_id INTEGER PRIMARY KEY,
        data_favoritado DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (hino_id) REFERENCES hino(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hino_id INTEGER NOT NULL,
        data_acesso DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (hino_id) REFERENCES hino(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS lista_culto (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tema_gerador TEXT,
        data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS item_lista_culto (
        lista_id INTEGER NOT NULL,
        hino_id INTEGER NOT NULL,
        ordem_execucao INTEGER NOT NULL,
        PRIMARY KEY (lista_id, hino_id),
        FOREIGN KEY (lista_id) REFERENCES lista_culto(id) ON DELETE CASCADE,
        FOREIGN KEY (hino_id) REFERENCES hino(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS preferencias (
        chave TEXT PRIMARY KEY,
        valor TEXT
    );

    -- 6. Camada de Compatibilidade (hinos, metadados, view)
    CREATE TABLE IF NOT EXISTS hinos (
        numero TEXT PRIMARY KEY,
        titulo TEXT NOT NULL,
        letra_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS metadados (
        hino_numero TEXT PRIMARY KEY,
        categoria TEXT,
        subcategoria TEXT,
        texto_base TEXT,
        textos_relacionados_json TEXT,
        temas_relacionados_json TEXT,
        autores TEXT,
        video_url TEXT,
        FOREIGN KEY (hino_numero) REFERENCES hinos(numero) ON DELETE CASCADE
    );

    CREATE VIEW IF NOT EXISTS v_hinos_completos AS
    SELECT 
        h.numero,
        h.titulo,
        h.letra_json,
        m.categoria,
        m.subcategoria,
        m.texto_base,
        m.textos_relacionados_json,
        m.temas_relacionados_json,
        m.autores,
        m.video_url
    FROM hinos h
    LEFT JOIN metadados m ON h.numero = m.hino_numero;

    -- 7. Índices de Otimização
    CREATE INDEX IF NOT EXISTS idx_hino_numero ON hino(numero);
    CREATE INDEX IF NOT EXISTS idx_hino_titulo ON hino(titulo);
    CREATE INDEX IF NOT EXISTS idx_hino_categoria ON hino(categoria);
    CREATE INDEX IF NOT EXISTS idx_hino_subcategoria ON hino(subcategoria);
    CREATE INDEX IF NOT EXISTS idx_hinos_titulo ON hinos(titulo);
    CREATE INDEX IF NOT EXISTS idx_metadados_categoria ON metadados(categoria);
    CREATE INDEX IF NOT EXISTS idx_metadados_subcategoria ON metadados(subcategoria);
    CREATE INDEX IF NOT EXISTS idx_hino_tema_hino ON hino_tema(hino_id);
    CREATE INDEX IF NOT EXISTS idx_hino_tema_tema ON hino_tema(tema_id);
    CREATE INDEX IF NOT EXISTS idx_hino_texto_hino ON hino_texto(hino_id);
    CREATE INDEX IF NOT EXISTS idx_favorito_data ON favorito(data_favoritado DESC);
    CREATE INDEX IF NOT EXISTS idx_historico_hino_data ON historico(hino_id, data_acesso DESC);
    """)

    conn.commit()


def processar_e_gerar_banco(
    base_dir: str = ".",
    db_name: str = "hinario_antigo.db",
    total_hinos: int = 613
) -> str:
    """
    Executa o pipeline completo de povoamento do banco padronizado.
    """
    logger.info("=" * 70)
    logger.info("GERANDO BANCO HINÁRIO ANTIGO (PADRÃO HINARIO.DB + FTS5)")
    logger.info("=" * 70)

    category_file = resolve_file_path(base_dir, [
        "hinarioAntigo/xmls/category.xml",
        "hinarioAntigo/xmls/categorias.xml",
        "category.xml",
        "categorias.xml"
    ])

    detail_file = resolve_file_path(base_dir, [
        "hinarioAntigo/xmls/hymn_detail.xml",
        "hinarioAntigo/xmls/hymns.xml",
        "hymn_detail.xml",
        "hymns.xml"
    ])

    xmls_dir = resolve_file_path(base_dir, [
        "hinarioAntigo/xmls/hymns",
        "xmls/hymns",
        "hymns"
    ])

    htmls_dir = resolve_file_path(base_dir, [
        "hinarioAntigo/hinos_html/html",
        "hinos_html/html",
        "html"
    ])

    db_path = os.path.join(base_dir, db_name) if not os.path.isabs(db_name) else db_name

    mapa_categorias = carregar_categorias(category_file)
    mapa_metadados = carregar_metadados(detail_file)

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            logger.info(f"Banco existente removido para recriação limpa: {db_path}")
        except Exception as e:
            logger.warning(f"Aviso ao remover banco existente: {e}")

    conn = sqlite3.connect(db_path)
    criar_esquema_banco(conn)
    cursor = conn.cursor()

    # Estruturas para tabelas relacionais
    temas_dict: Dict[str, int] = {}       # nome_tema -> id
    textos_dict: Dict[str, int] = {}      # referencia -> id

    logger.info(f"Processando {total_hinos} hinos...")

    for i in range(1, total_hinos + 1):
        num_str = str(i)
        xml_file = os.path.join(xmls_dir, f"h{i}.xml")
        html_file = os.path.join(htmls_dir, f"{i}.html")

        titulo_pt, versiculo_ref_xml, author_xml, letra_plano, letra_array = extrair_letra_hino(xml_file, html_file)

        cat_info = mapa_categorias.get(i, {"categoria": "", "subcategoria": ""})
        meta_info = mapa_metadados.get(i, {
            "original": "",
            "verse_ref": "",
            "history": "",
            "authors": []
        })

        categoria = cat_info["categoria"]
        subcategoria = cat_info["subcategoria"]
        texto_base = meta_info["verse_ref"] or versiculo_ref_xml

        # Resolve autores
        autor_letra, autor_musica, autores_str = resolver_autores(author_xml, meta_info["authors"])

        letra_json_str = json.dumps(letra_array, ensure_ascii=False)
        temas_list = [t for t in [categoria, subcategoria] if t]
        textos_rel_list = [texto_base] if texto_base else []

        # 1. Inserção na tabela principal 'hino'
        cursor.execute("""
        INSERT INTO hino (
            numero,
            titulo,
            letra,
            letra_json,
            autor_letra,
            autor_musica,
            autores,
            texto_base,
            categoria,
            subcategoria,
            link_video
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            num_str,
            titulo_pt,
            letra_plano,
            letra_json_str,
            autor_letra,
            autor_musica,
            autores_str,
            texto_base,
            categoria,
            subcategoria,
            ""  # link_video
        ))
        hino_id = cursor.lastrowid

        # 2. Inserção na tabela FTS5 'hino_fts'
        temas_str = " ".join(temas_list)
        cursor.execute("""
        INSERT INTO hino_fts (
            numero,
            titulo,
            letra,
            categoria,
            subcategoria,
            texto_base,
            autor_letra,
            autor_musica,
            temas,
            textos
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            num_str,
            titulo_pt,
            letra_plano,
            categoria,
            subcategoria,
            texto_base,
            autor_letra,
            autor_musica,
            temas_str,
            texto_base
        ))

        # 3. Inserção na camada de compatibilidade 'hinos' e 'metadados'
        cursor.execute("""
        INSERT INTO hinos (numero, titulo, letra_json)
        VALUES (?, ?, ?);
        """, (num_str, titulo_pt, letra_json_str))

        cursor.execute("""
        INSERT INTO metadados (
            hino_numero,
            categoria,
            subcategoria,
            texto_base,
            textos_relacionados_json,
            temas_relacionados_json,
            autores,
            video_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            num_str,
            categoria,
            subcategoria,
            texto_base,
            json.dumps(textos_rel_list, ensure_ascii=False),
            json.dumps(temas_list, ensure_ascii=False),
            autores_str,
            ""
        ))

        # 4. Inserção relacional: tema e hino_tema
        for t_nome in temas_list:
            if t_nome not in temas_dict:
                cursor.execute("INSERT OR IGNORE INTO tema (nome) VALUES (?);", (t_nome,))
                cursor.execute("SELECT id FROM tema WHERE nome = ?;", (t_nome,))
                t_row = cursor.fetchone()
                if t_row:
                    temas_dict[t_nome] = t_row[0]
            if t_nome in temas_dict:
                cursor.execute("""
                INSERT OR IGNORE INTO hino_tema (hino_id, tema_id) VALUES (?, ?);
                """, (hino_id, temas_dict[t_nome]))

        # 5. Inserção relacional: texto_biblico e hino_texto
        if texto_base:
            if texto_base not in textos_dict:
                cursor.execute("INSERT OR IGNORE INTO texto_biblico (referencia) VALUES (?);", (texto_base,))
                cursor.execute("SELECT id FROM texto_biblico WHERE referencia = ?;", (texto_base,))
                ref_row = cursor.fetchone()
                if ref_row:
                    textos_dict[texto_base] = ref_row[0]
            if texto_base in textos_dict:
                cursor.execute("""
                INSERT OR IGNORE INTO hino_texto (hino_id, texto_id) VALUES (?, ?);
                """, (hino_id, textos_dict[texto_base]))

    conn.commit()
    conn.close()

    logger.info("=" * 70)
    logger.info(f"BANCO PADRONIZADO GERADO COM SUCESSO EM: {db_path}")
    logger.info("=" * 70)
    return db_path


def testar_banco_padronizado(db_path: str):
    """
    Executa testes de validação, consultas FTS5 e verificação de integridade.
    """
    logger.info("VALIDANDO BANCO PADRONIZADO...")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Contagens
    cur.execute("SELECT COUNT(*) FROM hino;")
    total_hino = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM hinos;")
    total_hinos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM metadados;")
    total_meta = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM hino_fts;")
    total_fts = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tema;")
    total_temas = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM texto_biblico;")
    total_textos = cur.fetchone()[0]

    logger.info(f"Tabela 'hino': {total_hino} registros")
    logger.info(f"Tabela 'hinos': {total_hinos} registros")
    logger.info(f"Tabela 'metadados': {total_meta} registros")
    logger.info(f"Tabela 'hino_fts': {total_fts} registros")
    logger.info(f"Tabela 'tema': {total_temas} temas")
    logger.info(f"Tabela 'texto_biblico': {total_textos} referências bíblicas")

    # Teste de busca FTS5 (busca sem acento)
    termo_busca = "gloria"
    cur.execute("""
    SELECT numero, titulo, autor_letra, autor_musica, texto_base
    FROM hino_fts
    WHERE hino_fts MATCH ?
    LIMIT 3;
    """, (termo_busca,))
    fts_results = cur.fetchall()
    logger.info(f"\nTeste de Busca FTS5 por '{termo_busca}': {len(fts_results)} resultados exibidos:")
    for r in fts_results:
        logger.info(f"  Hino {r[0]}: {r[1]} | Autores: {r[2]} / {r[3]} | Ref: {r[4]}")

    # Exemplo detalhado
    cur.execute("SELECT * FROM hino WHERE numero = '1';")
    h1 = cur.fetchone()
    cols = [d[0] for d in cur.description]
    logger.info("\nExemplo Hino 1 na tabela 'hino':")
    for c, v in zip(cols, h1):
        v_str = str(v)[:90] + "..." if len(str(v)) > 90 else str(v)
        logger.info(f"  {c}: {v_str}")

    conn.close()


if __name__ == "__main__":
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    db_output = os.path.join(root_dir, "basesdedados", "hinario_antigo.db")
    db_gerado = processar_e_gerar_banco(base_dir=root_dir, db_name=db_output)
    testar_banco_padronizado(db_gerado)

