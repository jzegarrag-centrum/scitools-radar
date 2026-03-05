"""
Refresh Pipeline - Agentes de actualización de calidad de contenido

Pipeline de tres agentes:
  1. Quality Reviewer  — evalúa herramientas y genera score de calidad (0-100)
  2. Research Agent    — reutiliza researcher.py adaptado para una herramienta específica
  3. Content Writer    — redacta contenido mejorado en español profesional

Orquestación principal: run_refresh_pipeline()
"""
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from flask import current_app

from app.services.llm_service import get_llm_service, log_llm_call

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Agente 1: Quality Reviewer
# ──────────────────────────────────────────────────────────────

def review_tool_quality(tool) -> Dict:
    """
    Evalúa la calidad del contenido de una herramienta y devuelve un score (0-100)
    junto con una lista de mejoras necesarias.

    Returns:
        {
          "score": int,
          "needs_update": bool,
          "issues": ["descripción corta", ...],
          "priority": "high|medium|low"
        }
    """
    issues = []
    score = 100

    # Evaluación heurística (rápida, sin LLM)
    summary = tool.summary or ''
    if len(summary) < 100:
        issues.append('Descripción muy corta (< 100 caracteres)')
        score -= 30
    elif len(summary) < 150:
        issues.append('Descripción puede ser más detallada (< 150 caracteres)')
        score -= 10

    if not tool.pricing:
        issues.append('Falta información de pricing')
        score -= 10

    if not tool.platform:
        issues.append('Falta información de plataforma')
        score -= 5

    if not tool.features:
        issues.append('Falta lista de funcionalidades/features')
        score -= 15

    if not tool.editorial:
        issues.append('Falta sección "Novedades" (editorial)')
        score -= 15

    if tool.last_updated:
        days_old = (datetime.utcnow() - tool.last_updated).days
        if days_old > 180:
            issues.append(f'Contenido desactualizado ({days_old} días sin actualización)')
            score -= 20
    else:
        issues.append('Sin fecha de actualización registrada')
        score -= 10

    if not tool.logo_url:
        issues.append('Falta imagen/logo de la herramienta')
        score -= 10

    score = max(0, score)
    needs_update = score < 70 or bool(issues)

    if score < 40:
        priority = 'high'
    elif score < 70:
        priority = 'medium'
    else:
        priority = 'low'

    return {
        'score': score,
        'needs_update': needs_update,
        'issues': issues,
        'priority': priority,
    }


def scan_all_tools(
    category_filter: Optional[str] = None,
    min_days_old: Optional[int] = None,
    only_empty_fields: bool = False,
    limit: Optional[int] = None,
) -> List[Dict]:
    """
    Agente 1 completo: escanea todas las herramientas y devuelve lista priorizada.

    Args:
        category_filter:   Filtrar por categoría (None = todas)
        min_days_old:      Solo herramientas no actualizadas en X días
        only_empty_fields: Solo herramientas con campos vacíos críticos
        limit:             Máximo de herramientas a retornar

    Returns:
        Lista ordenada por score ascendente (las de peor calidad primero):
        [{"tool": <Tool>, "review": {...}}, ...]
    """
    from app.models import Tool

    query = Tool.query.filter_by(status='active')

    if category_filter:
        query = query.filter(Tool.category.ilike(f'%{category_filter}%'))

    if min_days_old:
        cutoff = datetime.utcnow() - timedelta(days=min_days_old)
        query = query.filter(
            (Tool.last_updated < cutoff) | Tool.last_updated.is_(None)
        )

    if only_empty_fields:
        query = query.filter(
            (Tool.features.is_(None)) |
            (Tool.editorial.is_(None)) |
            (Tool.summary.is_(None))
        )

    tools = query.all()
    logger.info(f'Quality Reviewer: evaluando {len(tools)} herramientas')

    results = []
    for tool in tools:
        review = review_tool_quality(tool)
        if review['needs_update']:
            results.append({'tool': tool, 'review': review})

    # Ordenar: las de peor calidad primero
    results.sort(key=lambda x: x['review']['score'])

    if limit:
        results = results[:limit]

    logger.info(
        f'Quality Reviewer: {len(results)} herramientas necesitan actualización '
        f'(de {len(tools)} evaluadas)'
    )
    return results


# ──────────────────────────────────────────────────────────────
# Agente 2: Research Agent (adaptado para herramienta específica)
# ──────────────────────────────────────────────────────────────

def research_tool_info(tool) -> Dict:
    """
    Busca información actualizada sobre una herramienta específica.
    Usa el LLM y opcionalmente Tavily.

    Returns:
        {
          "features": ["feature1", "feature2", ...],
          "description": "descripción mejorada",
          "pricing": "...",
          "updates": "novedades recientes narrativas",
          "raw_context": "contexto crudo recopilado"
        }
    """
    llm = get_llm_service()

    # Buscar con Tavily si está disponible
    web_context = _tavily_tool_search(tool)

    web_section = ''
    if web_context:
        web_section = f'\n\nINFORMACIÓN WEB RECIENTE:\n{web_context}\n'

    system_prompt = f"""Eres un investigador experto en herramientas digitales para investigación científica.

Tu tarea: Recopilar información actualizada y detallada sobre la siguiente herramienta.
{web_section}
HERRAMIENTA A INVESTIGAR:
- Nombre: {tool.name}
- URL: {tool.url or 'No disponible'}
- Categoría: {tool.category or 'No especificada'}
- Campo: {tool.field or 'No especificado'}
- Descripción actual: {tool.summary or 'Sin descripción'}
- Pricing actual: {tool.pricing or 'Desconocido'}

Recopila y sintetiza:
1. Qué hace la herramienta exactamente (propósito principal)
2. Funcionalidades clave (3-5 features destacados)
3. Modelo de pricing actualizado
4. Novedades o actualizaciones recientes (2024-2026) si las hay
5. Casos de uso en investigación científica

Responde SOLO con JSON válido (sin texto adicional):
{{
  "description": "descripción precisa en español (2-3 oraciones, 150-300 chars)",
  "features": ["feature 1 en español", "feature 2 en español", "feature 3 en español", "feature 4", "feature 5"],
  "pricing": "modelo detallado (ej: 'freemium: plan Free, Pro $10/mes', 'open-source', 'paid: desde $29/mes')",
  "platform": "plataformas reales (ej: 'web', 'web, API', 'desktop (Windows, Mac)')",
  "updates": "párrafo breve sobre novedades recientes (o null si no hay)",
  "use_cases": ["caso de uso 1", "caso de uso 2"]
}}

IMPORTANTE:
- pricing: Sé ESPECÍFICO. No solo digas 'freemium'. Detalla los planes y precios reales.
- features: Lista 3-5 funcionalidades CONCRETAS y REALES, no genéricas.
- platform: Indica las plataformas reales donde se puede usar."""

    try:
        response = llm.research_call(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': (
                    f'Investiga {tool.name} ({tool.url or "sin URL"}) y '
                    f'proporciona información detallada y actualizada.'
                )},
            ],
            temperature=0.3,
        )

        log_llm_call('refresh_research', response, {'tool': tool.slug})

        result_text = response.choices[0].message.content
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0]
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0]

        data = json.loads(result_text.strip())
        data['raw_context'] = web_context or ''
        return data

    except Exception as e:
        logger.error(f'Research failed for {tool.slug}: {e}')
        return {
            'description': tool.summary or '',
            'features': [],
            'pricing': tool.pricing or '',
            'updates': None,
            'use_cases': [],
            'raw_context': '',
        }


def _tavily_tool_search(tool) -> str:
    """Búsqueda Tavily opcional para una herramienta específica."""
    tavily_key = current_app.config.get('TAVILY_API_KEY', '')
    if not tavily_key or tavily_key.startswith('tvly-your') or len(tavily_key) < 20:
        return ''

    try:
        from tavily import TavilyClient
        tavily = TavilyClient(api_key=tavily_key)
        results = tavily.search(
            query=f'{tool.name} scientific research tool features update {datetime.utcnow().year} {datetime.utcnow().year + 1}',
            search_depth='basic',
            max_results=3,
            include_answer=False,
        )
        snippets = [
            f"{r.get('title', '')}: {r.get('content', '')[:400]}"
            for r in results.get('results', [])
        ]
        return '\n\n'.join(snippets)
    except Exception as e:
        logger.warning(f'Tavily search failed for {tool.name}: {e}')
        return ''


# ──────────────────────────────────────────────────────────────
# Agente 3: Content Writer
# ──────────────────────────────────────────────────────────────

def write_improved_content(tool, research_data: Dict) -> Dict:
    """
    Genera contenido mejorado en español profesional a partir de los datos
    del Research Agent y la entrada existente.

    Returns:
        {
          "description": "...",
          "features": ["...", ...],
          "editorial": "párrafo narrativo de Novedades",
          "pricing": "..."
        }
    """
    llm = get_llm_service()

    features_raw = research_data.get('features', [])
    features_str = '\n'.join(f'- {f}' for f in features_raw) if features_raw else 'No disponible'

    use_cases = research_data.get('use_cases', [])
    use_cases_str = '\n'.join(f'- {u}' for u in use_cases) if use_cases else 'No disponible'

    system_prompt = f"""Eres un editor de contenido científico-técnico especializado en herramientas de investigación.

Tu tarea: Reescribir y mejorar la información de esta herramienta en español profesional y accesible.

HERRAMIENTA: {tool.name}
URL: {tool.url or 'No disponible'}
Categoría: {tool.category or 'No especificada'}

DATOS RECOPILADOS POR EL INVESTIGADOR:
Descripción sugerida: {research_data.get('description', 'No disponible')}
Funcionalidades:
{features_str}
Casos de uso:
{use_cases_str}
Novedades recientes: {research_data.get('updates') or 'Sin novedades recientes documentadas'}
Pricing: {research_data.get('pricing', 'Desconocido')}
Platform: {research_data.get('platform', tool.platform or 'Desconocido')}

ENTRADA ACTUAL EN LA BASE DE DATOS:
Descripción: {tool.summary or 'Sin descripción'}
Features: {tool.features or 'Sin features'}
Editorial: {tool.editorial or 'Sin editorial'}

INSTRUCCIONES DE ESTILO:
- Español profesional y accesible para investigadores
- Enfocado en beneficios para el usuario, no solo características técnicas
- Evita jerga innecesaria
- Descripción: 150-350 caracteres, clara y directa
- Features: lista de 3-5 items concisos (máx 80 chars cada uno), funcionalidades REALES y ESPECÍFICAS
- Editorial (Novedades): 1-2 párrafos narrativos sobre qué hay de nuevo o por qué es relevante hoy
  Si no hay novedades recientes, escribe sobre el valor actual de la herramienta
- Pricing: Sé ESPECÍFICO con planes y precios reales (ej: "freemium: Free, Pro $10/mes")

Responde SOLO con JSON válido:
{{
  "description": "descripción mejorada...",
  "features": ["funcionalidad 1", "funcionalidad 2", "funcionalidad 3"],
  "editorial": "párrafo narrativo de novedades...",
  "pricing": "modelo de precios detallado",
  "platform": "plataformas (ej: web, API, desktop)"
}}"""

    try:
        response = llm.writer_call(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': (
                    f'Genera contenido mejorado para {tool.name}. '
                    f'Asegúrate de que sea informativo, profesional y útil para investigadores.'
                )},
            ],
            temperature=0.5,
        )

        log_llm_call('refresh_writer', response, {'tool': tool.slug})

        result_text = response.choices[0].message.content
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0]
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0]

        content = json.loads(result_text.strip())
        return content

    except Exception as e:
        logger.error(f'Content Writer failed for {tool.slug}: {e}')
        return {
            'description': research_data.get('description', tool.summary or ''),
            'features': research_data.get('features', []),
            'editorial': research_data.get('updates') or '',
            'pricing': research_data.get('pricing', tool.pricing or ''),
        }


# ──────────────────────────────────────────────────────────────
# Orquestador principal
# ──────────────────────────────────────────────────────────────

def run_refresh_pipeline(
    category_filter: Optional[str] = None,
    min_days_old: Optional[int] = None,
    only_empty_fields: bool = False,
    limit: Optional[int] = None,
    rate_limit_seconds: float = 2.0,
    progress_callback=None,
) -> Dict:
    """
    Ejecuta el pipeline completo de actualización de contenido:
      1. Quality Reviewer escanea herramientas
      2. Para cada herramienta con score bajo:
         a. Research Agent busca info actualizada
         b. Content Writer genera nuevo contenido
         c. Se guarda en BD con auto_updated=True

    Args:
        category_filter:     Filtrar por categoría
        min_days_old:        Solo herramientas con last_updated > X días
        only_empty_fields:   Solo herramientas con campos vacíos
        limit:               Máximo de herramientas a procesar
        rate_limit_seconds:  Pausa entre herramientas (proteger APIs)
        progress_callback:   Función opcional(step, total, current, message)

    Returns:
        {
          "total_scanned": int,
          "total_updated": int,
          "total_errors": int,
          "duration_seconds": float,
          "details": [{"tool": str, "score_before": int, "score_after": int, ...}]
        }
    """
    from app import db
    from app.models import Tool

    started_at = datetime.utcnow()
    stats = {
        'total_scanned': 0,
        'total_updated': 0,
        'total_errors': 0,
        'duration_seconds': 0.0,
        'details': [],
    }

    # Paso 1: Quality Reviewer
    logger.info('=== Refresh Pipeline: Iniciando Quality Reviewer ===')
    if progress_callback:
        progress_callback('scanning', 0, 0, 'Escaneando herramientas con Quality Reviewer...')

    candidates = scan_all_tools(
        category_filter=category_filter,
        min_days_old=min_days_old,
        only_empty_fields=only_empty_fields,
        limit=limit,
    )

    stats['total_scanned'] = len(candidates)
    logger.info(f'Pipeline: {len(candidates)} herramientas candidatas para actualización')

    if not candidates:
        stats['duration_seconds'] = (datetime.utcnow() - started_at).total_seconds()
        return stats

    # Paso 2 + 3: Research + Content Writer para cada herramienta
    for idx, candidate in enumerate(candidates):
        tool = candidate['tool']
        review = candidate['review']

        logger.info(
            f'[{idx + 1}/{len(candidates)}] Procesando: {tool.name} '
            f'(score={review["score"]}, issues={review["issues"]})'
        )

        if progress_callback:
            progress_callback(
                'processing',
                len(candidates),
                idx + 1,
                f'Actualizando: {tool.name} (score actual: {review["score"]})',
            )

        try:
            # Research
            research_data = research_tool_info(tool)

            # Content Writer
            new_content = write_improved_content(tool, research_data)

            # Guardar en BD
            _apply_content_update(tool, new_content)
            db.session.commit()

            # Score re-evaluado (post-update)
            post_review = review_tool_quality(tool)

            detail = {
                'tool_slug': tool.slug,
                'tool_name': tool.name,
                'score_before': review['score'],
                'score_after': post_review['score'],
                'issues_fixed': review['issues'],
                'status': 'updated',
            }
            stats['details'].append(detail)
            stats['total_updated'] += 1

            logger.info(
                f'  ✓ {tool.name}: score {review["score"]} → {post_review["score"]}'
            )

        except Exception as e:
            logger.error(f'  ✗ Error procesando {tool.slug}: {e}', exc_info=True)
            stats['total_errors'] += 1
            stats['details'].append({
                'tool_slug': tool.slug,
                'tool_name': tool.name,
                'score_before': review['score'],
                'score_after': review['score'],
                'status': 'error',
                'error': str(e),
            })
            try:
                db.session.rollback()
            except Exception:
                pass

        # Rate limiting
        if idx < len(candidates) - 1:
            time.sleep(rate_limit_seconds)

    stats['duration_seconds'] = (datetime.utcnow() - started_at).total_seconds()

    logger.info(
        f'=== Refresh Pipeline completado: '
        f'{stats["total_updated"]} actualizadas, '
        f'{stats["total_errors"]} errores, '
        f'{stats["duration_seconds"]:.1f}s ==='
    )

    if progress_callback:
        progress_callback(
            'done',
            len(candidates),
            len(candidates),
            f'Completado: {stats["total_updated"]} actualizadas, {stats["total_errors"]} errores',
        )

    return stats


def _apply_content_update(tool, new_content: Dict) -> None:
    """Aplica el contenido generado al objeto Tool."""
    description = new_content.get('description', '')
    features = new_content.get('features', [])
    editorial = new_content.get('editorial', '')
    pricing = new_content.get('pricing', '')
    platform = new_content.get('platform', '')

    if description and len(description) > len(tool.summary or ''):
        tool.summary = description

    if features:
        tool.features = json.dumps(features, ensure_ascii=False)

    if editorial:
        tool.editorial = editorial

    if pricing and pricing != tool.pricing:
        tool.pricing = pricing

    if platform and platform != tool.platform:
        tool.platform = platform

    tool.auto_updated = True
    tool.quality_score = review_tool_quality(tool)['score']
    tool.last_updated = datetime.utcnow()

    # Auto-fix missing logo using Google Favicon API
    if not tool.logo_url and tool.url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(tool.url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            if domain:
                tool.logo_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
                logger.info(f'Auto-assigned logo for {tool.slug}: {tool.logo_url}')
        except Exception:
            pass
