#!/bin/bash

# Medical Terminology Standardization Engine - Start Script
# This script starts the entire application stack using Docker Compose

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
}

# Function to check if Docker Compose is available
check_docker_compose() {
    if ! command -v docker-compose >/dev/null 2>&1; then
        print_error "Docker Compose is not installed. Please install Docker Compose and try again."
        exit 1
    fi
}

# Function to wait for services to be healthy
wait_for_services() {
    print_status "Waiting for services to start..."
    
    # Redis no longer needed - removed with Celery
    
    # Wait for Backend API
    print_status "Checking Backend API..."
    timeout=120
    while [ $timeout -gt 0 ]; do
        if curl -s http://localhost:8000/health >/dev/null 2>&1; then
            print_success "Backend API is responding"
            break
        fi
        sleep 5
        timeout=$((timeout - 5))
    done
    
    if [ $timeout -le 0 ]; then
        print_warning "Backend API health check timed out, but continuing..."
    fi
    
    # Wait for Frontend
    print_status "Checking Frontend..."
    timeout=60
    while [ $timeout -gt 0 ]; do
        if curl -s http://localhost:3000 >/dev/null 2>&1; then
            print_success "Frontend is responding"
            break
        fi
        sleep 3
        timeout=$((timeout - 3))
    done
    
    if [ $timeout -le 0 ]; then
        print_warning "Frontend health check timed out, but continuing..."
    fi
}

# Function to open browser
open_browser() {
    local url="$1"
    
    # Check operating system and open browser accordingly
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        open "$url"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$url"
        elif command -v gnome-open >/dev/null 2>&1; then
            gnome-open "$url"
        elif command -v firefox >/dev/null 2>&1; then
            firefox "$url"
        elif command -v chromium-browser >/dev/null 2>&1; then
            chromium-browser "$url"
        elif command -v google-chrome >/dev/null 2>&1; then
            google-chrome "$url"
        else
            print_warning "Could not detect browser to open automatically"
        fi
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        # Windows
        start "$url"
    else
        print_warning "Unknown OS type: $OSTYPE - cannot open browser automatically"
    fi
}

# Function to display service URLs
show_urls() {
    echo ""
    echo "Medical Terminology Standardization Engine is now running!"
    echo ""
    echo "📱 Access Points:"
    echo "   • Web Interface:      http://localhost:3000"
    echo "   • API Documentation:  http://localhost:8000/docs"
    echo "   • API Health Check:   http://localhost:8000/health"
    echo ""
    echo "📊 Service Status:"
    docker-compose ps --format "table {{.Name}}\t{{.State}}\t{{.Ports}}"
    echo ""
    echo "📋 Useful commands:"
    echo "   • View logs:       docker-compose logs -f"
    echo "   • Stop services:   ./stop.sh"
    echo "   • Rebuild:         docker-compose build --no-cache"
    echo "   • Shell into API:  docker-compose exec api bash"
    echo "   • Run tests:       docker-compose exec api pytest"
    echo "   • Reinit database: ./start.sh --init-db"
    echo ""
}

# Main execution
main() {
    echo "Starting Medical Terminology Standardization Engine..."
    echo "========================================"
    
    # Pre-flight checks
    print_status "Running pre-flight checks..."
    check_docker
    check_docker_compose
    
    # Check if services are already running
    if docker-compose ps -q | xargs docker inspect -f '{{.State.Status}}' 2>/dev/null | grep -q "running"; then
        print_warning "Some services are already running. Stopping them first..."
        docker-compose down
        sleep 2
    fi
    
    # Start services
    print_status "Starting Docker services..."
    print_status "This may take a few minutes on first run (downloading images)..."
    
    # Pull latest images
    print_status "Pulling latest Docker images..."
    docker-compose pull
    
    # Build services if needed
    print_status "Building services..."
    docker-compose build
    
    # Initialize databases if this is first run or if requested
    if [ "$1" == "--init-db" ] || [ ! -f "data/terminology/.initialized" ]; then
        print_status "Initializing terminology databases..."
        docker-compose run --rm api python scripts/setup_terminology_db.py
        touch data/terminology/.initialized
        print_success "Databases initialized"
    fi
    
    # Start services in detached mode
    print_status "Starting all services..."
    if ! docker-compose up -d; then
        print_error "Failed to start services. Please check the logs:"
        print_status "docker-compose logs"
        exit 1
    fi
    
    # Wait for services to be ready
    wait_for_services
    
    # Show service information
    show_urls
    
    # Open browser to the web interface
    print_status "Opening web interface in browser..."
    open_browser "http://localhost:3000"
    
    print_success "Startup complete! The application is ready to use."
}

# Handle script interruption
trap 'print_error "Startup interrupted. Run ./stop.sh to clean up if needed."; exit 1' INT

# Run main function
main "$@"