"""
Classifier Agent - Paso 2
Clasifica hallazgos como herramientas nuevas o updates de existentes
"""
import logging
import json
from typing import List, Dict
from app.services.llm_service import get_llm_service, log_llm_call
from app.models import Tool

logger = logging.getLogger(__name__)


def classify_findings(findings: List[Dict], existing_tools: List[Tool]) -> Dict:
    """
    Paso 2: Clasifica hallazgos en tools nuevas o updates
    
    Args:
        findings: Lista de hallazgos del Research Agent
        existing_tools: Lista de Tools existentes (para comparar)
        
    Returns:
        Dict con {
            'new_tools': [{...}],
            'updates': [{tool_id, field_updated, new_value, description}]
        }
    """
    logger.info(f"Starting Classifier Agent with {len(findings)} findings...")
    
    if not findings:
        return {'new_tools': [], 'updates': []}
    
    # Inventario actual para el LLM
    inventory_summary = "\n".join([
        f"- {t.slug}: {t.name} ({t.summary[:100]}...)" if t.summary else f"- {t.slug}: {t.name}"
        for t in existing_tools[:200]  # Limitar contexto
    ])
    
    llm = get_llm_service()
    
    system_prompt = f"""Eres un clasificador experto de herramientas científicas.

INVENTARIO ACTUAL (primeras 200 herramientas):
{inventory_summary}

Tu tarea: Clasifica cada hallazgo como:
1. **NUEVA HERRAMIENTA**: Si no existe en el inventario o es significativamente distinta
2. **ACTUALIZACIÓN**: Si es información nueva sobre una herramienta que YA existe

Para NUEVAS herramientas, genera un 'slug' único (formato: lowercase-con-guiones).
Para ACTUALIZACIONES, identifica el 'tool_slug' exacto del inventario y el campo que se actualizó.

Responde en JSON:
{{
  "new_tools": [
    {{
      "slug": "nombre-herramienta",
      "name": "Nombre Oficial",
      "url": "https://...",
      "summary": "Descripción",
      "field": "campo-disciplinar",
      "category": "letra-A-P",
      "source_url": "fuente"
    }}
  ],
  "updates": [
    {{
      "tool_slug": "slug-existente",
      "field_updated": "url|summary|category",
      "new_value": "nuevo valor",
      "description": "Qué cambió y por qué"
    }}
  ]
}}"""

    findings_text = json.dumps(findings, indent=2, ensure_ascii=False)
    
    try:
        response = llm.classifier_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Hallazgos a clasificar:\n\n{findings_text}"}
            ],
            temperature=0.2
        )
        
        log_llm_call('classifier', response, {'findings': len(findings)})
        
        # Parse JSON
        result_text = response.choices[0].message.content
        
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0]
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0]
        
        classified = json.loads(result_text.strip())
        
        logger.info(
            f"Classifier: {len(classified.get('new_tools', []))} new, "
            f"{len(classified.get('updates', []))} updates"
        )
        
        return classified
    
    except Exception as e:
        logger.error(f"Classifier failed: {e}")
        return {'new_tools': [], 'updates': []}
