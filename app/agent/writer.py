"""
Writer Agent - Paso 3
Genera el editorial y estructura JSON completa de la entrada diaria
"""
import logging
import json
from datetime import date
from typing import Dict
from app.services.llm_service import get_llm_service, log_llm_call

logger = logging.getLogger(__name__)


def write_daily_entry(classified: Dict, entry_date: date) -> Dict:
    """
    Paso 3: Redacta el editorial y genera JSON válido
    
    Args:
        classified: Output del Classifier Agent
        entry_date: Fecha de la entrada
        
    Returns:
        Dict con estructura de Entry:
        {
            'date': 'YYYY-MM-DD',
            'editorial': 'texto...',
            'new_tools': [...],
            'updates': [...]
        }
    """
    logger.info("Starting Writer Agent...")
    
    new_tools = classified.get('new_tools', [])
    updates = classified.get('updates', [])
    
    if not new_tools and not updates:
        logger.warning("No content to write about")
        return {
            'date': entry_date.isoformat(),
            'editorial': 'No se encontraron novedades significativas hoy.',
            'new_tools': [],
            'updates': []
        }
    
    llm = get_llm_service()
    
    # Resumen para el LLM
    content_summary = "NUEVAS HERRAMIENTAS:\n"
    for tool in new_tools[:10]:
        content_summary += f"- {tool['name']}: {tool.get('summary', 'N/A')}\n"
    
    if updates:
        content_summary += "\n\nACTUALIZACIONES:\n"
        for upd in updates[:10]:
            content_summary += f"- {upd['tool_slug']}: {upd.get('description', 'N/A')}\n"
    
    system_prompt = f"""Eres el editor del blog "SciTools Radar", que reporta novedades diarias en herramientas científicas para investigadores académicos.

Fecha: {entry_date.strftime('%d de %B de %Y')}

Escribe un editorial breve (2-3 párrafos, estilo profesional pero accesible) que:
1. Resuma las novedades del día
2. Destaque 1-2 herramientas más relevantes
3. Proporcione contexto sobre por qué son importantes

Luego, estructura los datos en JSON válido:

{{
  "date": "{entry_date.isoformat()}",
  "editorial": "Tu editorial aquí...",
  "new_tools": [
    # Copia exacta de new_tools del input
  ],
  "updates": [
    # Copia exacta de updates del input
  ]
}}

IMPORTANTE: El JSON debe ser válido y parseable. Usa comillas dobles, escapa caracteres especiales."""

    try:
        response = llm.writer_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Contenido del día:\n\n{content_summary}\n\nData original:\n{json.dumps(classified, indent=2, ensure_ascii=False)}"}
            ],
            temperature=0.4
        )
        
        log_llm_call('writer', response)
        
        # Parse JSON
        result_text = response.choices[0].message.content
        
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0]
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0]
        
        entry_data = json.loads(result_text.strip())
        
        # Validar estructura mínima
        if 'date' not in entry_data or 'editorial' not in entry_data:
            raise ValueError("Invalid entry structure: missing required fields")
        
        logger.info(f"Writer generated entry: {len(entry_data.get('editorial', ''))} chars editorial")
        
        return entry_data
    
    except Exception as e:
        logger.error(f"Writer failed: {e}")
        # Fallback: entrada básica sin editorial elabor ado
        return {
            'date': entry_date.isoformat(),
            'editorial': f"Actualización del {entry_date.strftime('%d/%m/%Y')}. "
                        f"Se registraron {len(new_tools)} nuevas herramientas y {len(updates)} actualizaciones.",
            'new_tools': new_tools,
            'updates': updates
        }
