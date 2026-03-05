"""
Research Agent - Paso 1
Descubre nuevas herramientas científicas usando conocimiento LLM + Tavily (opcional)
"""
import logging
import json
from typing import List, Dict, Optional
from flask import current_app
from app.services.llm_service import get_llm_service, log_llm_call

logger = logging.getLogger(__name__)

# 16 categorías de monitoreo (A-P)
CATEGORIES = [
    'AI tools for research',
    'bibliometrics and citation',
    'collaboration platforms',
    'data analysis and statistics',
    'experiment design',
    'field-specific tools',
    'grant writing',
    'knowledge management',
    'literature review and synthesis',
    'note-taking and organization',
    'open science and reproducibility',
    'project management',
    'qualitative analysis',
    'reference management',
    'surveys and questionnaires',
    'visualization and graphics',
]


def _tavily_search(categories: List[str], existing_slugs: List[str]) -> List[Dict]:
    """
    Búsqueda web via Tavily (opcional, solo si hay API key real).
    """
    tavily_key = current_app.config.get('TAVILY_API_KEY', '')
    if not tavily_key or tavily_key.startswith('tvly-your') or len(tavily_key) < 20:
        logger.info("Tavily API key not configured or is placeholder — skipping web search")
        return []

    try:
        from tavily import TavilyClient
        tavily = TavilyClient(api_key=tavily_key)
    except ImportError:
        logger.warning("tavily-python not installed — skipping web search")
        return []

    search_results = []
    for category in categories:
        try:
            results = tavily.search(
                query=f"new scientific research tool {category} 2025 2026",
                search_depth="advanced",
                max_results=3,
                include_answer=False
            )
            for result in results.get('results', []):
                search_results.append({
                    'category': category,
                    'title': result.get('title'),
                    'url': result.get('url'),
                    'content': result.get('content'),
                    'score': result.get('score', 0),
                })
            logger.info(f"Tavily '{category}': {len(results.get('results', []))} results")
        except Exception as e:
            logger.error(f"Tavily search failed for '{category}': {e}")
            continue

    return search_results


def _llm_discover_tools(
    existing_tools_summary: str,
    category_gaps: List[str],
    tavily_context: Optional[str] = None
) -> List[Dict]:
    """
    Usa el LLM para descubrir herramientas científicas nuevas/emergentes
    basándose en su conocimiento y, opcionalmente, resultados de búsqueda web.
    """
    llm = get_llm_service()

    web_context = ""
    if tavily_context:
        web_context = f"""

RESULTADOS DE BÚSQUEDA WEB RECIENTES:
{tavily_context}

Usa estos resultados para complementar tu conocimiento. Prioriza herramientas
mencionadas en fuentes recientes."""

    system_prompt = f"""Eres un investigador experto en herramientas digitales para investigación científica y académica.

Tu misión: Identificar herramientas científicas REALES que NO estén en el inventario actual.

INVENTARIO ACTUAL (herramientas que ya tenemos — NO las repitas):
{existing_tools_summary}

CATEGORÍAS CON MENOS COBERTURA (priorizar):
{', '.join(category_gaps) if category_gaps else 'Todas las categorías tienen cobertura similar'}
{web_context}

INSTRUCCIONES:
1. Identifica 5-8 herramientas REALES y VERIFICABLES que falten en nuestro inventario
2. Prioriza herramientas:
   - Lanzadas o actualizadas significativamente en 2024-2026
   - Con impacto real en investigación académica
   - De diferentes categorías (diversidad)
   - Tanto de ciencias duras como sociales/humanidades
3. CADA herramienta debe ser un software/plataforma/servicio REAL con URL verificable
4. NO inventes herramientas — solo menciona las que realmente existen

Responde SOLO con un JSON array válido (sin texto adicional):
[
  {{
    "name": "Nombre Exacto de la Herramienta",
    "url": "https://url-oficial.com",
    "summary": "Descripción precisa en español (2-3 oraciones). Qué hace, para qué sirve, qué la diferencia.",
    "category": "una de las 16 categorías",
    "field": "campo disciplinar principal (ej: multidisciplinar, ciencias sociales, biomedicina, etc.)",
    "source_url": "https://fuente-donde-se-puede-verificar.com",
    "pricing": "free|freemium|paid|open-source (si es freemium o paid, especifica brevemente planes y precios)",
    "platform": "web|desktop|mobile|API|extension (puede ser combinación: web, API)",
    "features": ["funcionalidad clave 1 en español", "funcionalidad clave 2", "funcionalidad clave 3", "funcionalidad clave 4", "funcionalidad clave 5"]
  }}
]

IMPORTANTE:
- El campo 'pricing' es OBLIGATORIO. Investiga el modelo de precios real de cada herramienta.
  Ejemplos: "open-source", "free", "freemium: plan gratuito limitado, Pro $10/mes", "paid: desde $29/mes"
- El campo 'platform' es OBLIGATORIO. Indica las plataformas reales.
  Ejemplos: "web", "desktop (Windows, Mac)", "web, API", "extensión de navegador"
- El campo 'features' es OBLIGATORIO. Lista 3-5 funcionalidades clave REALES y ESPECÍFICAS.
  No uses descripciones genéricas. Sé concreto sobre qué hace exactamente la herramienta."""

    try:
        response = llm.research_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    "Identifica herramientas científicas reales que no estén "
                    "en nuestro inventario. Enfócate en herramientas emergentes, "
                    "con buena tracción, y que cubran las categorías menos representadas. "
                    "Incluye herramientas tanto para ciencias duras como para ciencias sociales."
                )}
            ],
            temperature=0.4
        )

        log_llm_call('research_discover', response, {'mode': 'llm_knowledge'})

        result_text = response.choices[0].message.content

        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0]
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0]

        findings = json.loads(result_text.strip())

        if not isinstance(findings, list):
            logger.error("LLM returned non-list response")
            return []

        logger.info(f"LLM discovered {len(findings)} potential new tools")
        return findings

    except Exception as e:
        logger.error(f"LLM discovery failed: {e}")
        return []


def _analyze_category_gaps(existing_tools_summary: str) -> List[str]:
    """Identifica categorías con poca cobertura en el inventario actual."""
    category_counts = {}
    lower_summary = existing_tools_summary.lower()

    for cat in CATEGORIES:
        keywords = cat.lower().split()
        count = sum(1 for kw in keywords if kw in lower_summary)
        category_counts[cat] = count

    sorted_cats = sorted(category_counts.items(), key=lambda x: x[1])
    gaps = [cat for cat, _ in sorted_cats[:5]]

    logger.info(f"Category gaps identified: {gaps}")
    return gaps


def research_daily_tools(existing_slugs: List[str]) -> List[Dict]:
    """
    Paso 1: Descubre herramientas nuevas usando LLM + Tavily (opcional)
    
    Args:
        existing_slugs: Lista de slugs de herramientas ya existentes
        
    Returns:
        Lista de hallazgos estructurados con fuentes
    """
    logger.info("=" * 50)
    logger.info("Starting Research Agent (LLM + optional Tavily)")
    logger.info("=" * 50)

    # 1. Construir resumen del inventario actual
    from app.models import Tool
    existing_tools = Tool.query.filter_by(status='active').all()

    existing_summary = "\n".join([
        f"- {t.slug}: {t.name} | {t.category or 'sin categoría'} | {(t.summary or '')[:80]}"
        for t in existing_tools
    ])

    logger.info(f"Current inventory: {len(existing_tools)} tools")

    # 2. Identificar categorías con brechas
    category_gaps = _analyze_category_gaps(existing_summary)

    # 3. Búsqueda web opcional (Tavily)
    tavily_results = _tavily_search(category_gaps, existing_slugs)
    tavily_context = None
    if tavily_results:
        tavily_context = "\n\n".join([
            f"**{r['category']}**\n"
            f"Title: {r['title']}\n"
            f"URL: {r['url']}\n"
            f"Content: {r['content'][:400]}"
            for r in tavily_results[:20]
        ])
        logger.info(f"Tavily provided {len(tavily_results)} results as context")

    # 4. Descubrimiento principal via LLM
    findings = _llm_discover_tools(existing_summary, category_gaps, tavily_context)

    # 5. Filtrar herramientas que ya existen
    existing_names_lower = {t.name.lower() for t in existing_tools}
    existing_slugs_set = set(existing_slugs)

    filtered = []
    for f in findings:
        slug_candidate = f.get('name', '').lower().replace(' ', '-').replace('.', '-')
        name_lower = f.get('name', '').lower()

        if slug_candidate in existing_slugs_set:
            logger.info(f"Filtered out (slug exists): {f['name']}")
            continue
        if name_lower in existing_names_lower:
            logger.info(f"Filtered out (name exists): {f['name']}")
            continue

        filtered.append(f)

    logger.info(f"Research Agent: {len(filtered)} new tools after filtering (from {len(findings)} candidates)")
    return filtered
