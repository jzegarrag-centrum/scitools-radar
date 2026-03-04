# SciTools Radar Flask

Aplicación Flask para radar de herramientas científicas con agente autónomo.

## Despliegue en Railway

Este proyecto usa Nixpacks (auto-detect) para despliegue en Railway.

### Variables de entorno a configurar en Railway:

```
COMETAPI_KEY=sk-j2gAYJxByJVvIaktLh0USEk2OcevDPmmxGV26GVunBxUMPKS
TAVILY_API_KEY=tu-tavily-key
SECRET_KEY=genera-con-secrets-token-hex
API_KEY=tu-api-key-segura
ADMIN_EMAIL=admin@smartcentrum.edu.pe
ADMIN_PASSWORD=tu-password-seguro
AGENT_ENABLED=True
```

DATABASE_URL y REDIS_URL se auto-provisionan al agregar los plugins.
