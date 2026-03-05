"""
Scheduler del Agente - Orquesta los 6 pasos diarios
"""
import logging
import re
from datetime import datetime, date
from urllib.parse import urlparse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import current_app
from app import db
from app.models import Tool, Entry, Update, AgentRun
from app.agent.researcher import research_daily_tools
from app.agent.classifier import classify_findings
from app.agent.updater import refresh_existing_tools, apply_tool_updates
from app.agent.writer import write_daily_entry
from app.agent.evaluator import evaluate_entry_quality
from app.services.llm_service import get_llm_service

logger = logging.getLogger(__name__)

scheduler = None


def init_scheduler(app):
    """
    Inicializa el scheduler del agente.
    Usa gunicorn --workers 1 para evitar jobs duplicados.
    """
    global scheduler
    
    if not app.config.get('AGENT_ENABLED', False):
        logger.info("Agent scheduler DISABLED by config")
        return
    
    if scheduler is not None:
        logger.info("Scheduler already running, skipping")
        return
    
    scheduler = BackgroundScheduler(timezone='America/Lima')
    
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


def _select_tools_for_refresh(existing_tools, max_refresh=10):
    """
    Selecciona herramientas que necesitan actualización.
    Prioriza: sin descripción, descripción corta, más antiguas.
    """
    scored = []
    for t in existing_tools:
        score = 0
        # Sin summary o muy corto → prioridad alta
        if not t.summary or len(t.summary) < 30:
            score += 50
        elif len(t.summary) < 80:
            score += 20
        # Sin pricing/platform/developer → datos incompletos
        if not t.pricing:
            score += 10
        if not t.platform:
            score += 10
        if not t.developer:
            score += 5
        # Más antigua la última actualización → más urgente
        if t.last_updated:
            days_old = (datetime.utcnow() - t.last_updated).days
            score += min(days_old, 60)  # Cap en 60 puntos
        else:
            score += 60
        scored.append((t, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    selected = [t for t, _ in scored[:max_refresh]]

    logger.info(
        f"Selected {len(selected)} tools for refresh "
        f"(top scores: {[f'{t.slug}={s}' for t, s in scored[:5]]})"
    )
    return selected


def run_daily_agent():
    """
    Ejecuta el pipeline completo del agente
    
    Pasos:
    0. Inventory Check
    1. Research Agent (LLM + Tavily) — descubrir nuevas herramientas
    2. Classifier Agent — clasificar hallazgos
    2B. Tool Updater — refrescar herramientas existentes
    3. Writer Agent — redactar editorial
    4. Entry Creator — insertar en BD
    5. Quality Evaluator — evaluar calidad
    """
    logger.info("=" * 60)
    logger.info("STARTING DAILY AGENT RUN")
    logger.info("=" * 60)
    
    run = AgentRun(
        started_at=datetime.utcnow(),
        status='running'
    )
    db.session.add(run)
    db.session.commit()
    
    try:
        # Verificar si ya existe entrada para hoy
        from datetime import date as date_cls
        today = date_cls.today()
        existing_entry = Entry.query.filter_by(date=today).first()
        if existing_entry:
            logger.warning(f"Entry for {today} already exists (id={existing_entry.id}) — skipping run")
            run.status = 'success'
            run.finished_at = datetime.utcnow()
            run.entry_id = existing_entry.id
            run.error = f'Entry for {today} already exists'
            db.session.commit()
            return

        # PASO 0: Obtener inventario actual
        logger.info("[STEP 0] Inventory Check")
        existing_tools = Tool.query.filter_by(status='active').all()
        existing_slugs = [t.slug for t in existing_tools]
        logger.info(f"Current inventory: {len(existing_slugs)} active tools")
        
        # PASO 1: Investigar nuevas herramientas
        logger.info("[STEP 1] Research Agent")
        findings = research_daily_tools(existing_slugs)
        run.tools_found = len(findings)
        db.session.commit()
        
        # PASO 2: Clasificar hallazgos
        logger.info("[STEP 2] Classifier Agent")
        if findings:
            classified = classify_findings(findings, existing_tools)
        else:
            classified = {'new_tools': [], 'updates': []}
        
        new_tools_data = classified.get('new_tools', [])
        updates_from_classifier = classified.get('updates', [])
        
        run.tools_new = len(new_tools_data)
        db.session.commit()
        
        logger.info(f"Classified: {len(new_tools_data)} new, {len(updates_from_classifier)} updates")
        
        # Límites de config
        max_new = current_app.config.get('AGENT_MAX_NEW_TOOLS', 6)
        max_updates = current_app.config.get('AGENT_MAX_UPDATES', 5)
        new_tools_data = new_tools_data[:max_new]
        
        # PASO 2B: Refrescar herramientas existentes
        logger.info("[STEP 2B] Tool Updater")
        max_refresh = current_app.config.get('AGENT_MAX_REFRESH', 10)
        tools_to_refresh = _select_tools_for_refresh(existing_tools, max_refresh)
        
        updater_results = []
        if tools_to_refresh:
            updater_results = refresh_existing_tools(tools_to_refresh)
            update_stats = apply_tool_updates(updater_results)
            logger.info(f"Tool Updater: {update_stats['updated']} tools refreshed")
        
        # Combinar updates del classifier + updater para el editorial
        all_updates_for_writer = updates_from_classifier[:max_updates]
        
        # Añadir resúmenes del updater como updates para el writer
        for ur in updater_results:
            for change in ur.get('changes', []):
                all_updates_for_writer.append({
                    'tool_slug': ur['tool_slug'],
                    'field_updated': change.get('field', 'summary'),
                    'new_value': change.get('new_value', ''),
                    'description': f"{ur.get('tool_name', ur['tool_slug'])}: {change.get('reason', 'actualización')}"
                })
        
        run.updates_count = len(all_updates_for_writer)
        db.session.commit()
        
        # Si no hay nada nuevo ni actualizaciones, terminar
        if not new_tools_data and not all_updates_for_writer:
            logger.warning("No new tools or updates — ending run")
            run.status = 'success'
            run.finished_at = datetime.utcnow()
            db.session.commit()
            return
        
        # PASO 3: Redactar
        logger.info("[STEP 3] Writer Agent")
        entry_data = write_daily_entry(
            {'new_tools': new_tools_data, 'updates': all_updates_for_writer},
            date.today()
        )
        
        # PASO 4: Insertar en DB
        logger.info("[STEP 4] Entry Creator")
        entry = create_entry_from_data(entry_data)
        
        run.entry_id = entry.id
        db.session.commit()
        logger.info(f"Entry created: ID={entry.id}, date={entry.date}")
        
        # PASO 4B: Generar imagen de portada
        logger.info("[STEP 4B] Cover Image Generation")
        generate_cover_image(entry)
        
        # PASO 4C: Obtener logos de herramientas
        logger.info("[STEP 4C] Tool Logo Fetching")
        fetch_tool_logos(entry)
        
        # PASO 5: Evaluar calidad
        logger.info("[STEP 5] Quality Evaluator")
        scores = evaluate_entry_quality(entry)
        
        run.completeness = scores.get('completeness')
        run.field_diversity = scores.get('field_diversity')
        run.social_coverage = scores.get('social_coverage')
        run.hallucination_risk = scores.get('hallucination_risk')
        
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
        logger.info(f"New tools: {len(new_tools_data)}, Updates: {len(all_updates_for_writer)}")
        logger.info(f"Quality: completeness={run.completeness:.2f}, "
                   f"diversity={run.field_diversity:.2f}, "
                   f"hallucination={run.hallucination_risk:.2f}")
        logger.info("=" * 60)
    
    except Exception as e:
        logger.error(f"Agent run failed: {e}", exc_info=True)
        run.status = 'failed'
        run.error = str(e)
        run.finished_at = datetime.utcnow()
        db.session.commit()


def generate_cover_image(entry: Entry):
    """
    Genera imagen de portada para la entrada usando DALL-E 3.
    Construye un prompt basado en el editorial.
    """
    if entry.cover_image_url:
        logger.info(f"Entry {entry.id} already has a cover image — skipping")
        return

    try:
        llm = get_llm_service()

        # Extraer primer párrafo del editorial como contexto
        editorial_preview = (entry.editorial or '')[:300]

        # Generar un prompt de imagen a partir del contenido editorial
        prompt = (
            f"A clean, modern, professional editorial illustration for a science & technology blog post. "
            f"Abstract composition with subtle gradients in deep navy blue (#003865) and gold (#C5922E). "
            f"Theme: {editorial_preview}. "
            f"Style: minimalist, geometric shapes, data visualization motifs, interconnected nodes, "
            f"digital research tools. No text, no words, no letters. Widescreen 16:9 aspect ratio."
        )

        url = llm.generate_image(prompt, size='1792x1024', model='dall-e-3')

        if url:
            entry.cover_image_url = url
            db.session.commit()
            logger.info(f"Cover image generated for entry {entry.id}: {url[:80]}...")
        else:
            logger.warning(f"Failed to generate cover image for entry {entry.id}")

    except Exception as e:
        logger.error(f"Cover image generation error: {e}")


def fetch_tool_logos(entry: Entry):
    """
    Intenta obtener logos/favicons para las herramientas de la entrada.
    Usa Google Favicon API como fuente confiable.
    """
    for tool in entry.tools:
        if tool.logo_url:
            continue  # Ya tiene logo

        if not tool.url:
            continue

        try:
            parsed = urlparse(tool.url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            if not domain:
                continue

            # Google Favicon API — 128px, muy confiable
            logo_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
            tool.logo_url = logo_url
            logger.info(f"Assigned logo for {tool.slug}: {logo_url}")

        except Exception as e:
            logger.warning(f"Logo fetch failed for {tool.slug}: {e}")

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
    
    # Verificar si ya existe una entrada para esta fecha
    existing = Entry.query.filter_by(date=entry_date).first()
    if existing:
        logger.warning(f"Entry for {entry_date} already exists (id={existing.id}) — returning existing")
        return existing
    
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
