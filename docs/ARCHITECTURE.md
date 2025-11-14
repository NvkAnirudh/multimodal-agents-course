# Recollect Architecture & Tech Stack

## 📋 Complete Technology Stack

### Frontend Layer

| Technology | Version | Purpose | Scalability Rating | Notes |
|------------|---------|---------|-------------------|-------|
| **React** | 18.3.1 | UI Framework | ⭐⭐⭐⭐⭐ Excellent | Industry standard, scales well with code-splitting |
| **TypeScript** | 5.5.3 | Type Safety | ⭐⭐⭐⭐⭐ Excellent | Better maintainability at scale |
| **Vite** | 5.4.1 | Build Tool | ⭐⭐⭐⭐⭐ Excellent | Fast HMR, optimized production builds |
| **Tailwind CSS** | Latest | Styling | ⭐⭐⭐⭐⭐ Excellent | Minimal CSS bundle, utility-first |
| **TanStack Query** | Latest | State Management | ⭐⭐⭐⭐⭐ Excellent | Built-in caching, request deduplication |
| **Shadcn/ui** | Latest | Component Library | ⭐⭐⭐⭐ Good | Composable, customizable components |

**Frontend Scalability Verdict:** ✅ **Excellent** - Modern stack, well-suited for production

---

### API Layer

| Technology | Version | Purpose | Scalability Rating | Notes |
|------------|---------|---------|-------------------|-------|
| **FastAPI** | 0.115.13+ | Web Framework | ⭐⭐⭐⭐ Good | Async support, but single-process by default |
| **Uvicorn** | Latest | ASGI Server | ⭐⭐⭐ Moderate | Single worker, needs Gunicorn for multi-process |
| **Pydantic** | 2.x | Data Validation | ⭐⭐⭐⭐⭐ Excellent | Type-safe, performant validation |
| **Instructor** | Latest | Structured Outputs | ⭐⭐⭐⭐ Good | Adds reliability to LLM outputs |

**API Scalability Concerns:**
- ⚠️ **Single Worker Uvicorn** - Not production-ready for concurrent users
- ⚠️ **No Load Balancing** - Single instance
- ⚠️ **Synchronous Bottlenecks** - Some blocking operations

**Recommendations:**
```yaml
# Use Gunicorn with multiple workers
gunicorn recollect_api.api:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8080 \
  --timeout 120 \
  --keep-alive 5
```

---

### LLM Providers

| Technology | Purpose | Scalability Rating | Notes |
|------------|---------|-------------------|-------|
| **Groq** | LLM Inference (Llama 4) | ⭐⭐⭐⭐⭐ Excellent | Ultra-fast inference (500+ tok/s), rate limits: 30 req/min |
| **OpenAI API** | Embeddings, Whisper, Vision | ⭐⭐⭐⭐⭐ Excellent | Enterprise-grade, 10K RPM+ on paid tiers |

**LLM Scalability Verdict:** ✅ **Excellent** - API-based, managed infrastructure

**Cost Considerations:**
- **Groq Free Tier:** 500K tokens/day (sufficient for MVP)
- **OpenAI Costs:** ~$0.10/1K tokens (GPT-4o-mini), $0.006/min (Whisper)
- **Recommendation:** Implement caching for repeated queries

---

### MCP Server

| Technology | Version | Purpose | Scalability Rating | Notes |
|------------|---------|---------|-------------------|-------|
| **FastMCP** | 2.5.2+ | MCP Framework | ⭐⭐⭐ Moderate | New framework, limited production usage |
| **Pixeltable** | 0.4.1+ | Multimodal Processing | ⭐⭐⭐ Moderate | SQLite backend limits concurrency |

**MCP Scalability Concerns:**
- ⚠️ **Pixeltable SQLite** - Single-writer limitation
- ⚠️ **No Horizontal Scaling** - Stateful processing
- ⚠️ **Memory Intensive** - Video processing requires significant RAM

**Recommendations:**
```python
# For production, switch Pixeltable to PostgreSQL backend
import pixeltable as pxt

# Configure PostgreSQL backend
pxt.set_db_url("postgresql://user:pass@postgres:5432/recollect")
```

---

### Memory & Persistence (NEW)

| Technology | Version | Purpose | Scalability Rating | Notes |
|------------|---------|---------|-------------------|-------|
| **Redis** | 7.x | Hot Memory Storage | ⭐⭐⭐⭐⭐ Excellent | 100K+ ops/sec, horizontal scaling with Redis Cluster |
| **PostgreSQL** | 16.x | Cold Archive Storage | ⭐⭐⭐⭐⭐ Excellent | Battle-tested, multi-region replication |
| **Pixeltable** | 0.4.1+ | Video Metadata Only | ⭐⭐⭐ Moderate | Keep for multimodal processing, not chat history |

**Memory Architecture:**
```
┌─────────────────────────────────────────────────────────┐
│  Memory Strategy                                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Redis (In-Memory)                                      │
│  ├─ Active Conversations (last 7 days)                 │
│  ├─ Session State                                       │
│  ├─ Rate Limiting Counters                             │
│  └─ Background Task Queue                              │
│                                                          │
│  PostgreSQL (Persistent)                                │
│  ├─ Conversation Archives (>7 days)                    │
│  ├─ User Profiles & Authentication                     │
│  ├─ Video Metadata (source, author, tags)              │
│  ├─ Analytics & Usage Statistics                       │
│  └─ Audit Logs                                          │
│                                                          │
│  Pixeltable (Video Processing)                          │
│  ├─ Video Tables (frames, audio chunks)                │
│  ├─ Embedding Indexes (CLIP, text)                     │
│  └─ Similarity Search                                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**Memory Scalability Verdict:** ✅ **Excellent** - Redis scales to millions of users

---

### Video Processing

| Technology | Version | Purpose | Scalability Rating | Notes |
|------------|---------|---------|-------------------|-------|
| **MoviePy** | 2.2.1+ | Video Manipulation | ⭐⭐⭐ Moderate | CPU-intensive, synchronous processing |
| **yt-dlp** | Latest | Video Downloader | ⭐⭐⭐⭐ Good | Handles rate limiting, robust |
| **OpenCV** | Latest | Frame Extraction | ⭐⭐⭐⭐ Good | Efficient, but CPU-bound |
| **PIL/Pillow** | Latest | Image Processing | ⭐⭐⭐⭐ Good | Lightweight, fast |

**Video Processing Concerns:**
- ⚠️ **CPU-Intensive** - Video encoding/decoding is blocking
- ⚠️ **Memory Spikes** - Large videos can cause OOM
- ⚠️ **No Parallelization** - Current implementation is sequential

**Recommendations:**
```python
# Use Celery for async video processing
from celery import Celery

celery_app = Celery('recollect', broker='redis://redis:6379/0')

@celery_app.task
def process_video_async(video_path: str):
    """Process video in background worker"""
    # Video processing logic here
    pass
```

---

### Observability & Monitoring

| Technology | Version | Purpose | Scalability Rating | Notes |
|------------|---------|---------|-------------------|-------|
| **Opik** | 1.7.36+ | LLM Observability | ⭐⭐⭐⭐ Good | Prompt versioning, tracing |
| **Loguru** | Latest | Structured Logging | ⭐⭐⭐⭐⭐ Excellent | Fast, rotating file logs |

**Observability Verdict:** ✅ **Good** - Adequate for production

**Additional Recommendations:**
- Add **Prometheus** for metrics
- Add **Grafana** for dashboards
- Add **Sentry** for error tracking

---

### Infrastructure & Deployment

| Technology | Version | Purpose | Scalability Rating | Notes |
|------------|---------|---------|-------------------|-------|
| **Docker** | Latest | Containerization | ⭐⭐⭐⭐⭐ Excellent | Standard for microservices |
| **Docker Compose** | Latest | Orchestration (Dev) | ⭐⭐ Poor | Not for production |
| **Nginx** | Latest | Reverse Proxy | ⭐⭐⭐⭐⭐ Excellent | Battle-tested, high performance |

**Infrastructure Concerns:**
- ❌ **Docker Compose** - Not production-grade, single-host only
- ⚠️ **No Auto-scaling** - Manual scaling required
- ⚠️ **No Health Checks** - No automatic recovery

**Production Recommendations:**

#### Option 1: Kubernetes (Best for Scale)
```yaml
# Horizontal scaling, auto-healing, load balancing
apiVersion: apps/v1
kind: Deployment
metadata:
  name: recollect-api
spec:
  replicas: 3  # Auto-scale based on CPU/memory
  template:
    spec:
      containers:
      - name: api
        image: recollect-api:latest
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
```

#### Option 2: AWS ECS/Fargate (Managed Containers)
- Auto-scaling groups
- Load balancer integration
- Managed infrastructure

#### Option 3: Railway/Render/Fly.io (Easiest)
- Zero DevOps
- Auto-scaling included
- Great for MVPs

---

## 🔍 Scalability Analysis by Component

### Critical Bottlenecks (Needs Immediate Attention)

| Component | Current State | Issue | Fix |
|-----------|--------------|-------|-----|
| **FastAPI Worker** | Single Uvicorn worker | 1 request at a time | Use Gunicorn with 4-8 workers |
| **Pixeltable Memory** | SQLite backend | Write locks, no concurrency | Switch to PostgreSQL |
| **Video Processing** | Synchronous blocking | API hangs during processing | Move to Celery workers |
| **Docker Compose** | Single-host deployment | No redundancy | Move to Kubernetes/ECS |

### Components That Scale Well

| Component | Why It Scales | Max Capacity |
|-----------|--------------|-------------|
| **Redis** | In-memory, horizontal scaling | Millions of users |
| **PostgreSQL** | MVCC, read replicas | 10K+ concurrent connections |
| **React Frontend** | Static CDN deployment | Unlimited |
| **Groq/OpenAI APIs** | Managed infrastructure | Rate limits only |

---

## 🚀 Recommended Production Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Load Balancer (Nginx/AWS ALB)                           │
│  ├─ SSL Termination                                      │
│  ├─ Rate Limiting                                        │
│  └─ DDoS Protection                                      │
└───────────────────┬──────────────────────────────────────┘
                    │
        ┌───────────┴────────────┐
        │                        │
        ▼                        ▼
┌───────────────┐        ┌───────────────┐
│  API Pods     │        │  API Pods     │  (Horizontal Scaling)
│  (3+ replicas)│        │  (3+ replicas)│
└───────┬───────┘        └───────┬───────┘
        │                        │
        └───────────┬────────────┘
                    ▼
        ┌────────────────────────┐
        │  Redis Cluster         │
        │  (Master + 2 Replicas) │
        └────────────────────────┘
                    │
                    ▼
        ┌────────────────────────┐
        │  PostgreSQL            │
        │  (Primary + Replicas)  │
        └────────────────────────┘
                    │
                    ▼
        ┌────────────────────────┐
        │  Celery Workers        │
        │  (Video Processing)    │
        │  (4+ workers)          │
        └────────────────────────┘
                    │
                    ▼
        ┌────────────────────────┐
        │  S3/Object Storage     │
        │  (Video Files)         │
        └────────────────────────┘
```

---

## 💰 Estimated Infrastructure Costs (Monthly)

### MVP (100 users, 1K videos/month)
- **Railway/Render:** $20-50/month
- **Redis Cloud:** $0 (free tier)
- **Supabase (Postgres):** $0 (free tier)
- **OpenAI API:** $50-100
- **Groq API:** $0 (free tier)
- **Total:** ~$70-150/month

### Production (10K users, 50K videos/month)
- **AWS ECS/Fargate:** $150-300/month
- **Redis Cluster:** $50-100/month
- **RDS PostgreSQL:** $100-200/month
- **S3 Storage:** $50-100/month
- **OpenAI API:** $500-1000/month
- **Groq API:** $200-500/month
- **Total:** ~$1,050-2,200/month

### Enterprise (100K+ users)
- **Kubernetes (EKS/GKE):** $500-1000/month
- **Redis Cluster:** $200-500/month
- **PostgreSQL:** $500-1000/month
- **CDN (CloudFront):** $100-300/month
- **LLM APIs:** $5,000-10,000/month
- **Total:** ~$6,300-12,800/month

---

## ✅ Updated Tech Stack Summary

### Keep As-Is ✅
- React + TypeScript (Frontend)
- FastAPI (with Gunicorn)
- Groq + OpenAI APIs
- Pixeltable (for video processing only)
- FastMCP (MCP protocol)
- Opik (observability)

### Replace/Add 🔄
- ✅ **Add Redis** for memory
- ✅ **Add PostgreSQL** for archives & metadata
- ✅ **Add Celery** for async video processing
- ✅ **Add Gunicorn** for multi-worker API
- 🔄 **Replace Docker Compose** with Kubernetes (production)
- 🔄 **Add S3/MinIO** for video storage (production)

### Optional Enhancements 💡
- **Prometheus + Grafana** for metrics
- **Sentry** for error tracking
- **Elasticsearch** for full-text search
- **RabbitMQ** for complex task queues
- **Vector DB (Qdrant/Pinecone)** for semantic search

---

## 📊 Scalability Scorecard

| Layer | Current | With Updates | Max Users |
|-------|---------|--------------|-----------|
| Frontend | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Unlimited (CDN) |
| API | ⭐⭐ | ⭐⭐⭐⭐⭐ | 100K+ (Kubernetes) |
| Memory | ⭐⭐ | ⭐⭐⭐⭐⭐ | Millions (Redis Cluster) |
| Video Processing | ⭐⭐ | ⭐⭐⭐⭐ | 10K+ concurrent jobs |
| Database | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 100K+ (PostgreSQL) |

**Overall:** Current = ⭐⭐⭐ | With Updates = ⭐⭐⭐⭐⭐

