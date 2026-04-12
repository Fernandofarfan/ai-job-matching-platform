"""
market_analyzer.py — Análisis del Mercado Salarial
Extrae y analiza datos salariales de los CSVs scrapeados y los enriquece con IA.
"""
import os
import json
import logging
import re
from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Patrones regex para extraer salarios de texto libre
_SALARY_PATTERNS = [
    # USD: $2,000 - $4,000 / $2000 - $4000
    r'\$\s*(\d{1,3}(?:[.,]\d{3})*)\s*[-–]\s*\$?\s*(\d{1,3}(?:[.,]\d{3})*)',
    # USD: USD 2000-4000
    r'(?:USD|US\$)\s*(\d{1,3}(?:[.,]\d{3})*)\s*[-–]\s*(?:USD|US\$)?\s*(\d{1,3}(?:[.,]\d{3})*)',
    # ARS: $200,000 - $350,000
    r'\$\s*(\d{1,3}(?:[.,]\d{3}){2,})\s*[-–]\s*\$?\s*(\d{1,3}(?:[.,]\d{3}){2,})',
    # Número solo: 3000 a 5000
    r'(\d{3,6})\s*(?:a|al|to|-)\s*(\d{3,6})',
]

_CURRENCY_PATTERNS = {
    "USD": [r'U\$S', r'USD', r'US\$', r'dólares', r'dolares'],
    "ARS": [r'ARS', r'\$', r'pesos'],
    "EUR": [r'EUR', r'euros', r'€'],
}


def extract_salary_from_text(text: str) -> dict:
    """Extrae rango salarial de texto libre usando regex."""
    if not text or len(str(text)) < 3:
        return {"min": None, "max": None, "currency": None, "raw": None, "confidence": "none"}

    text = str(text)

    # Detectar moneda
    detected_currency = None
    for currency, patterns in _CURRENCY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                detected_currency = currency
                break
        if detected_currency:
            break

    # Extraer rango
    for pattern in _SALARY_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                raw_min = match.group(1).replace(",", "").replace(".", "")
                raw_max = match.group(2).replace(",", "").replace(".", "")
                min_val = float(raw_min)
                max_val = float(raw_max)

                if min_val > max_val:
                    min_val, max_val = max_val, min_val

                # Inferir moneda por magnitud si no se detectó
                if not detected_currency:
                    if min_val < 20000:
                        detected_currency = "USD"
                    else:
                        detected_currency = "ARS"

                return {
                    "min": min_val,
                    "max": max_val,
                    "avg": (min_val + max_val) / 2,
                    "currency": detected_currency,
                    "raw": match.group(0),
                    "confidence": "high"
                }
            except (ValueError, IndexError):
                continue

    return {"min": None, "max": None, "currency": detected_currency, "raw": None, "confidence": "none"}


def analyze_salary_distribution(jobs_df: pd.DataFrame,
                                 salary_col: str = "Salary") -> dict:
    """
    Analiza la distribución salarial de un DataFrame de trabajos.
    Retorna estadísticas y datos para graficar.
    """
    if salary_col not in jobs_df.columns:
        return {"error": f"Columna '{salary_col}' no encontrada"}

    salaries = []
    currencies = []

    for val in jobs_df[salary_col].dropna():
        extracted = extract_salary_from_text(str(val))
        if extracted["min"] and extracted["max"]:
            salaries.append({
                "min": extracted["min"],
                "max": extracted["max"],
                "avg": extracted["avg"],
                "currency": extracted["currency"],
            })
            if extracted["currency"]:
                currencies.append(extracted["currency"])

    if not salaries:
        return {
            "total_with_salary": 0,
            "total_jobs": len(jobs_df),
            "coverage": 0,
            "message": "No se encontraron datos salariales en el CSV"
        }

    avgs = [s["avg"] for s in salaries]
    usd_salaries = [s for s in salaries if s["currency"] == "USD"]
    ars_salaries = [s for s in salaries if s["currency"] == "ARS"]

    result = {
        "total_with_salary": len(salaries),
        "total_jobs": len(jobs_df),
        "coverage": round(len(salaries) / len(jobs_df) * 100, 1),
        "currency_breakdown": {
            "USD": len(usd_salaries),
            "ARS": len(ars_salaries),
            "other": len(salaries) - len(usd_salaries) - len(ars_salaries),
        },
        "stats": {
            "mean": round(float(np.mean(avgs)), 2),
            "median": round(float(np.median(avgs)), 2),
            "min": round(float(np.min(avgs)), 2),
            "max": round(float(np.max(avgs)), 2),
            "std": round(float(np.std(avgs)), 2),
            "p25": round(float(np.percentile(avgs, 25)), 2),
            "p75": round(float(np.percentile(avgs, 75)), 2),
        },
        "usd_stats": None,
        "ars_stats": None,
        "histogram_data": _create_histogram_data(avgs),
        "all_salaries": salaries[:100],  # Cap para JSON response
    }

    if usd_salaries:
        usd_avgs = [s["avg"] for s in usd_salaries]
        result["usd_stats"] = {
            "count": len(usd_avgs),
            "mean": round(float(np.mean(usd_avgs)), 2),
            "median": round(float(np.median(usd_avgs)), 2),
            "range": [round(float(np.min(usd_avgs)), 2), round(float(np.max(usd_avgs)), 2)],
        }

    if ars_salaries:
        ars_avgs = [s["avg"] for s in ars_salaries]
        result["ars_stats"] = {
            "count": len(ars_avgs),
            "mean": round(float(np.mean(ars_avgs)), 2),
            "median": round(float(np.median(ars_avgs)), 2),
            "range": [round(float(np.min(ars_avgs)), 2), round(float(np.max(ars_avgs)), 2)],
        }

    return result


def _create_histogram_data(values: list, bins: int = 10) -> dict:
    """Crea datos de histograma para Chart.js."""
    if not values:
        return {"labels": [], "counts": []}
    arr = np.array(values)
    counts, bin_edges = np.histogram(arr, bins=bins)
    labels = [f"${int(bin_edges[i]):,}-${int(bin_edges[i+1]):,}" for i in range(len(bin_edges)-1)]
    return {
        "labels": labels,
        "counts": counts.tolist(),
    }


def get_salary_by_company(jobs_df: pd.DataFrame,
                           title_col: str = "Title",
                           company_col: str = "Company",
                           salary_col: str = "Salary") -> list:
    """Retorna ranking de empresas por salario promedio."""
    results = []

    for col in [title_col, company_col, salary_col]:
        if col not in jobs_df.columns:
            return []

    company_data = {}
    for _, row in jobs_df.iterrows():
        company = str(row.get(company_col, ""))
        if not company or company == "nan":
            continue
        salary_data = extract_salary_from_text(str(row.get(salary_col, "")))
        if salary_data["avg"]:
            if company not in company_data:
                company_data[company] = []
            company_data[company].append(salary_data["avg"])

    for company, salaries in company_data.items():
        if len(salaries) >= 1:
            results.append({
                "company": company,
                "avg_salary": round(float(np.mean(salaries)), 2),
                "min_salary": round(float(np.min(salaries)), 2),
                "max_salary": round(float(np.max(salaries)), 2),
                "job_count": len(salaries),
            })

    return sorted(results, key=lambda x: x["avg_salary"], reverse=True)[:20]


def enrich_csv_with_salary_data(csv_path: str) -> str:
    """
    Lee un CSV de trabajos, extrae datos salariales de la columna Salary/Salario
    y agrega columnas normalizadas al CSV.
    """
    try:
        df = pd.read_csv(csv_path, encoding="latin-1")
        salary_col = next((c for c in ["Salary", "Salario", "salary"] if c in df.columns), None)

        if not salary_col:
            logger.warning(f"No salary column found in {csv_path}")
            return csv_path

        extracted = df[salary_col].apply(lambda x: extract_salary_from_text(str(x)))
        df["salary_min"] = extracted.apply(lambda x: x.get("min"))
        df["salary_max"] = extracted.apply(lambda x: x.get("max"))
        df["salary_avg"] = extracted.apply(lambda x: x.get("avg"))
        df["salary_currency"] = extracted.apply(lambda x: x.get("currency"))

        output = csv_path.replace(".csv", "_salary_enriched.csv")
        df.to_csv(output, index=False)
        return output

    except Exception as e:
        logger.error(f"Error enriching CSV with salary data: {e}")
        return csv_path
