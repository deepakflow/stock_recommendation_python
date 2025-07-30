from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
import jwt
import time
import os
from typing import Optional, List
import asyncio
import logging
from datetime import datetime, timedelta
import uvicorn
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import httpx
from supabase import create_client, Client
from google.oauth2 import id_token
from google.auth.transport import requests

# Import your existing agent code
from main import run_agent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
JWT_SECRET = os.getenv("JWT_SECRET", "your-jwt-secret-change-this")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Security scheme
security = HTTPBearer()

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="Your message to the stock recommendation agent")

class ChatResponse(BaseModel):
    response: str
    timestamp: datetime
    user_id: str
    message_id: str
    queries_remaining: int

class GoogleAuthRequest(BaseModel):
    id_token: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: str
    name: str
    queries_remaining: int

class UserProfile(BaseModel):
    user_id: str
    email: str
    name: str
    queries_used_today: int
    queries_remaining: int
    last_query_date: Optional[datetime]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Stock Recommendation API with Google Auth and Supabase...")
    yield
    # Shutdown
    logger.info("Shutting down Stock Recommendation API...")

# Create FastAPI app
app = FastAPI(
    title="Stock Recommendation Agent API",
    description="A secure API for interacting with AI-powered stock recommendation agents using Google Auth and Supabase",
    version="1.0.0",
    lifespan=lifespan
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://yourdomain.com"],  # Configure for your frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add memory optimization
import gc
import psutil

# Memory monitoring
def log_memory_usage():
    process = psutil.Process()
    memory_info = process.memory_info()
    logger.info(f"Memory usage: {memory_info.rss / 1024 / 1024:.2f} MB")

@app.middleware("http")
async def memory_monitoring_middleware(request: Request, call_next):
    log_memory_usage()
    response = await call_next(request)
    # Force garbage collection after each request
    gc.collect()
    return response

def verify_google_token(id_token_str: str):
    """Verify Google ID token and return user info"""
    try:
        idinfo = id_token.verify_oauth2_token(
            id_token_str,
            requests.Request(),
            GOOGLE_CLIENT_ID
        )

        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')

        return {
            'user_id': idinfo['sub'],
            'email': idinfo['email'],
            'name': idinfo.get('name', ''),
            'picture': idinfo.get('picture', '')
        }
    except Exception as e:
        logger.error(f"Google token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token"
        )

def create_jwt_token(user_id: str, email: str):
    """Create JWT token for authenticated user"""
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and return user info"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

async def get_or_create_user(user_info: dict):
    """Get or create user in Supabase"""
    try:
        # Check if user exists
        response = supabase.table('users').select('*').eq('user_id', user_info['user_id']).execute()

        if response.data:
            user = response.data[0]
            return user
        else:
            # Create new user
            new_user = {
                'user_id': user_info['user_id'],
                'email': user_info['email'],
                'name': user_info['name'],
                'queries_used_today': 0,
                'last_query_date': None,
                'created_at': datetime.utcnow().isoformat()
            }

            response = supabase.table('users').insert(new_user).execute()
            return response.data[0]
    except Exception as e:
        logger.error(f"Error in get_or_create_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error"
        )

async def check_daily_limit(user_id: str):
    """Check and update daily query limit"""
    try:
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        user = response.data[0]

        today = datetime.utcnow().date()
        last_query_date = user.get('last_query_date')

        # Reset counter if it's a new day
        if last_query_date is None or datetime.fromisoformat(last_query_date).date() != today:
            await reset_daily_queries(user_id)
            return 3  # Fresh start for the day

        queries_used = user.get('queries_used_today', 0)
        if queries_used >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Daily query limit reached. You can make 3 queries per day."
            )

        return 3 - queries_used
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking daily limit: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error checking query limit"
        )

async def increment_query_count(user_id: str):
    """Increment the query count for today"""
    try:
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        user = response.data[0]

        current_count = user.get('queries_used_today', 0)
        new_count = current_count + 1

        supabase.table('users').update({
            'queries_used_today': new_count,
            'last_query_date': datetime.utcnow().isoformat()
        }).eq('user_id', user_id).execute()

    except Exception as e:
        logger.error(f"Error incrementing query count: {str(e)}")

async def reset_daily_queries(user_id: str):
    """Reset daily query count"""
    try:
        supabase.table('users').update({
            'queries_used_today': 0,
            'last_query_date': datetime.utcnow().isoformat()
        }).eq('user_id', user_id).execute()
    except Exception as e:
        logger.error(f"Error resetting daily queries: {str(e)}")

@app.post("/auth/google", response_model=AuthResponse)
@limiter.limit("10/minute")
async def google_auth(request: GoogleAuthRequest):
    """Authenticate with Google ID token"""
    try:
        # Verify Google token
        user_info = verify_google_token(request.id_token)

        # Get or create user in database
        user = await get_or_create_user(user_info)

        # Create JWT token
        access_token = create_jwt_token(user_info['user_id'], user_info['email'])

        # Check remaining queries
        queries_remaining = await check_daily_limit(user_info['user_id'])

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user_id=user_info['user_id'],
            email=user_info['email'],
            name=user_info['name'],
            queries_remaining=queries_remaining
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google auth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )

@app.get("/auth/profile", response_model=UserProfile)
async def get_user_profile(current_user: dict = Depends(verify_jwt_token)):
    """Get user profile and query usage"""
    try:
        response = supabase.table('users').select('*').eq('user_id', current_user['sub']).execute()
        user = response.data[0]

        queries_remaining = await check_daily_limit(current_user['sub'])

        return UserProfile(
            user_id=user['user_id'],
            email=user['email'],
            name=user['name'],
            queries_used_today=user.get('queries_used_today', 0),
            queries_remaining=queries_remaining,
            last_query_date=user.get('last_query_date')
        )

    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user profile"
        )

@app.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat_with_agent(
    request: ChatRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """Chat with the stock recommendation agent"""
    try:
        user_id = current_user['sub']

        # Check daily limit
        queries_remaining = await check_daily_limit(user_id)

        logger.info(f"User {user_id} sent message: {request.message[:50]}...")

        # Increment query count
        await increment_query_count(user_id)

        # Run the agent asynchronously
        await run_agent(request.message)

        # For now, return a simple response
        # You'll need to modify your run_agent function to return the response
        response_text = "Stock recommendation analysis completed. Check the logs for detailed output."

        return ChatResponse(
            response=response_text,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            message_id=f"msg_{int(time.time())}",
            queries_remaining=queries_remaining - 1
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request"
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Stock Recommendation Agent API",
        "version": "1.0.0",
        "features": [
            "Google Authentication",
            "Supabase Database",
            "Daily Query Limits (3 per user)",
            "JWT Token Security"
        ],
        "endpoints": {
            "auth": "/auth/google",
            "profile": "/auth/profile",
            "chat": "/chat",
            "health": "/health",
            "docs": "/docs"
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disable reload in production
        workers=1,     # Single worker for 2GB RAM
        loop="asyncio"
    )
