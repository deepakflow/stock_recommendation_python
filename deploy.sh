#!/bin/bash

# Stock Recommendation Agent Deployment Script with Google Auth and Supabase

echo "🚀 Deploying Stock Recommendation Agent with Google Auth and Supabase..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "�� Creating .env file from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  Please configure the following in your .env file:"
    echo "   - GOOGLE_CLIENT_ID (from Google Cloud Console)"
    echo "   - SUPABASE_URL (from your Supabase project)"
    echo "   - SUPABASE_SERVICE_ROLE_KEY (from Supabase dashboard)"
    echo "   - JWT_SECRET (generate a secure random key)"
    echo "   - OPENAI_API_KEY"
    echo "   - BRIGHT_DATA_API_TOKEN"
    echo ""
    echo "�� Setup Instructions:"
    echo "1. Create a Google Cloud project and enable Google+ API"
    echo "2. Create OAuth 2.0 credentials and get the Client ID"
    echo "3. Create a Supabase project and get the URL and keys"
    echo "4. Run the SQL schema in your Supabase SQL editor"
    echo "5. Update the frontend/index.html with your Google Client ID"
    echo ""
    read -p "Press Enter after configuring .env file..."
fi

# Create logs directory
mkdir -p logs

# Build and start the application
echo "🔨 Building and starting the application..."
docker-compose up --build -d

# Wait for the application to start
echo "⏳ Waiting for the application to start..."
sleep 10

# Check if the application is running
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Application is running successfully!"
    echo "🌐 API is available at: http://localhost:8000"
    echo "�� API documentation: http://localhost:8000/docs"
    echo "�� Health check: http://localhost:8000/health"
    echo ""
    echo "🎯 Features:"
    echo "   - Google Authentication"
    echo "   - Supabase Database"
    echo "   - Daily Query Limits (3 per user)"
    echo "   - JWT Token Security"
    echo ""
    echo "🌐 To test the application:"
    echo "   1. Open frontend/index.html in your browser"
    echo "   2. Sign in with Google"
    echo "   3. Start chatting with the stock recommendation agent"
    echo "   4. Each user gets 3 queries per day"
else
    echo "❌ Application failed to start. Check the logs:"
    docker-compose logs
fi

echo ""
echo "�� Useful commands:"
echo "   - View logs: docker-compose logs -f"
echo "   - Stop application: docker-compose down"
echo "   - Restart application: docker-compose restart"
echo ""
echo "📊 Monitor usage in Supabase dashboard"
