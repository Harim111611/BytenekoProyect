#!/bin/bash

# =============================================================================
# Byteneko - Script de Gestión de Deployment
# =============================================================================
# Este script facilita operaciones comunes de deployment y mantenimiento
# =============================================================================

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Variables

# Set DJANGO_SETTINGS_MODULE to new path
export DJANGO_SETTINGS_MODULE="byteneko.settings.production"

# If you want to use local or test settings, change to:
# export DJANGO_SETTINGS_MODULE="byteneko.settings.local"
# export DJANGO_SETTINGS_MODULE="byteneko.settings.test"

# Funciones de ayuda
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# =============================================================================
# COMANDOS
# =============================================================================

# Deploy: Actualizar código y reiniciar servicios
deploy() {
    print_info "Iniciando deployment..."
    
    cd $PROJECT_DIR
    
    # Hacer backup de base de datos antes de actualizar
    print_info "Creando backup de base de datos..."
    backup_db
    
    # Pull cambios
    print_info "Obteniendo últimos cambios del repositorio..."
    git pull origin main
    
    # Instalar/actualizar dependencias
    print_info "Instalando dependencias..."
    source $VENV_DIR/bin/activate
    $PIP install -r requirements.txt --quiet
    
    # Ejecutar migraciones
    print_info "Ejecutando migraciones..."
    $MANAGE migrate --noinput
    
    # Recopilar archivos estáticos
    print_info "Recopilando archivos estáticos..."
    $MANAGE collectstatic --noinput
    
    # Reiniciar servicios
    print_info "Reiniciando servicios..."
    sudo supervisorctl restart all
    
    print_success "Deployment completado exitosamente!"
}

# Status: Ver estado de todos los servicios
status() {
    print_info "Estado de servicios:"
    echo ""
    sudo supervisorctl status
    echo ""
    print_info "PostgreSQL:"
    sudo systemctl status postgresql --no-pager -l
    echo ""
    print_info "Redis:"
    sudo systemctl status redis-server --no-pager -l
    echo ""
    print_info "NGINX:"
    sudo systemctl status nginx --no-pager -l
}

# Logs: Ver logs en tiempo real
logs() {
    SERVICE=${1:-gunicorn}
    
    case $SERVICE in
        gunicorn)
            tail -f $PROJECT_DIR/logs/gunicorn_error.log
            ;;
        celery)
            tail -f $PROJECT_DIR/logs/celery_worker.log
            ;;
        celerybeat)
            tail -f $PROJECT_DIR/logs/celery_beat.log
            ;;
        nginx)
            tail -f /var/log/nginx/byteneko_error.log
            ;;
        django)
            tail -f $PROJECT_DIR/logs/error.log
            ;;
        *)
            print_error "Servicio no reconocido. Opciones: gunicorn, celery, celerybeat, nginx, django"
            exit 1
            ;;
    esac
}

# Restart: Reiniciar servicios específicos
restart() {
    SERVICE=${1:-all}
    
    print_info "Reiniciando $SERVICE..."
    sudo supervisorctl restart byteneko_$SERVICE
    print_success "$SERVICE reiniciado!"
}

# Shell: Abrir shell de Django
shell() {
    cd $PROJECT_DIR
    source $VENV_DIR/bin/activate
    $MANAGE shell
}

# DBShell: Abrir shell de PostgreSQL
dbshell() {
    cd $PROJECT_DIR
    source $VENV_DIR/bin/activate
    $MANAGE dbshell
}

# Migrate: Ejecutar migraciones
migrate() {
    cd $PROJECT_DIR
    source $VENV_DIR/bin/activate
    $MANAGE migrate
    print_success "Migraciones completadas!"
}

# Collectstatic: Recopilar archivos estáticos
collectstatic() {
    cd $PROJECT_DIR
    source $VENV_DIR/bin/activate
    $MANAGE collectstatic --noinput
    print_success "Archivos estáticos recopilados!"
}

# Backup: Crear backup de base de datos
backup_db() {
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    BACKUP_DIR="$PROJECT_DIR/backups"
    BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.sql"
    
    mkdir -p $BACKUP_DIR
    
    print_info "Creando backup en $BACKUP_FILE..."
    sudo -u postgres pg_dump byteneko_production > $BACKUP_FILE
    
    # Comprimir backup
    gzip $BACKUP_FILE
    
    print_success "Backup creado: ${BACKUP_FILE}.gz"
    
    # Limpiar backups antiguos (mantener últimos 7 días)
    find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
    print_info "Backups antiguos eliminados"
}

# Restore: Restaurar backup de base de datos
restore_db() {
    if [ -z "$1" ]; then
        print_error "Uso: $0 restore_db <archivo_backup.sql.gz>"
        exit 1
    fi
    
    BACKUP_FILE=$1
    
    if [ ! -f "$BACKUP_FILE" ]; then
        print_error "Archivo no encontrado: $BACKUP_FILE"
        exit 1
    fi
    
    print_warning "¡ATENCIÓN! Esto sobrescribirá la base de datos actual."
    read -p "¿Estás seguro? (yes/no): " -r
    
    if [[ ! $REPLY =~ ^yes$ ]]; then
        print_info "Operación cancelada"
        exit 0
    fi
    
    # Descomprimir si es necesario
    if [[ $BACKUP_FILE == *.gz ]]; then
        print_info "Descomprimiendo backup..."
        gunzip -k $BACKUP_FILE
        BACKUP_FILE="${BACKUP_FILE%.gz}"
    fi
    
    print_info "Restaurando base de datos..."
    sudo -u postgres psql byteneko_production < $BACKUP_FILE
    
    print_success "Base de datos restaurada!"
}

# Check: Ejecutar checks de Django
check() {
    cd $PROJECT_DIR
    source $VENV_DIR/bin/activate
    $MANAGE check --deploy
}

# Celery Status: Ver estado de workers de Celery
celery_status() {
    cd $PROJECT_DIR
    source $VENV_DIR/bin/activate
    $CELERY -A byteneko inspect active
}

# Flush Cache: Limpiar caché de Redis
flush_cache() {
    print_warning "Esto eliminará todos los datos en caché."
    read -p "¿Continuar? (yes/no): " -r
    
    if [[ $REPLY =~ ^yes$ ]]; then
        redis-cli -n 1 FLUSHDB
        print_success "Caché limpiada!"
    else
        print_info "Operación cancelada"
    fi
}

# Update Dependencies: Actualizar dependencias de Python
update_deps() {
    cd $PROJECT_DIR
    source $VENV_DIR/bin/activate
    
    print_info "Actualizando pip..."
    $PIP install --upgrade pip
    
    print_info "Actualizando dependencias..."
    $PIP install -r requirements.txt --upgrade
    
    print_success "Dependencias actualizadas!"
}

# Help: Mostrar ayuda
show_help() {
    cat << EOF
Byteneko Deployment Manager
===========================

Uso: $0 <comando> [argumentos]

Comandos disponibles:

  deploy              Actualizar código, ejecutar migraciones y reiniciar servicios
  status              Ver estado de todos los servicios
  logs <servicio>     Ver logs en tiempo real (gunicorn|celery|celerybeat|nginx|django)
  restart <servicio>  Reiniciar servicio específico (gunicorn|celery|celerybeat|all)
  
  shell               Abrir shell de Django
  dbshell             Abrir shell de PostgreSQL
  migrate             Ejecutar migraciones de base de datos
  collectstatic       Recopilar archivos estáticos
  
  backup_db           Crear backup de base de datos
  restore_db <file>   Restaurar backup de base de datos
  
  check               Ejecutar checks de deployment de Django
  celery_status       Ver estado de workers de Celery
  flush_cache         Limpiar caché de Redis
  update_deps         Actualizar dependencias de Python
  
  help                Mostrar esta ayuda

Ejemplos:
  $0 deploy                    # Deployment completo
  $0 logs gunicorn             # Ver logs de Gunicorn
  $0 restart celery            # Reiniciar workers de Celery
  $0 backup_db                 # Crear backup
  $0 restore_db backup.sql.gz  # Restaurar backup

EOF
}

# =============================================================================
# MAIN
# =============================================================================

case "${1:-help}" in
    deploy)
        deploy
        ;;
    status)
        status
        ;;
    logs)
        logs "$2"
        ;;
    restart)
        restart "$2"
        ;;
    shell)
        shell
        ;;
    dbshell)
        dbshell
        ;;
    migrate)
        migrate
        ;;
    collectstatic)
        collectstatic
        ;;
    backup_db)
        backup_db
        ;;
    restore_db)
        restore_db "$2"
        ;;
    check)
        check
        ;;
    celery_status)
        celery_status
        ;;
    flush_cache)
        flush_cache
        ;;
    update_deps)
        update_deps
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Comando no reconocido: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
