#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Enriquecimento e Migração do Hinário Adventista
=========================================================
1. Parte 1: Enriquecimento dos 601 arquivos JSON individuais em hinos_json/
   com base no hinario_completo.json (textos_relacionados, texto_base, temas_relacionados).
2. Parte 2: Criação e povoamento do banco SQLite de alta performance (hinario.db)
   com as tabelas 'hinos' e 'metadados'.
"""

import os
import glob
import json
import sqlite3
import logging
from typing import Dict, Any, Tuple, List, Optional

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("HinarioETL")

# Caminhos padrão do projeto
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HINARIO_COMPLETO_PATH = os.path.join(ROOT_DIR, "Ideia", "hinario_completo.json")
HINOS_JSON_DIR = os.path.join(ROOT_DIR, "hinos_json")
DB_PATH = os.path.join(ROOT_DIR, "basesdedados", "hinario.db")

AUTORES_JSON_PATH = os.path.join(ROOT_DIR, "basesdedados", "autores.json")
CATEGORIAS_JSON_PATH = os.path.join(ROOT_DIR, "basesdedados", "categorias.json")
SUBCATEGORIAS_JSON_PATH = os.path.join(ROOT_DIR, "basesdedados", "subcategorias.json")


def normalize_number(num: Any) -> str:
    """
    Normaliza o número do hino para garantir correspondência exata
    entre strings e inteiros (ex: 1 -> '1', '587_A' -> '587A', ' 001 ' -> '1').
    """
    if num is None:
        return ""
    s = str(num).replace("_", "").replace(" ", "").upper().strip()
    # Se for estritamente numérico, remove zeros à esquerda para casar "001" com "1"
    if s.isdigit():
        return str(int(s))
    # Para casos como "587A", "587B"
    return s


def load_auxiliary_maps() -> Tuple[Dict[int, str], Dict[int, str], Dict[int, Tuple[str, Optional[int]]]]:
    """
    Carrega mapas de autores, categorias e subcategorias para resolução de fallbacks.
    """
    authors_map: Dict[int, str] = {}
    cat_map: Dict[int, str] = {}
    sub_map: Dict[int, Tuple[str, Optional[int]]] = {}

    if os.path.exists(AUTORES_JSON_PATH):
        try:
            with open(AUTORES_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                authors_map = {a["id"]: a["name"] for a in data.get("authors", [])}
        except Exception as e:
            logger.warning(f"Não foi possível carregar autores.json: {e}")

    if os.path.exists(CATEGORIAS_JSON_PATH):
        try:
            with open(CATEGORIAS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                cat_map = {c["id"]: c["name"] for c in data.get("categories", [])}
        except Exception as e:
            logger.warning(f"Não foi possível carregar categorias.json: {e}")

    if os.path.exists(SUBCATEGORIAS_JSON_PATH):
        try:
            with open(SUBCATEGORIAS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                sub_map = {s["id"]: (s["name"], s.get("category")) for s in data.get("subcategories", [])}
        except Exception as e:
            logger.warning(f"Não foi possível carregar subcategorias.json: {e}")

    return authors_map, cat_map, sub_map


def format_autores(
    completo_item: Dict[str, Any],
    hymn_dict: Dict[str, Any],
    authors_map: Dict[int, str]
) -> str:
    """
    Formata os autores do hino a partir de hinario_completo.json com fallback
    para os IDs em lyricsComposer/musicComposer de autores.json.
    """
    autor_letra = (completo_item.get("autor_letra") or "").strip()
    autor_musica = (completo_item.get("autor_musica") or "").strip()

    # Fallback caso estejam vazios no hinario_completo.json (ex: 587A e 587B)
    if not autor_letra and not autor_musica and hymn_dict and authors_map:
        lyrics_ids = hymn_dict.get("lyricsComposer", [])
        music_ids = hymn_dict.get("musicComposer", [])
        letra_names = [authors_map[aid] for aid in lyrics_ids if aid in authors_map]
        musica_names = [authors_map[aid] for aid in music_ids if aid in authors_map]
        autor_letra = ", ".join(filter(None, letra_names))
        autor_musica = ", ".join(filter(None, musica_names))

    if autor_letra and autor_musica:
        if autor_letra == autor_musica:
            return autor_letra
        return f"Letra: {autor_letra} | Música: {autor_musica}"
    elif autor_letra:
        return f"Letra: {autor_letra}"
    elif autor_musica:
        return f"Música: {autor_musica}"
    return ""


def get_categoria_subcategoria(
    completo_item: Dict[str, Any],
    hymn_dict: Dict[str, Any],
    cat_map: Dict[int, str],
    sub_map: Dict[int, Tuple[str, Optional[int]]]
) -> Tuple[str, str]:
    """
    Recupera categoria e subcategoria com fallback via subCategory ID.
    """
    cat = (completo_item.get("categoria") or "").strip()
    subcat = (completo_item.get("subcategoria") or "").strip()

    if (not cat or not subcat) and hymn_dict and sub_map:
        sub_id = hymn_dict.get("subCategory")
        if sub_id in sub_map:
            s_name, c_id = sub_map[sub_id]
            if not subcat:
                subcat = s_name
            if not cat and c_id in cat_map:
                cat = cat_map[c_id]

    return cat, subcat


# ==============================================================================
# PARTE 1: ENRIQUECIMENTO DOS JSONs
# ==============================================================================
def enriquecer_jsons(
    completo_path: str = HINARIO_COMPLETO_PATH,
    hinos_dir: str = HINOS_JSON_DIR
) -> int:
    """
    Lê o hinario_completo.json e atualiza/injeta nos 601 arquivos JSON originais:
      - textos_relacionados (list)
      - texto_base (str)
      - temas_relacionados (list)
    """
    logger.info("=" * 60)
    logger.info("INICIANDO PARTE 1: Enriquecimento dos Arquivos JSON")
    logger.info("=" * 60)

    if not os.path.exists(completo_path):
        raise FileNotFoundError(f"Arquivo hinario_completo não encontrado em: {completo_path}")

    if not os.path.exists(hinos_dir):
        raise FileNotFoundError(f"Diretório de hinos não encontrado em: {hinos_dir}")

    # Carrega hinario_completo.json indexado pelo número normalizado
    with open(completo_path, "r", encoding="utf-8") as f:
        completo_data: List[Dict[str, Any]] = json.load(f)

    completo_index: Dict[str, Dict[str, Any]] = {
        normalize_number(item.get("numero")): item for item in completo_data
    }
    logger.info(f"Carregados {len(completo_index)} hinos de referência do arquivo de curadoria.")

    json_files = sorted(glob.glob(os.path.join(hinos_dir, "*.json")))
    if not json_files:
        raise FileNotFoundError(f"Nenhum arquivo .json encontrado na pasta {hinos_dir}")

    logger.info(f"Encontrados {len(json_files)} arquivos JSON individuais para enriquecer.")

    processados = 0
    nao_encontrados = []

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                hino_json = json.load(f)

            hymn_node = hino_json.get("hymn")
            if not hymn_node:
                logger.warning(f"Arquivo sem nó 'hymn': {os.path.basename(file_path)}")
                continue

            num_norm = normalize_number(hymn_node.get("number"))
            curadoria = completo_index.get(num_norm)

            if not curadoria:
                nao_encontrados.append(file_path)
                logger.warning(f"Hino {num_norm} ({os.path.basename(file_path)}) não encontrado na curadoria.")
                continue

            # Injeção/Atualização dos campos de curadoria teológica
            # 1. textos_relacionados
            hymn_node["textos_relacionados"] = curadoria.get("textos_relacionados", [])

            # 2. texto_base (usa o curado ou fallback para o 'verse' original caso vazio)
            texto_base = curadoria.get("texto_base") or hymn_node.get("verse", "")
            hymn_node["texto_base"] = str(texto_base).strip()

            # 3. temas_relacionados
            hymn_node["temas_relacionados"] = curadoria.get("temas_relacionados", [])

            # Salva o arquivo atualizado mantendo formatação e caracteres UTF-8
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(hino_json, f, ensure_ascii=False, indent=4)

            processados += 1

        except Exception as e:
            logger.error(f"Erro ao processar arquivo {file_path}: {e}", exc_info=True)
            raise

    logger.info(f"Parte 1 concluída com sucesso! Total de arquivos enriquecidos: {processados}/{len(json_files)}")
    if nao_encontrados:
        logger.warning(f"Arquivos sem correspondência ({len(nao_encontrados)}): {nao_encontrados}")

    return processados


# ==============================================================================
# PARTE 2: MIGRAÇÃO PARA SQLITE (hinario.db)
# ==============================================================================
def criar_esquema_sqlite(conn: sqlite3.Connection):
    """
    Cria as tabelas relacionais de alta performance e índices no SQLite.
    """
    cursor = conn.cursor()

    # Otimizações de performance (WAL mode, cache, normal sync)
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA cache_size = -64000;")  # 64MB Cache

    cursor.executescript("""
    -- Tabela Principal de Hinos
    CREATE TABLE IF NOT EXISTS hinos (
        numero TEXT PRIMARY KEY,
        titulo TEXT NOT NULL,
        letra_json TEXT NOT NULL
    );

    -- Tabela de Metadados e Curadoria Teológica
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

    -- Índices para buscas ultrarrápidas no app Flet
    CREATE INDEX IF NOT EXISTS idx_hinos_titulo ON hinos(titulo);
    CREATE INDEX IF NOT EXISTS idx_metadados_categoria ON metadados(categoria);
    CREATE INDEX IF NOT EXISTS idx_metadados_subcategoria ON metadados(subcategoria);

    -- View unificada para simplificar consultas na interface Flet
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
    """)
    conn.commit()


def migrar_para_sqlite(
    db_path: str = DB_PATH,
    hinos_dir: str = HINOS_JSON_DIR,
    completo_path: str = HINARIO_COMPLETO_PATH
) -> int:
    """
    Lê os 601 arquivos JSON enriquecidos e popula o banco SQLite com commits em lote.
    """
    logger.info("=" * 60)
    logger.info("INICIANDO PARTE 2: Migração para SQLite (hinario.db)")
    logger.info("=" * 60)

    authors_map, cat_map, sub_map = load_auxiliary_maps()

    # Carrega dados adicionais de curadoria para metadados complementares
    completo_index: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(completo_path):
        with open(completo_path, "r", encoding="utf-8") as f:
            completo_data = json.load(f)
            completo_index = {
                normalize_number(item.get("numero")): item for item in completo_data
            }

    json_files = sorted(glob.glob(os.path.join(hinos_dir, "*.json")))
    if not json_files:
        raise FileNotFoundError(f"Nenhum arquivo .json encontrado na pasta {hinos_dir}")

    # Remove o banco anterior se existir para garantir integridade limpa
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            logger.info(f"Banco existente removido para recriação limpa: {db_path}")
        except Exception as e:
            logger.warning(f"Não foi possível remover banco antigo: {e}")

    conn = sqlite3.connect(db_path)
    try:
        criar_esquema_sqlite(conn)

        hinos_batch: List[Tuple[str, str, str]] = []
        metadados_batch: List[Tuple[str, str, str, str, str, str, str, str]] = []

        for file_path in json_files:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            hymn = data.get("hymn", {})
            lyrics = data.get("lyrics", [])

            numero = str(hymn.get("number", "")).strip()
            num_norm = normalize_number(numero)
            titulo = hymn.get("title", "").strip()

            # Serializa array de estrofes original
            letra_json_str = json.dumps(lyrics, ensure_ascii=False)

            curadoria_item = completo_index.get(num_norm, {})

            # Categoria e Subcategoria
            cat, subcat = get_categoria_subcategoria(curadoria_item, hymn, cat_map, sub_map)

            # Texto base
            texto_base = (
                hymn.get("texto_base")
                or curadoria_item.get("texto_base")
                or hymn.get("verse", "")
            ).strip()

            # Textos relacionados (array serializado)
            textos_relacionados = (
                hymn.get("textos_relacionados")
                or curadoria_item.get("textos_relacionados", [])
            )
            textos_rel_json_str = json.dumps(textos_relacionados, ensure_ascii=False)

            # Temas relacionados (array serializado)
            temas_relacionados = (
                hymn.get("temas_relacionados")
                or curadoria_item.get("temas_relacionados", [])
            )
            temas_rel_json_str = json.dumps(temas_relacionados, ensure_ascii=False)

            # Autores
            autores = format_autores(curadoria_item, hymn, authors_map)

            # Video URL
            video_url = (
                hymn.get("youtubeURL")
                or curadoria_item.get("link_video", "")
            ).strip()

            # Adiciona aos lotes
            hinos_batch.append((numero, titulo, letra_json_str))
            metadados_batch.append((
                numero,
                cat,
                subcat,
                texto_base,
                textos_rel_json_str,
                temas_rel_json_str,
                autores,
                video_url
            ))

        # Inserção em Lote com Transação Atômica
        cursor = conn.cursor()
        logger.info(f"Inserindo {len(hinos_batch)} registros na tabela 'hinos'...")
        cursor.executemany(
            "INSERT INTO hinos (numero, titulo, letra_json) VALUES (?, ?, ?)",
            hinos_batch
        )

        logger.info(f"Inserindo {len(metadados_batch)} registros na tabela 'metadados'...")
        cursor.executemany(
            """
            INSERT INTO metadados (
                hino_numero,
                categoria,
                subcategoria,
                texto_base,
                textos_relacionados_json,
                temas_relacionados_json,
                autores,
                video_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            metadados_batch
        )

        conn.commit()
        logger.info("Transação confirmada (commit) com sucesso!")

        # Validação pós-migração
        cursor.execute("SELECT COUNT(*) FROM hinos")
        count_hinos = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM metadados")
        count_meta = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM v_hinos_completos")
        count_view = cursor.fetchone()[0]

        logger.info(f"Validação: hinos={count_hinos}, metadados={count_meta}, view={count_view}")

        return count_hinos

    except Exception as e:
        conn.rollback()
        logger.error(f"Erro durante migração SQLite: {e}. Rollback efetuado.", exc_info=True)
        raise
    finally:
        conn.close()


def main():
    """
    Executa o pipeline completo: Parte 1 (Enriquecimento) e Parte 2 (Migração SQLite).
    """
    logger.info("Iniciando processo completo do Hinário...")
    try:
        # Parte 1
        total_enriquecidos = enriquecer_jsons()

        # Parte 2
        total_migrados = migrar_para_sqlite()

        logger.info("=" * 60)
        logger.info("PIPELINE CONCLUÍDO COM SUCESSO!")
        logger.info(f" -> {total_enriquecidos} arquivos JSON atualizados em '{os.path.relpath(HINOS_JSON_DIR)}'")
        logger.info(f" -> {total_migrados} hinos migrados para o banco SQLite '{os.path.relpath(DB_PATH)}'")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Falha na execução do pipeline: {e}")
        exit(1)


if __name__ == "__main__":
    main()

