#!/bin/bash

# Medical Terminology Standardization Engine - Stop Script
# This script stops the entire application stack and cleans up resources

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
        print_error "Docker is not running. Cannot stop services."
        exit 1
    fi
}

# Function to check if Docker Compose is available
check_docker_compose() {
    if ! command -v docker-compose >/dev/null 2>&1; then
        print_error "Docker Compose is not installed."
        exit 1
    fi
}

# Function to stop services gracefully
stop_services() {
    print_status "Stopping Docker services gracefully..."
    
    # Check if any services are running
    if ! docker-compose ps -q | xargs docker inspect -f '{{.State.Status}}' 2>/dev/null | grep -q "running"; then
        print_warning "No services appear to be running."
        return 0
    fi
    
    # Stop services with timeout
    docker-compose down --timeout 30
    
    print_success "All services stopped successfully"
}

# Function to clean up resources (optional)
cleanup_resources() {
    local cleanup_level="$1"
    
    case "$cleanup_level" in
        "full")
            print_status "Performing full cleanup (removing volumes and images)..."
            docker-compose down -v --rmi all --remove-orphans
            print_success "Full cleanup completed"
            ;;
        "volumes")
            print_status "Removing Docker volumes (data will be lost)..."
            docker-compose down -v --remove-orphans
            print_success "Volumes removed"
            ;;
        "basic")
            print_status "Basic cleanup (removing containers only)..."
            docker-compose down --remove-orphans
            print_success "Basic cleanup completed"
            ;;
        *)
            # Default: just stop services
            stop_services
            ;;
    esac
}

# Function to show cleanup options
show_cleanup_options() {
    echo ""
    echo "🧹 Cleanup Options:"
    echo "   ./stop.sh          - Stop services only (preserve data)"
    echo "   ./stop.sh basic    - Stop and remove containers"
    echo "   ./stop.sh volumes  - Stop and remove containers + volumes (⚠️  data loss)"
    echo "   ./stop.sh full     - Stop and remove everything (⚠️  complete reset)"
    echo ""
}

# Function to confirm destructive operations
confirm_destructive() {
    local operation="$1"
    echo ""
    print_warning "⚠️  WARNING: This will $operation"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Operation cancelled."
        exit 0
    fi
}

# Function to show current status
show_status() {
    echo ""
    echo "📊 Current Service Status:"
    if docker-compose ps -q >/dev/null 2>&1; then
        docker-compose ps --format "table {{.Name}}\t{{.State}}\t{{.Ports}}"
    else
        print_status "No services found or Docker Compose not available"
    fi
    echo ""
}

# Main execution
main() {
    local cleanup_level="${1:-default}"
    
    echo "Stopping Medical Terminology Standardization Engine..."
    echo "========================================"
    
    # Pre-flight checks
    print_status "Running pre-flight checks..."
    check_docker
    check_docker_compose
    
    # Show current status
    show_status
    
    # Handle different cleanup levels
    case "$cleanup_level" in
        "help"|"-h"|"--help")
            echo "Usage: ./stop.sh [cleanup_level]"
            show_cleanup_options
            exit 0
            ;;
        "full")
            confirm_destructive "remove ALL containers, volumes, and images"
            cleanup_resources "full"
            ;;
        "volumes")
            confirm_destructive "remove containers and volumes (ALL DATA WILL BE LOST)"
            cleanup_resources "volumes"
            ;;
        "basic")
            cleanup_resources "basic"
            ;;
        "status")
            show_status
            exit 0
            ;;
        *)
            # Default: just stop services
            stop_services
            ;;
    esac
    
    # Show final status
    print_status "Final status check..."
    show_status
    
    print_success "Medical Terminology Standardization Engine stopped successfully!"
    
    # Show restart information
    echo ""
    echo "🚀 To restart the application, run: ./start.sh"
    
    if [ "$cleanup_level" != "default" ]; then
        show_cleanup_options
    fi
}

# Handle script interruption
trap 'print_error "Stop operation interrupted."; exit 1' INT

# Run main function
main "$@"