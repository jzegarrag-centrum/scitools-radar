"""
Scheduler del Agente - Orquesta los 5 pasos diarios
"""
import logging
from datetime import datetime, date
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import current_app
from app import db
from app.models import Tool, Entry, Update, AgentRun
from app.agent.researcher import research_daily_tools
from app.agent.classifier import classify_findings
from app.agent.writer import write_daily_entry
from app.agent.evaluator import evaluate_entry_quality

logger = logging.getLogger(__name__)

scheduler = None


def init_scheduler(app):
    """
    Inicializa el scheduler del agente
    
    Args:
        app: Flask app instance
    """
    global scheduler
    
    if not app.config.get('AGENT_ENABLED', False):
        logger.info("Agent scheduler DISABLED by config")
        return
    
    scheduler = BackgroundScheduler(timezone='America/Lima')
    
    # Job diario: lunes a viernes
    hour = app.config.get('AGENT_SCHEDULE_HOUR', 7)
    days = app.config.get('AGENT_SCHEDULE_DAYS', 'mon-fri')
    
    scheduler.add_job(
        func=lambda: run_daily_agent_with_context(app),
        trigger=CronTrigger(day_of_week=days, hour=hour, minute=0),
        id='daily_research_agent',
        name='SciTools Daily Research Agent',
        replace_existing=True
    )
    
    scheduler.start()
    
    logger.info(f"Agent scheduler initialized: {days} at {hour}:00 Lima time")


def run_daily_agent_with_context(app):
    """Wrapper para ejecutar con app context"""
    with app.app_context():
        run_daily_agent()


def run_daily_agent():
    """
    Ejecuta el pipeline completo del agente
    
    Pasos:
    0. Inventory Check
    1. Research Agent (GPT-5.3 + Tavily)
    2. Classifier Agent (Gemini Flash Lite)
    3. Writer Agent (GPT-5.3 JSON mode)
    4. Entry Creator (DB insert)
    5. Quality Evaluator (GPT-5 Nano)
    """
    logger.info("=" * 60)
    logger.info("STARTING DAILY AGENT RUN")
    logger.info("=" * 60)
    
    # Crear registro de ejecución
    run = AgentRun(
        started_at=datetime.utcnow(),
        status='running'
    )
    db.session.add(run)
    db.session.commit()
    
    try:
        # PASO 0: Obtener inventario actual
        logger.info("[STEP 0] Inventory Check")
        existing_tools = Tool.query.filter_by(status='active').all()
        existing_slugs = [t.slug for t in existing_tools]
        logger.info(f"Current inventory: {len(existing_slugs)} active tools")
        
        # PASO 1: Investigar
        logger.info("[STEP 1] Research Agent")
        findings = research_daily_tools(existing_slugs)
        run.tools_found = len(findings)
        db.session.commit()
        
        if not findings:
            logger.warning("No findings from research - ending run")
            run.status = 'success'
            run.finished_at = datetime.utcnow()
            db.session.commit()
            return
        
        # PASO 2: Clasificar
        logger.info("[STEP 2] Classifier Agent")
        classified = classify_findings(findings, existing_tools)
        
        new_tools_data = classified.get('new_tools', [])
        updates_data = classified.get('updates', [])
        
        run.tools_new = len(new_tools_data)
        run.updates_count = len(updates_data)
        db.session.commit()
        
        logger.info(f"Classified: {len(new_tools_data)} new, {len(updates_data)} updates")
        
        # Límites de config
        max_new = current_app.config.get('AGENT_MAX_NEW_TOOLS', 6)
        max_updates = current_app.config.get('AGENT_MAX_UPDATES', 5)
        
        new_tools_data = new_tools_data[:max_new]
        updates_data = updates_data[:max_updates]
        
        # PASO 3: Redactar
        logger.info("[STEP 3] Writer Agent")
        entry_data = write_daily_entry(
            {'new_tools': new_tools_data, 'updates': updates_data},
            date.today()
        )
        
        # PASO 4: Insertar en DB
        logger.info("[STEP 4] Entry Creator")
        entry = create_entry_from_data(entry_data)
        
        run.entry_id = entry.id
        db.session.commit()
        
        logger.info(f"Entry created: ID={entry.id}, date={entry.date}")
        
        # PASO 5: Evaluar calidad
        logger.info("[STEP 5] Quality Evaluator")
        scores = evaluate_entry_quality(entry)
        
        run.completeness = scores.get('completeness')
        run.field_diversity = scores.get('field_diversity')
        run.social_coverage = scores.get('social_coverage')
        run.hallucination_risk = scores.get('hallucination_risk')
        
        # TODO: Calcular costos reales desde logs
        run.total_tokens = 0
        run.total_cost_usd = 0.0
        run.models_used = {
            'research': current_app.config['MODELS']['research'],
            'classifier': current_app.config['MODELS']['classifier'],
            'writer': current_app.config['MODELS']['writer'],
            'evaluator': current_app.config['MODELS']['evaluator'],
        }
        
        run.status = 'success'
        run.finished_at = datetime.utcnow()
        db.session.commit()
        
        logger.info("=" * 60)
        logger.info(f"AGENT RUN COMPLETED SUCCESSFULLY in {run.duration_seconds:.1f}s")
        logger.info(f"Quality scores: completeness={run.completeness:.2f}, "
                   f"diversity={run.field_diversity:.2f}, "
                   f"hallucination={run.hallucination_risk:.2f}")
        logger.info("=" * 60)
    
    except Exception as e:
        logger.error(f"Agent run failed: {e}", exc_info=True)
        run.status = 'failed'
        run.error = str(e)
        run.finished_at = datetime.utcnow()
        db.session.commit()


def create_entry_from_data(entry_data: dict) -> Entry:
    """
    Crea Entry y Tools/Updates en la DB desde el JSON del Writer
    
    Args:
        entry_data: Dict con keys: date, editorial, new_tools, updates
        
    Returns:
        Entry creada
    """
    from datetime import datetime
    
    entry_date = datetime.strptime(entry_data['date'], '%Y-%m-%d').date()
    
    # Crear Entry
    entry = Entry(
        date=entry_date,
        editorial=entry_data['editorial'],
        created_by='agent',
        created_at=datetime.utcnow()
    )
    db.session.add(entry)
    db.session.flush()  # Para obtener entry.id
    
    # Crear Tools nuevas
    for tool_data in entry_data.get('new_tools', []):
        tool = Tool(
            slug=tool_data['slug'],
            name=tool_data['name'],
            summary=tool_data.get('summary'),
            url=tool_data.get('url'),
            field=tool_data.get('field'),
            category=tool_data.get('category'),
            priority_source=tool_data.get('source_url', '').split('/')[2] if tool_data.get('source_url') else None,
            first_seen=datetime.utcnow(),
            status='active'
        )
        db.session.add(tool)
        entry.tools.append(tool)
    
    # Crear Updates
    for upd_data in entry_data.get('updates', []):
        # Buscar tool existente
        tool = Tool.query.filter_by(slug=upd_data['tool_slug']).first()
        
        if not tool:
            logger.warning(f"Tool '{upd_data['tool_slug']}' not found for update - skipping")
            continue
        
        # Guardar valor viejo
        field_name = upd_data['field_updated']
        old_value = str(getattr(tool, field_name, ''))
        
        # Actualizar tool
        setattr(tool, field_name, upd_data['new_value'])
        tool.last_updated = datetime.utcnow()
        
        # Crear Update record
        update = Update(
            tool_id=tool.id,
            entry_id=entry.id,
            field_updated=field_name,
            old_value=old_value,
            new_value=upd_data['new_value'],
            description=upd_data.get('description', ''),
            created_at=datetime.utcnow()
        )
        db.session.add(update)
        entry.updates.append(update)
    
    db.session.commit()
    
    logger.info(f"Created entry with {len(entry.tools)} tools and {len(entry.updates)} updates")
    
    return entry


def stop_scheduler():
    """Detiene el scheduler (para cleanup)"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        logger.info("Agent scheduler stopped")
