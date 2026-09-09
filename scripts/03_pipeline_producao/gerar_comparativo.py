#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de Banco de Dados SQLite Comparativo (hinario_comparativo.db)
====================================================================
Cruza os hinos do Hinário Novo (hinario.db) e do Hinário Antigo (hinario_antigo.db),
identificando hinos preservados (idênticos ou modificados), hinos inéditos e hinos
descontinuados, gerando diffs pré-calculados em formato Unified Diff e JSON estruturado.

Tabelas:
- comparativo_hinos: Tabela principal com cruzamento, status, métricas e diffs.
- comparativo_fts: Tabela virtual FTS5 para busca em tempo real no app Flet.
"""

import os
import re
import json
import sqlite3
import logging
import difflib
import glob
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Tuple, Optional, Set

# Configuração de Logging elegante
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ComparativoETL")


def norm_clean(t: str) -> str:
    """Remove pontuação e formatação para comparação de similaridade de texto."""
    if not t:
        return ""
    return re.sub(r"[^a-zA-Z0-9áéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]", "", t.lower())


def norm_simple(t: str) -> str:
    """Remove caracteres não alfanuméricos ASCII simples."""
    if not t:
        return ""
    return re.sub(r"[^a-zA-Z0-9]", "", t.lower())


def clean_lines(t: str) -> List[str]:
    """Retorna lista de linhas limpas não vazias."""
    if not t:
        return []
    return [l.strip() for l in t.splitlines() if l.strip()]


def carregar_dados_hinarios(
    db_novo_path: str,
    db_antigo_path: str,
    hinos_json_dir: str,
    hymn_detail_path: str
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """
    Carrega todos os dados necessários do Hinário Novo e do Hinário Antigo.
    """
    logger.info("Carregando dados de hinario.db (Novo) e hinario_antigo.db (Antigo)...")

    # 1. Carregar Antigo
    conn_old = sqlite3.connect(db_antigo_path)
    cur_old = conn_old.cursor()
    cur_old.execute("""
    SELECT numero, titulo, letra, letra_json, autores, categoria, subcategoria, texto_base
    FROM hino;
    """)
    old_hymns: Dict[str, Dict[str, Any]] = {}
    for num, tit, let, let_j, aut, cat, sub, vref in cur_old.fetchall():
        lines = clean_lines(let)
        old_hymns[str(num)] = {
            "numero": str(num),
            "titulo": tit,
            "norm_titulo": norm_simple(tit),
            "letra": let or "",
            "letra_json": let_j or "[]",
            "lines": lines,
            "first_line": norm_simple(lines[0]) if lines else "",
            "original": "",
            "norm_original": "",
            "autores": aut or "",
            "categoria": cat or "",
            "subcategoria": sub or "",
            "texto_base": vref or ""
        }
    conn_old.close()

    # Enriquecer Antigo com original de hymn_detail.xml se existir
    if os.path.exists(hymn_detail_path):
        try:
            dtree = ET.parse(hymn_detail_path)
            for h in dtree.getroot().findall("hymn"):
                num = str(int(h.get("number", "0")))
                orig = h.find("original")
                if num in old_hymns and orig is not None and orig.text:
                    orig_text = orig.text.strip()
                    old_hymns[num]["original"] = orig_text
                    old_hymns[num]["norm_original"] = norm_simple(orig_text)
        except Exception as e:
            logger.warning(f"Aviso ao ler {hymn_detail_path}: {e}")

    # 2. Carregar Novo
    conn_new = sqlite3.connect(db_novo_path)
    cur_new = conn_new.cursor()
    cur_new.execute("""
    SELECT numero, titulo, letra, letra_json, autores, categoria, subcategoria, texto_base
    FROM hino;
    """)
    new_hymns: Dict[str, Dict[str, Any]] = {}
    for num, tit, let, let_j, aut, cat, sub, vref in cur_new.fetchall():
        lines = clean_lines(let)
        new_hymns[str(num)] = {
            "numero": str(num),
            "titulo": tit,
            "norm_titulo": norm_simple(tit),
            "letra": let or "",
            "letra_json": let_j or "[]",
            "lines": lines,
            "first_line": norm_simple(lines[0]) if lines else "",
            "original": "",
            "norm_original": "",
            "autores": aut or "",
            "categoria": cat or "",
            "subcategoria": sub or "",
            "texto_base": vref or ""
        }
    conn_new.close()

    # Enriquecer Novo com originalTitle de hinos_json
    if os.path.exists(hinos_json_dir):
        for jf in glob.glob(os.path.join(hinos_json_dir, "*.json")):
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f).get("hymn", {})
                    num_raw = str(data.get("number", "")).replace("_", "").replace(" ", "").upper()
                    if num_raw.isdigit():
                        num_raw = str(int(num_raw))
                    if num_raw in new_hymns:
                        orig = (data.get("originalTitle") or "").strip()
                        new_hymns[num_raw]["original"] = orig
                        new_hymns[num_raw]["norm_original"] = norm_simple(orig)
            except Exception as e:
                logger.warning(f"Aviso ao ler {jf}: {e}")

    logger.info(f"Carregados: {len(new_hymns)} hinos novos e {len(old_hymns)} hinos antigos.")
    return new_hymns, old_hymns


def gerar_diffs_e_metricas(
    letra_antiga: str,
    letra_nova: str,
    titulo_antigo: str,
    titulo_novo: str,
    num_antigo: str,
    num_novo: str
) -> Tuple[bool, float, str, str, str]:
    """
    Compara duas letras e gera:
    Retorna (modificado, similaridade_pct, diff_texto, diff_json_str, resumo_alteracoes).
    """
    norm_ant = norm_clean(letra_antiga)
    norm_nov = norm_clean(letra_nova)

    # Similaridade textual global (0.0 a 100.0)
    sim_ratio = difflib.SequenceMatcher(None, norm_ant, norm_nov).ratio() * 100.0
    similaridade_pct = round(sim_ratio, 1)

    old_lines = clean_lines(letra_antiga)
    new_lines = clean_lines(letra_nova)

    # 1. Unified Diff (formato legível Git / Markdown)
    udiff_lines = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"Antigo #{num_antigo} ({titulo_antigo})",
        tofile=f"Novo #{num_novo} ({titulo_novo})",
        lineterm=""
    ))
    diff_texto = "\n".join(udiff_lines)

    # 2. Diff Estruturado JSON para Flet
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    opcodes = matcher.get_opcodes()

    blocos: List[Dict[str, Any]] = []
    linhas_adicionadas = 0
    linhas_removidas = 0
    linhas_alteradas = 0
    linhas_iguais = 0

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            linhas_iguais += (i2 - i1)
            for l in old_lines[i1:i2]:
                blocos.append({"tipo": "igual", "texto": l})
        elif tag == "replace":
            linhas_alteradas += max(i2 - i1, j2 - j1)
            blocos.append({
                "tipo": "modificado",
                "antigo": old_lines[i1:i2],
                "novo": new_lines[j1:j2]
            })
        elif tag == "delete":
            linhas_removidas += (i2 - i1)
            for l in old_lines[i1:i2]:
                blocos.append({"tipo": "removido", "texto": l})
        elif tag == "insert":
            linhas_adicionadas += (j2 - j1)
            for l in new_lines[j1:j2]:
                blocos.append({"tipo": "adicionado", "texto": l})

    is_identical = (norm_ant == norm_nov)
    modificado = 0 if is_identical else 1

    if is_identical:
        resumo = "Letra idêntica"
    else:
        partes_resumo = []
        if linhas_alteradas:
            partes_resumo.append(f"{linhas_alteradas} linha(s) modificada(s)")
        if linhas_adicionadas:
            partes_resumo.append(f"{linhas_adicionadas} linha(s) adicionada(s)")
        if linhas_removidas:
            partes_resumo.append(f"{linhas_removidas} linha(s) removida(s)")
        resumo = ", ".join(partes_resumo) if partes_resumo else "Alterações pontuais na ortografia/pontuação"

    diff_json_obj = {
        "similaridade_pct": similaridade_pct,
        "estatisticas": {
            "linhas_adicionadas": linhas_adicionadas,
            "linhas_removidas": linhas_removidas,
            "linhas_alteradas": linhas_alteradas,
            "linhas_iguais": linhas_iguais
        },
        "blocos": blocos
    }

    return bool(modificado), similaridade_pct, diff_texto, json.dumps(diff_json_obj, ensure_ascii=False), resumo


def cruzar_hinarios(
    new_hymns: Dict[str, Dict[str, Any]],
    old_hymns: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Executa o cruzamento completo em múltiplos estágios e calcula todas as métricas e diffs.
    """
    logger.info("Iniciando cruzamento inteligente dos hinos...")

    # Índices invertidos
    old_by_orig: Dict[str, str] = {d["norm_original"]: num for num, d in old_hymns.items() if d["norm_original"]}
    old_by_tit: Dict[str, str] = {d["norm_titulo"]: num for num, d in old_hymns.items() if d["norm_titulo"]}
    old_by_firstline: Dict[str, str] = {d["first_line"]: num for num, d in old_hymns.items() if d["first_line"]}

    matched_new: Dict[str, Tuple[str, str]] = {}  # num_novo -> (num_antigo, metodo)
    used_old: Set[str] = set()

    # Pass 1: Título Original em Inglês
    for num_n, dn in new_hymns.items():
        if dn["norm_original"] and dn["norm_original"] in old_by_orig:
            num_a = old_by_orig[dn["norm_original"]]
            if num_a not in used_old:
                # Verificação de segurança na letra
                sim = difflib.SequenceMatcher(None, norm_clean(dn["letra"]), norm_clean(old_hymns[num_a]["letra"])).ratio()
                if sim > 0.30:
                    matched_new[num_n] = (num_a, "original_title")
                    used_old.add(num_a)

    # Pass 2: Título em Português Idêntico / Normalizado
    for num_n, dn in new_hymns.items():
        if num_n in matched_new:
            continue
        if dn["norm_titulo"] and dn["norm_titulo"] in old_by_tit:
            num_a = old_by_tit[dn["norm_titulo"]]
            if num_a not in used_old:
                sim = difflib.SequenceMatcher(None, norm_clean(dn["letra"]), norm_clean(old_hymns[num_a]["letra"])).ratio()
                if sim > 0.35:
                    matched_new[num_n] = (num_a, "titulo_pt")
                    used_old.add(num_a)

    # Pass 3: Primeira Linha da Letra
    for num_n, dn in new_hymns.items():
        if num_n in matched_new:
            continue
        if dn["first_line"] and dn["first_line"] in old_by_firstline:
            num_a = old_by_firstline[dn["first_line"]]
            if num_a not in used_old:
                sim = difflib.SequenceMatcher(None, norm_clean(dn["letra"]), norm_clean(old_hymns[num_a]["letra"])).ratio()
                if sim > 0.35:
                    matched_new[num_n] = (num_a, "primeira_linha")
                    used_old.add(num_a)

    # Pass 4: Fuzzy Match com alta similaridade de título/letra
    for num_n, dn in new_hymns.items():
        if num_n in matched_new:
            continue
        best_cand: Optional[Tuple[str, str]] = None
        best_sim = 0.0

        for num_a, da in old_hymns.items():
            if num_a in used_old:
                continue

            t_ratio = difflib.SequenceMatcher(None, dn["norm_titulo"], da["norm_titulo"]).quick_ratio()
            fl_ratio = difflib.SequenceMatcher(None, dn["first_line"], da["first_line"]).quick_ratio() if dn["first_line"] and da["first_line"] else 0.0

            if t_ratio > 0.80 or fl_ratio > 0.80:
                l_sim = difflib.SequenceMatcher(None, norm_clean(dn["letra"]), norm_clean(da["letra"])).ratio()
                if l_sim > 0.50 and l_sim > best_sim:
                    best_sim = l_sim
                    best_cand = (num_a, f"fuzzy (sim={l_sim:.2f})")

        if best_cand:
            matched_new[num_n] = best_cand
            used_old.add(best_cand[0])

    logger.info(f"Total de pares cruzados: {len(matched_new)}.")

    # Monta a lista final de registros comparativos
    registros: List[Dict[str, Any]] = []

    # 1. Processa todos os hinos do Hinário Novo (cruzados e inéditos)
    for num_n, dn in sorted(new_hymns.items(), key=lambda x: (int(x[0]) if x[0].isdigit() else 9999, x[0])):
        if num_n in matched_new:
            num_a, metodo = matched_new[num_n]
            da = old_hymns[num_a]

            modificado, sim_pct, diff_txt, diff_j, resumo = gerar_diffs_e_metricas(
                letra_antiga=da["letra"],
                letra_nova=dn["letra"],
                titulo_antigo=da["titulo"],
                titulo_novo=dn["titulo"],
                num_antigo=num_a,
                num_novo=num_n
            )

            status = "IDENTICO" if not modificado else "MODIFICADO"

            registros.append({
                "numero_novo": num_n,
                "numero_antigo": num_a,
                "titulo_novo": dn["titulo"],
                "titulo_antigo": da["titulo"],
                "categoria_nova": dn["categoria"],
                "categoria_antiga": da["categoria"],
                "status_comparacao": status,
                "modificado": int(modificado),
                "similaridade_pct": sim_pct,
                "diff_texto": diff_txt,
                "diff_json": diff_j,
                "resumo_alteracoes": resumo,
                "metodo_cruzamento": metodo
            })
        else:
            # Hino Inédito no Hinário Novo
            registros.append({
                "numero_novo": num_n,
                "numero_antigo": None,
                "titulo_novo": dn["titulo"],
                "titulo_antigo": None,
                "categoria_nova": dn["categoria"],
                "categoria_antiga": None,
                "status_comparacao": "NOVO_INEDITO",
                "modificado": 1,
                "similaridade_pct": 0.0,
                "diff_texto": f"+ [Hino Inédito no Novo Hinário]: {dn['titulo']}\n\n" + dn["letra"],
                "diff_json": json.dumps({
                    "similaridade_pct": 0.0,
                    "estatisticas": {"linhas_adicionadas": len(dn["lines"]), "linhas_removidas": 0, "linhas_alteradas": 0, "linhas_iguais": 0},
                    "blocos": [{"tipo": "adicionado", "texto": l} for l in dn["lines"]]
                }, ensure_ascii=False),
                "resumo_alteracoes": "Hino inédito adicionado no novo hinário",
                "metodo_cruzamento": "sem_par"
            })

    # 2. Processa os hinos do Hinário Antigo que foram descontinuados
    for num_a, da in sorted(old_hymns.items(), key=lambda x: (int(x[0]) if x[0].isdigit() else 9999, x[0])):
        if num_a not in used_old:
            registros.append({
                "numero_novo": None,
                "numero_antigo": num_a,
                "titulo_novo": None,
                "titulo_antigo": da["titulo"],
                "categoria_nova": None,
                "categoria_antiga": da["categoria"],
                "status_comparacao": "ANTIGO_DESCONTINUADO",
                "modificado": 1,
                "similaridade_pct": 0.0,
                "diff_texto": f"- [Hino Descontinuado do Hinário Antigo]: {da['titulo']}\n\n" + da["letra"],
                "diff_json": json.dumps({
                    "similaridade_pct": 0.0,
                    "estatisticas": {"linhas_adicionadas": 0, "linhas_removidas": len(da["lines"]), "linhas_alteradas": 0, "linhas_iguais": 0},
                    "blocos": [{"tipo": "removido", "texto": l} for l in da["lines"]]
                }, ensure_ascii=False),
                "resumo_alteracoes": "Hino presente no hinário antigo e não incluído no novo",
                "metodo_cruzamento": "sem_par"
            })

    return registros


def criar_esquema_comparativo(conn: sqlite3.Connection):
    """
    Cria a tabela principal, FTS5 e índices para o banco comparativo.
    """
    cur = conn.cursor()

    # Pragmas de performance
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    cur.execute("PRAGMA temp_store = MEMORY;")
    cur.execute("PRAGMA cache_size = -64000;")
    cur.execute("PRAGMA mmap_size = 268435456;")

    cur.executescript("""
    -- 1. Tabela Principal de Comparação
    CREATE TABLE IF NOT EXISTS comparativo_hinos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_novo TEXT,
        numero_antigo TEXT,
        titulo_novo TEXT,
        titulo_antigo TEXT,
        categoria_nova TEXT,
        categoria_antiga TEXT,
        status_comparacao TEXT NOT NULL,
        modificado INTEGER NOT NULL,
        similaridade_pct REAL,
        diff_texto TEXT,
        diff_json TEXT,
        resumo_alteracoes TEXT,
        metodo_cruzamento TEXT
    );

    -- 2. Tabela Virtual FTS5 para Busca Rápida de Diffs e Hinos
    CREATE VIRTUAL TABLE IF NOT EXISTS comparativo_fts USING fts5(
        numero_novo,
        numero_antigo,
        titulo_novo,
        titulo_antigo,
        status_comparacao,
        resumo_alteracoes,
        diff_texto,
        tokenize="unicode61 remove_diacritics 2"
    );

    -- 3. Índices de Alta Velocidade
    CREATE INDEX IF NOT EXISTS idx_comp_numero_novo ON comparativo_hinos(numero_novo);
    CREATE INDEX IF NOT EXISTS idx_comp_numero_antigo ON comparativo_hinos(numero_antigo);
    CREATE INDEX IF NOT EXISTS idx_comp_status ON comparativo_hinos(status_comparacao);
    CREATE INDEX IF NOT EXISTS idx_comp_modificado ON comparativo_hinos(modificado);
    """)

    conn.commit()


def gerar_banco_comparativo(
    base_dir: str = ".",
    db_name: str = "hinario_comparativo.db"
) -> str:
    """
    Pipeline principal para gerar o hinario_comparativo.db.
    """
    logger.info("=" * 70)
    logger.info("GERAÇÃO DO BANCO COMPARATIVO (hinario_comparativo.db)")
    logger.info("=" * 70)

    db_novo_path = os.path.join(base_dir, "basesdedados", "hinario.db") if not os.path.exists(os.path.join(base_dir, "hinario.db")) else os.path.join(base_dir, "hinario.db")
    db_antigo_path = os.path.join(base_dir, "basesdedados", "hinario_antigo.db") if not os.path.exists(os.path.join(base_dir, "hinario_antigo.db")) else os.path.join(base_dir, "hinario_antigo.db")
    hinos_json_dir = os.path.join(base_dir, "hinos_json")
    hymn_detail_path = os.path.join(base_dir, "hinarioAntigo", "xmls", "hymn_detail.xml")
    db_comparativo_path = os.path.join(base_dir, "basesdedados", db_name) if not os.path.isabs(db_name) else db_name

    if not os.path.exists(db_novo_path):
        raise FileNotFoundError(f"Banco do hinário novo não encontrado: {db_novo_path}")
    if not os.path.exists(db_antigo_path):
        raise FileNotFoundError(f"Banco do hinário antigo não encontrado: {db_antigo_path}")

    # Carrega dados
    new_hymns, old_hymns = carregar_dados_hinarios(
        db_novo_path=db_novo_path,
        db_antigo_path=db_antigo_path,
        hinos_json_dir=hinos_json_dir,
        hymn_detail_path=hymn_detail_path
    )

    # Executa cruzamento
    registros = cruzar_hinarios(new_hymns, old_hymns)

    # Recria banco SQLite limpo
    if os.path.exists(db_comparativo_path):
        try:
            os.remove(db_comparativo_path)
            logger.info(f"Banco comparativo existente removido para recriação limpa: {db_comparativo_path}")
        except Exception as e:
            logger.warning(f"Aviso ao remover banco anterior: {e}")

    conn = sqlite3.connect(db_comparativo_path)
    criar_esquema_comparativo(conn)
    cur = conn.cursor()

    logger.info(f"Inserindo {len(registros)} registros no banco comparativo...")

    for r in registros:
        # Inserção na tabela principal
        cur.execute("""
        INSERT INTO comparativo_hinos (
            numero_novo,
            numero_antigo,
            titulo_novo,
            titulo_antigo,
            categoria_nova,
            categoria_antiga,
            status_comparacao,
            modificado,
            similaridade_pct,
            diff_texto,
            diff_json,
            resumo_alteracoes,
            metodo_cruzamento
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            r["numero_novo"],
            r["numero_antigo"],
            r["titulo_novo"],
            r["titulo_antigo"],
            r["categoria_nova"],
            r["categoria_antiga"],
            r["status_comparacao"],
            r["modificado"],
            r["similaridade_pct"],
            r["diff_texto"],
            r["diff_json"],
            r["resumo_alteracoes"],
            r["metodo_cruzamento"]
        ))

        # Inserção na tabela FTS5
        cur.execute("""
        INSERT INTO comparativo_fts (
            numero_novo,
            numero_antigo,
            titulo_novo,
            titulo_antigo,
            status_comparacao,
            resumo_alteracoes,
            diff_texto
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (
            r["numero_novo"] or "",
            r["numero_antigo"] or "",
            r["titulo_novo"] or "",
            r["titulo_antigo"] or "",
            r["status_comparacao"],
            r["resumo_alteracoes"],
            r["diff_texto"]
        ))

    conn.commit()
    conn.close()

    logger.info("=" * 70)
    logger.info(f"BANCO COMPARATIVO GERADO COM SUCESSO: {db_comparativo_path}")
    logger.info("=" * 70)
    return db_comparativo_path


def relatorio_validacao(db_path: str):
    """
    Exibe estatísticas completas e amostras dos hinos comparados.
    """
    logger.info("RELATÓRIO DE ESTATÍSTICAS E VALIDAÇÃO:")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM comparativo_hinos;")
    total = cur.fetchone()[0]
    logger.info(f"Total de registros comparativos: {total}")

    cur.execute("""
    SELECT status_comparacao, COUNT(*) 
    FROM comparativo_hinos 
    GROUP BY status_comparacao;
    """)
    stats = cur.fetchall()
    for st, cnt in stats:
        logger.info(f"  - {st}: {cnt} hinos")

    cur.execute("""
    SELECT AVG(similaridade_pct) 
    FROM comparativo_hinos 
    WHERE status_comparacao IN ('IDENTICO', 'MODIFICADO');
    """)
    avg_sim = cur.fetchone()[0]
    logger.info(f"Similaridade média dos hinos preservados: {avg_sim:.1f}%\n")

    # Amostras
    logger.info("AMOSTRAS DE REGISTROS:")
    cur.execute("""
    SELECT numero_novo, numero_antigo, titulo_novo, titulo_antigo, status_comparacao, similaridade_pct, resumo_alteracoes
    FROM comparativo_hinos
    WHERE status_comparacao = 'MODIFICADO'
    LIMIT 3;
    """)
    for r in cur.fetchall():
        logger.info(f"  [MODIFICADO] Novo #{r[0]} (\"{r[2]}\") <-> Antigo #{r[1]} (\"{r[3]}\") | Sim: {r[5]}% | {r[6]}")

    cur.execute("""
    SELECT numero_novo, numero_antigo, titulo_novo, titulo_antigo, status_comparacao, similaridade_pct, resumo_alteracoes
    FROM comparativo_hinos
    WHERE status_comparacao = 'IDENTICO'
    LIMIT 2;
    """)
    for r in cur.fetchall():
        logger.info(f"  [IDÊNTICO] Novo #{r[0]} (\"{r[2]}\") <-> Antigo #{r[1]} (\"{r[3]}\") | Sim: {r[5]}% | {r[6]}")

    cur.execute("""
    SELECT numero_novo, titulo_novo, status_comparacao, resumo_alteracoes
    FROM comparativo_hinos
    WHERE status_comparacao = 'NOVO_INEDITO'
    LIMIT 2;
    """)
    for r in cur.fetchall():
        logger.info(f"  [INÉDITO] Novo #{r[0]} (\"{r[1]}\") | {r[3]}")

    cur.execute("""
    SELECT numero_antigo, titulo_antigo, status_comparacao, resumo_alteracoes
    FROM comparativo_hinos
    WHERE status_comparacao = 'ANTIGO_DESCONTINUADO'
    LIMIT 2;
    """)
    for r in cur.fetchall():
        logger.info(f"  [DESCONTINUADO] Antigo #{r[0]} (\"{r[1]}\") | {r[3]}")

    # Exemplo de diff textual
    logger.info("\nEXEMPLO DE DIFF TEXTUAL (Hino Novo #1 vs Hino Antigo #18):")
    cur.execute("""
    SELECT diff_texto 
    FROM comparativo_hinos 
    WHERE numero_novo = '1' AND numero_antigo = '18';
    """)
    row_diff = cur.fetchone()
    if row_diff and row_diff[0]:
        print(row_diff[0])

    conn.close()


if __name__ == "__main__":
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    db_gerado = gerar_banco_comparativo(base_dir=root_dir, db_name="hinario_comparativo.db")
    relatorio_validacao(db_gerado)

