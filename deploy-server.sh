#!/bin/bash

# Stock Recommendation Agent - Server Deployment Script
# Optimized for 2GB RAM Ubuntu server

echo "🚀 Deploying Stock Recommendation Agent on Ubuntu Server..."

# Configuration
APP_NAME="stock-recommendation-agent"
APP_DIR="/var/www/$APP_NAME"
SERVICE_NAME="stock-recommendation"
NGINX_SITE="stock-api"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Check system resources
print_status "Checking system resources..."
TOTAL_RAM=$(free -m | awk 'NR==2{printf "%.0f", $2}')
if [ "$TOTAL_RAM" -lt 1800 ]; then
    print_warning "Server has less than 2GB RAM. Performance may be affected."
fi

# Install system dependencies
print_status "Installing system dependencies..."
apt-get update
apt-get install -y python3.11 python3.11-venv python3.11-dev build-essential curl nginx certbot python3-certbot-nginx

# Create application directory
print_status "Setting up application directory..."
mkdir -p $APP_DIR
chown www-data:www-data $APP_DIR

# Copy application files
print_status "Copying application files..."
cp -r . $APP_DIR/
chown -R www-data:www-data $APP_DIR

# Create virtual environment
print_status "Setting up Python virtual environment..."
cd $APP_DIR
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
print_status "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create environment file if it doesn't exist
if [ ! -f $APP_DIR/.env ]; then
    print_status "Creating environment file..."
    cp .env.example $APP_DIR/.env
    chown www-data:www-data $APP_DIR/.env
    print_warning "Please edit $APP_DIR/.env with your actual configuration"
fi

# Setup systemd service
print_status "Setting up systemd service..."
cp stock-recommendation.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable $SERVICE_NAME

# Setup Nginx
print_status "Setting up Nginx configuration..."
cp nginx-stock-api.conf /etc/nginx/sites-available/$NGINX_SITE
ln -sf /etc/nginx/sites-available/$NGINX_SITE /etc/nginx/sites-enabled/

# Test Nginx configuration
nginx -t
if [ $? -eq 0 ]; then
    print_status "Nginx configuration is valid"
else
    print_error "Nginx configuration is invalid"
    exit 1
fi

# Start the application
print_status "Starting the application..."
systemctl start $SERVICE_NAME
systemctl status $SERVICE_NAME

# Reload Nginx
print_status "Reloading Nginx..."
systemctl reload nginx

# Wait for application to start
print_status "Waiting for application to start..."
sleep 10

# Check if application is running
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    print_status "✅ Application is running successfully!"
    print_status "🌐 API is available at: http://localhost:8000"
    print_status "�� Health check: http://localhost:8000/health"
    print_status "�� API documentation: http://localhost:8000/docs"
else
    print_error "❌ Application failed to start"
    print_status "Checking logs..."
    journalctl -u $SERVICE_NAME -n 20
    exit 1
fi

# Setup SSL certificate (optional)
read -p "Do you want to setup SSL certificate with Let's Encrypt? (y/n): " setup_ssl
if [ "$setup_ssl" = "y" ]; then
    read -p "Enter your domain name: " domain_name
    print_status "Setting up SSL certificate for $domain_name..."
    certbot --nginx -d $domain_name --non-interactive --agree-tos --email admin@$domain_name
fi

print_status "🎉 Deployment completed!"
print_status ""
print_status "�� Useful commands:"
print_status "   - View logs: journalctl -u $SERVICE_NAME -f"
print_status "   - Restart service: systemctl restart $SERVICE_NAME"
print_status "   - Check status: systemctl status $SERVICE_NAME"
print_status "   - View Nginx logs: tail -f /var/log/nginx/access.log"
print_status ""
print_status "🔧 Configuration files:"
print_status "   - Environment: $APP_DIR/.env"
print_status "   - Nginx config: /etc/nginx/sites-available/$NGINX_SITE"
print_status "   - Service file: /etc/systemd/system/$SERVICE_NAME"
print_status ""
print_status "📊 Monitor memory usage:"
print_status "   - htop"
print_status "   - free -h"
print_status "   - journalctl -u $SERVICE_NAME | grep 'Memory usage'"
