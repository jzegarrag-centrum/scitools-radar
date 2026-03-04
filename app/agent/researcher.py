"""
Research Agent - Paso 1
Busca novedades en categorías científicas via Tavily
"""
import logging
from typing import List, Dict
from tavily import TavilyClient
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


def research_daily_tools(existing_slugs: List[str]) -> List[Dict]:
    """
    Paso 1: Busca novedades en las 16 categorías
    
    Args:
        existing_slugs: Lista de slugs de herramientas ya existentes
        
    Returns:
        Lista de hallazgos crudos con fuentes
    """
    logger.info("Starting Research Agent...")
    
    tavily_key = current_app.config.get('TAVILY_API_KEY')
    if not tavily_key:
        logger.warning("TAVILY_API_KEY not configured, skipping web search")
        return []
    
    tavily = TavilyClient(api_key=tavily_key)
    
    # 1. Web search en cada categoría
    search_results = []
    for category in CATEGORIES:
        try:
            results = tavily.search(
                query=f"new scientific research tool {category} last 48 hours",
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
            
            logger.info(f"Category '{category}': {len(results.get('results', []))} results")
        
        except Exception as e:
            logger.error(f"Tavily search failed for '{category}': {e}")
            continue
    
    logger.info(f"Total raw results: {len(search_results)}")
    
    # 2. LLM sintetiza hallazgos
    if not search_results:
        logger.warning("No search results to analyze")
        return []
    
    llm = get_llm_service()
    
    # Preparar prompt
    search_summary = "\n\n".join([
        f"**{r['category']}**\n"
        f"Title: {r['title']}\n"
        f"URL: {r['url']}\n"
        f"Content: {r['content'][:500]}..."
        for r in search_results[:30]  # Limitar para no exceder context
    ])
    
    system_prompt = f"""Eres un asistente experto en identificar nuevas herramientas científicas.

Analiza los siguientes resultados de búsqueda web y extrae SOLO herramientas científicas reales que sean:
- Software, plataformas web, o servicios específicos
- Útiles para investigadores académicos
- Mencionados con nombre concreto (no conceptos genéricos)

IMPORTANTE: NO incluyas herramientas que ya conocemos: {', '.join(existing_slugs[:50])}

Para cada herramienta encontrada, extrae:
- Nombre exacto de la herramienta
- URL si está disponible
- Resumen corto (1-2 líneas)
- Categoría que mejor le corresponde
- Fuente URL de donde la encontraste

Responde en formato JSON array:
[
  {{
    "name": "Nombre Tool",
    "url": "https://...",
    "summary": "Breve descripción",
    "category": "categoria-principal",
    "source_url": "url-donde-se-menciona"
  }}
]

Si no encuentras herramientas nuevas válidas, responde con array vacío []."""

    try:
        response = llm.research_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Resultados de búsqueda:\n\n{search_summary}"}
            ],
            temperature=0.3
        )
        
        log_llm_call('research', response, {'results_count': len(search_results)})
        
        # Parse JSON response
        import json
        findings_text = response.choices[0].message.content
        
        # Limpiar markdown si existe
        if '```json' in findings_text:
            findings_text = findings_text.split('```json')[1].split('```')[0]
        elif '```' in findings_text:
            findings_text = findings_text.split('```')[1].split('```')[0]
        
        findings = json.loads(findings_text.strip())
        
        logger.info(f"Research Agent found {len(findings)} potential tools")
        
        return findings
    
    except Exception as e:
        logger.error(f"LLM synthesis failed: {e}")
        return []
