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

INSTRUCCIÓN OBLIGATORIA: Escribe un artículo completo entre 800 y 1500 palabras. Este es un requisito estricto — el artículo DEBE tener al menos 800 palabras. Un artículo de menos de 500 palabras será rechazado.

ESTRUCTURA DEL ARTÍCULO:
1. **Bajada / Lead** (primer párrafo, ~80-120 palabras): Un resumen atractivo y conciso del contenido del día que enganche al lector. Este párrafo aparecerá destacado visualmente como introducción.

2. **Desarrollo** (4-6 párrafos sustanciales, ~600-1000 palabras total):
   - Párrafo de contexto: panorama general de las tendencias que se observan en las herramientas del día
   - Para cada herramienta nueva destacada, un párrafo descriptivo de al menos 100 palabras que explique:
     • Qué problema resuelve para el investigador
     • Cómo funciona y qué la diferencia de alternativas existentes
     • Para qué tipo de investigador o disciplina resulta más útil
     • Modelo de precios si es relevante
   - Si hay actualizaciones de herramientas existentes, un párrafo que las integre en la narrativa
   - Cada párrafo debe ser sustancial (mínimo 80 palabras), NO resúmenes de una oración

3. **Cierre** (1-2 párrafos, ~100-150 palabras): Reflexión analítica sobre la importancia de estas herramientas para la comunidad investigadora, tendencias observadas y perspectivas.

ESTILO:
- Español profesional pero accesible para investigadores
- Tono informativo y analítico, como una columna de tecnología científica
- Usa párrafos completos y bien desarrollados, NO bullet points
- Separa CADA párrafo con doble salto de línea (\\n\\n) — esto es CRÍTICO para el renderizado
- Incluye contexto analítico y valor agregado, no solo listados
- Mínimo 7 párrafos sustanciales en total

Luego, estructura los datos en JSON válido:

{{
  "date": "{entry_date.isoformat()}",
  "editorial": "Tu artículo completo aquí (párrafos separados por \\n\\n)...",
  "new_tools": [
    # Copia exacta de new_tools del input, asegurándote de incluir pricing, platform y features
  ],
  "updates": [
    # Copia exacta de updates del input
  ]
}}

IMPORTANTE: 
- El JSON debe ser válido y parseable. Usa comillas dobles, escapa caracteres especiales.
- El editorial DEBE tener al menos 800 palabras y múltiples párrafos separados por \\n\\n.
- NO generes solo un resumen corto — esto es un artículo completo de blog."""

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
        
        editorial_text = entry_data.get('editorial', '')
        word_count = len(editorial_text.split())
        logger.info(f"Writer generated entry: {len(editorial_text)} chars, {word_count} words editorial")
        
        # Si el editorial es demasiado corto, reintentar una vez
        if word_count < 300:
            logger.warning(f"Editorial too short ({word_count} words), retrying with stronger prompt...")
            retry_response = llm.writer_call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Contenido del día:\n\n{content_summary}\n\nData original:\n{json.dumps(classified, indent=2, ensure_ascii=False)}"},
                    {"role": "assistant", "content": result_text},
                    {"role": "user", "content": f"El editorial que generaste tiene solo {word_count} palabras. "
                     f"Necesito MÍNIMO 800 palabras. Reescribe el artículo completo con párrafos "
                     f"más desarrollados y analíticos. Devuelve el JSON completo de nuevo."}
                ],
                temperature=0.5
            )
            log_llm_call('writer_retry', retry_response)
            retry_text = retry_response.choices[0].message.content
            if '```json' in retry_text:
                retry_text = retry_text.split('```json')[1].split('```')[0]
            elif '```' in retry_text:
                retry_text = retry_text.split('```')[1].split('```')[0]
            try:
                retry_data = json.loads(retry_text.strip())
                retry_words = len(retry_data.get('editorial', '').split())
                if retry_words > word_count:
                    entry_data = retry_data
                    logger.info(f"Retry successful: {retry_words} words")
            except Exception as retry_err:
                logger.warning(f"Retry parse failed ({retry_err}), using original")
        
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
