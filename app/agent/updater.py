"""
Tool Updater Agent - Paso 2B
Revisa herramientas existentes y actualiza descripciones, funcionalidades nuevas,
cambios de pricing, nuevas capacidades, etc.
"""
import logging
import json
from typing import List, Dict
from flask import current_app
from app.services.llm_service import get_llm_service, log_llm_call

logger = logging.getLogger(__name__)


def refresh_existing_tools(tools_to_refresh: List) -> List[Dict]:
    """
    Usa el LLM (+ Tavily opcional) para detectar novedades en herramientas
    que ya están en el inventario.
    
    Args:
        tools_to_refresh: Lista de objetos Tool a revisar
        
    Returns:
        Lista de actualizaciones detectadas:
        [
          {
            "tool_slug": "slack",
            "tool_name": "Slack",
            "changes": [
              {
                "field": "summary",
                "new_value": "...",
                "reason": "Nueva funcionalidad X lanzada en 2025"
              }
            ]
          }
        ]
    """
    if not tools_to_refresh:
        return []

    logger.info(f"Starting Tool Updater for {len(tools_to_refresh)} tools")

    # Preparar contexto de las herramientas a revisar
    tools_detail = "\n\n".join([
        f"SLUG: {t.slug}\n"
        f"NOMBRE: {t.name}\n"
        f"URL: {t.url or 'N/A'}\n"
        f"CATEGORÍA: {t.category or 'N/A'}\n"
        f"CAMPO: {t.field or 'N/A'}\n"
        f"PRICING: {t.pricing or 'N/A'}\n"
        f"PLATAFORMA: {t.platform or 'N/A'}\n"
        f"DESCRIPCIÓN ACTUAL: {t.summary or 'Sin descripción'}\n"
        f"ÚLTIMA ACTUALIZACIÓN: {t.last_updated.strftime('%Y-%m-%d') if t.last_updated else 'N/A'}"
        for t in tools_to_refresh
    ])

    # Opcionalmente buscar con Tavily
    web_context = _tavily_refresh_search(tools_to_refresh)

    llm = get_llm_service()

    web_section = ""
    if web_context:
        web_section = f"""

INFORMACIÓN WEB RECIENTE SOBRE ESTAS HERRAMIENTAS:
{web_context}

Usa esta información para complementar tu conocimiento sobre novedades."""

    system_prompt = f"""Eres un analista experto en herramientas de investigación científica.

Tu tarea: Revisar las siguientes herramientas y detectar NOVEDADES, ACTUALIZACIONES o
MEJORAS que hayan ocurrido recientemente (2024-2026).

HERRAMIENTAS A REVISAR:
{tools_detail}
{web_section}

Para CADA herramienta, evalúa:
1. ¿Ha habido actualizaciones significativas (nuevas funciones, cambios de versión)?
2. ¿Ha cambiado su modelo de pricing?
3. ¿Su descripción actual es completa y precisa?
4. ¿Tiene nuevas capacidades de IA, integraciones, o mejoras importantes?
5. ¿Ha cambiado su plataforma (ej: ahora también tiene app móvil)?

REGLAS:
- Solo reporta cambios REALES y verificables
- Si la descripción actual es adecuada, NO la cambies
- Prioriza cambios sustanciales, no cosméticos
- Mejora las descripciones que estén vacías, vagas o incompletas
- Las descripciones mejoradas deben ser en español, profesionales, 2-3 oraciones

Responde SOLO con un JSON array válido:
[
  {{
    "tool_slug": "slug-exacto",
    "tool_name": "Nombre",
    "changes": [
      {{
        "field": "summary|pricing|platform|url|category|description_html",
        "new_value": "nuevo valor",
        "reason": "Razón del cambio en español"
      }}
    ]
  }}
]

Si una herramienta NO tiene cambios que reportar, NO la incluyas en el array.
Si ninguna herramienta tiene cambios, responde con array vacío []."""

    try:
        response = llm.research_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    "Revisa cada herramienta y reporta novedades, "
                    "actualizaciones de funcionalidades, cambios de pricing, "
                    "y mejora las descripciones que estén incompletas o vacías."
                )}
            ],
            temperature=0.3
        )

        log_llm_call('tool_updater', response, {'tools_checked': len(tools_to_refresh)})

        result_text = response.choices[0].message.content

        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0]
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0]

        updates = json.loads(result_text.strip())

        if not isinstance(updates, list):
            logger.error("Updater returned non-list response")
            return []

        # Contar cambios totales
        total_changes = sum(len(u.get('changes', [])) for u in updates)
        logger.info(f"Tool Updater: {len(updates)} tools with {total_changes} total changes")

        return updates

    except Exception as e:
        logger.error(f"Tool Updater failed: {e}")
        return []


def _tavily_refresh_search(tools: List) -> str:
    """
    Busca novedades web sobre herramientas específicas (opcional).
    """
    tavily_key = current_app.config.get('TAVILY_API_KEY', '')
    if not tavily_key or tavily_key.startswith('tvly-your') or len(tavily_key) < 20:
        return ""

    try:
        from tavily import TavilyClient
        tavily = TavilyClient(api_key=tavily_key)
    except ImportError:
        return ""

    # Buscar novedades solo para un subconjunto (máx 5 para no gastar mucho)
    results_text = []
    for tool in tools[:5]:
        try:
            results = tavily.search(
                query=f"{tool.name} scientific research tool update new features 2025 2026",
                search_depth="basic",
                max_results=2,
                include_answer=False
            )
            for r in results.get('results', []):
                results_text.append(
                    f"[{tool.name}] {r.get('title', '')}: {r.get('content', '')[:300]}"
                )
        except Exception as e:
            logger.warning(f"Tavily refresh search failed for {tool.name}: {e}")
            continue

    return "\n\n".join(results_text) if results_text else ""


def apply_tool_updates(updates: List[Dict]) -> Dict:
    """
    Aplica las actualizaciones detectadas a las herramientas en la BD.
    
    Args:
        updates: Lista de actualizaciones del refresh_existing_tools
        
    Returns:
        Dict con estadísticas: {'updated': int, 'skipped': int, 'details': [...]}
    """
    from app.models import Tool, Update
    from app import db
    from datetime import datetime

    stats = {'updated': 0, 'skipped': 0, 'details': []}
    
    # Campos que se pueden actualizar
    ALLOWED_FIELDS = {'summary', 'pricing', 'platform', 'url', 'category',
                      'description_html', 'field', 'tags', 'developer'}

    for tool_update in updates:
        slug = tool_update.get('tool_slug', '')
        tool = Tool.query.filter_by(slug=slug).first()

        if not tool:
            logger.warning(f"Tool '{slug}' not found — skipping update")
            stats['skipped'] += 1
            continue

        changes = tool_update.get('changes', [])
        tool_changed = False

        for change in changes:
            field = change.get('field', '')
            new_value = change.get('new_value', '')
            reason = change.get('reason', '')

            if field not in ALLOWED_FIELDS:
                logger.warning(f"Field '{field}' not allowed for update — skipping")
                continue

            old_value = str(getattr(tool, field, '') or '')

            # Skip if values are the same
            if old_value.strip() == new_value.strip():
                continue

            setattr(tool, field, new_value)
            tool_changed = True

            stats['details'].append({
                'tool': tool.name,
                'field': field,
                'reason': reason
            })

            logger.info(f"Updated {tool.name}.{field}: {reason}")

        if tool_changed:
            tool.last_updated = datetime.utcnow()
            stats['updated'] += 1

    if stats['updated'] > 0:
        db.session.commit()

    logger.info(f"Tool updates applied: {stats['updated']} updated, {stats['skipped']} skipped")
    return stats
