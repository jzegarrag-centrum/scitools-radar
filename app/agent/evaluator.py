"""
Quality Evaluator - Paso 5
Evalúa la calidad de la entrada generada con LLM-as-judge
"""
import logging
import json
from typing import Dict
from app.models import Entry
from app.services.llm_service import get_llm_service, log_llm_call

logger = logging.getLogger(__name__)


def evaluate_entry_quality(entry: Entry) -> Dict[str, float]:
    """
    Paso 5: Evalúa calidad de la entrada
    
    Args:
        entry: Entry generada (ya en DB)
        
    Returns:
        Dict con scores:
        {
            'completeness': 0.0-1.0,
            'field_diversity': 0.0-1.0,
            'social_coverage': 0.0-1.0,
            'hallucination_risk': 0.0-1.0
        }
    """
    logger.info(f"Evaluating entry quality: Entry {entry.id}")
    
    # Métrica 1: Completitud (determinística)
    completeness = calculate_completeness(entry)
    
    # Métrica 2: Diversidad de campos
    diversity = calculate_field_diversity(entry)
    
    # Métrica 3: Cobertura de ciencias sociales
    social_coverage = check_social_science_coverage(entry)
    
    # Métrica 4: Hallucination check (LLM-as-judge)
    hallucination_risk = check_hallucination_risk(entry)
    
    scores = {
        'completeness': completeness,
        'field_diversity': diversity,
        'social_coverage': social_coverage,
        'hallucination_risk': hallucination_risk
    }
    
    logger.info(f"Quality scores: {scores}")
    
    return scores


def calculate_completeness(entry: Entry) -> float:
    """Calcula completitud: todos los campos llenos"""
    total_fields = 0
    filled_fields = 0
    
    # Editorial
    total_fields += 1
    if entry.editorial and len(entry.editorial) > 50:
        filled_fields += 1
    
    # Tools
    for tool in entry.tools:
        total_fields += 4  # name, summary, url, category
        if tool.name:
            filled_fields += 1
        if tool.summary and len(tool.summary) > 20:
            filled_fields += 1
        if tool.url:
            filled_fields += 1
        if tool.category:
            filled_fields += 1
    
    return filled_fields / total_fields if total_fields > 0 else 0.0


def calculate_field_diversity(entry: Entry) -> float:
    """Diversidad de campos disciplinares"""
    fields = set(t.field for t in entry.tools if t.field)
    
    # Meta: al menos 3 campos distintos
    diversity_score = min(len(fields) / 3.0, 1.0)
    
    return diversity_score


def check_social_science_coverage(entry: Entry) -> float:
    """Cobertura de ciencias sociales (meta: 2/5 tools)"""
    social_keywords = [
        'social', 'econom', 'psycholog', 'sociolog', 'anthropolog',
        'political', 'qualitative', 'survey', 'interview'
    ]
    
    social_count = 0
    for tool in entry.tools:
        tool_text = f"{tool.name} {tool.summary or ''}".lower()
        if any(kw in tool_text for kw in social_keywords):
            social_count += 1
    
    # Score basado en meta de 2/5 (40%)
    total_tools = len(entry.tools)
    if total_tools == 0:
        return 0.0
    
    social_ratio = social_count / total_tools
    # Score: 1.0 si >= 40%, proporcional si < 40%
    score = min(social_ratio / 0.4, 1.0)
    
    return score


def check_hallucination_risk(entry: Entry) -> float:
    """
    LLM-as-judge para detectar hallucinations
    
    Returns:
        Risk score 0.0-1.0 (0=no risk, 1=high risk)
    """
    llm = get_llm_service()
    
    # Preparar contenido para evaluar
    tools_summary = "\n".join([
        f"- {t.name}: {t.summary[:200]}" if t.summary else f"- {t.name}"
        for t in entry.tools[:10]
    ])
    
    content_to_check = f"""Editorial:
{entry.editorial}

Herramientas mencionadas:
{tools_summary}"""
    
    system_prompt = """Eres un evaluador experto en detectar información fabricada o inexacta.

Analiza el siguiente contenido sobre herramientas científicas y detecta:
1. Nombres de herramientas que parecen inventados o genéricos
2. Descripciones vagas o sin sustancia real
3. Claims exagerados o inverosímiles
4. Inconsistencias lógicas

Responde en JSON:
{
  "hallucination_risk": 0.0-1.0,
  "reason": "Breve explicación",
  "suspicious_items": ["lista de elementos sospechosos si los hay"]
}

Donde:
- 0.0 = Todo parece legítimo y específico
- 0.3 = Algunas descripciones vagas pero aceptable
- 0.5 = Varias señales de alerta
- 0.8+ = Alta probabilidad de información fabricada"""
    
    try:
        response = llm.evaluator_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_to_check}
            ],
            temperature=0.1
        )
        
        log_llm_call('evaluator', response, {'entry_id': entry.id})
        
        # Parse JSON
        result_text = response.choices[0].message.content
        
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0]
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0]
        
        eval_result = json.loads(result_text.strip())
        
        risk = float(eval_result.get('hallucination_risk', 0.5))
        
        if eval_result.get('suspicious_items'):
            logger.warning(f"Suspicious items detected: {eval_result['suspicious_items']}")
        
        return risk
    
    except Exception as e:
        logger.error(f"Hallucination check failed: {e}")
        return 0.5  # Default: medium risk if eval fails
