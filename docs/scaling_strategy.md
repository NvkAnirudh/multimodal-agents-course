# Scaling Strategy for Recollect AI

## Current Architecture Capacity

**Your Setup (from docker-compose.yml):**
- **1 Celery worker container**
- **4 concurrent workers** (concurrency=4)
- **2 CPU cores, 2GB RAM** (limits)
- **Processing time: ~206 seconds (3.4 minutes)** per video

**Math:**
```
Parallel videos: 4 (max)
Videos/hour: 4 × (60 min / 3.4 min) ≈ 70 videos/hour
Videos/day: 70 × 24 ≈ 1,680 videos/day
```

## 10K Users Overnight Scenario

**Conservative estimate:**
- Each user uploads **1 video on signup**
- Videos arrive over **24 hours** (not all at once)

**Load:**
```
10,000 videos / 24 hours = 417 videos/hour needed
Your capacity: 70 videos/hour
DEFICIT: -347 videos/hour ❌

Queue backlog: 10,000 videos / 70 per hour = 143 hours (6 days!)
```

**You're FUCKED** 🚨

---

## Realistic Viral Scenario

**More realistic:**
- 10K users over 24 hours
- 30% upload video immediately = 3,000 videos
- Peak traffic: First 4 hours (users excited, trending on Twitter)
  - 50% of uploads = 1,500 videos in 4 hours
  - **375 videos/hour during peak**

**Your system:**
```
Capacity: 70 videos/hour
Peak load: 375 videos/hour
OVERLOAD: 5.4x capacity exceeded
```

**What happens:**
- First hour: Queue builds up (305 videos waiting)
- Second hour: Queue grows to 610 videos
- Third hour: Queue at 915 videos
- Fourth hour: Queue at 1,220 videos

**Processing that backlog:**
```
1,220 videos / 70 per hour = 17.4 hours after peak ends
Total wait time for last user: 21+ hours ❌
```

Users will rage quit and roast you on Twitter.

---

## Bottlenecks in Your System

### 1. Celery Worker Bottleneck
```
Current: 1 container × 4 workers = 4 parallel videos
Problem: Each video takes 3.4 minutes
        - Frame extraction: ~30s
        - CLIP embeddings (45 frames): ~60s
        - Caption generation (45 frames): ~45s
        - Whisper transcription (13 chunks): ~60s
        - Storing embeddings: ~10s
```

### 2. External API Rate Limits

**OpenAI API:**
- **GPT-4o-mini** (captions): 500 requests/min (Tier 1)
- **Whisper** (transcription): 50 requests/min (Tier 1)
- **text-embedding-3-small**: 3,000 requests/min (Tier 1)

**Per video:**
- 45 caption requests (GPT-4o-mini)
- 13 transcription requests (Whisper)
- 58 embedding requests (captions + audio)

**At 4 parallel videos:**
```
GPT-4o-mini: 4 × 45 = 180 requests/min → OK (under 500)
Whisper: 4 × 13 = 52 requests/min → BOTTLENECK! (over 50)
Embeddings: 4 × 58 = 232 requests/min → OK (under 3000)
```

**You're already hitting Whisper rate limits at 4 workers!**

### 3. Pixeltable Embedded PostgreSQL
```
Current: Single embedded PostgreSQL instance
Problem: Not designed for high concurrency
        - Locks on table writes
        - No connection pooling
        - Embedded = single process bottleneck
```

### 4. Memory Constraints
```
Per video processing:
- Video in memory: ~20 MB
- 45 frames in memory: ~50 MB
- Audio processing: ~30 MB
- Model loading (CLIP, etc.): ~200 MB

4 parallel videos: 4 × 300 MB = 1.2 GB
Your limit: 2 GB → Only 800 MB headroom
If 5th video starts: OOM kill! 💥
```

---

## How Many Users Can You Actually Handle?

**Sustainable load (current setup):**
```
70 videos/hour × 24 hours = 1,680 videos/day

Assumptions:
- Each user uploads 2 videos/week on average
- 1,680 videos/day = 11,760 videos/week

Max users: 11,760 / 2 = 5,880 active users

WITH CURRENT SETUP: ~6,000 users MAX (steady state)
```

**For 10K users overnight, you'd need:**
```
Required capacity: 375 videos/hour (peak)
Current capacity: 70 videos/hour
Scale needed: 5.4x

Options:
1. Scale Celery workers: 5-6 containers × 4 workers = 20-24 parallel
2. Optimize processing time: 3.4 min → 1 min (via optimizations)
3. Use both: 3 containers × 8 workers + optimizations = handle 400/hour
```

---

## Scaling Options

### Option 1: Horizontal Scaling (Add More Workers)

**Quick fix (Docker Compose):**
```yaml
services:
  celery-worker:
    deploy:
      replicas: 6  # Scale to 6 containers
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

**New capacity:**
```
6 containers × 4 workers = 24 parallel videos
24 × (60 / 3.4) ≈ 424 videos/hour
Cost: 6x your current infra cost
```

**Problems:**
- Still hitting Whisper rate limits (24 × 13 = 312 requests/min > 50)
- Embedded Pixeltable can't handle 24 concurrent writes
- Need external PostgreSQL (you already have it!)

---

### Option 2: Optimize Processing (Reduce Time)

**Current: 3.4 minutes → Target: 1 minute**

**Optimizations:**
1. **Reduce frames: 45 → 20 frames**
   - Saves: 25 × (CLIP + caption) = ~60 seconds

2. **Batch API calls:**
   - OpenAI embeddings API supports batching (100 at once)
   - Instead of 58 individual calls → 1 batch call
   - Saves: ~40 seconds

3. **Parallel processing within video:**
   ```python
   # Current: Sequential
   frames → captions → embeddings → audio → transcribe

   # Optimized: Parallel
   ┌─ frames → captions → embeddings
   └─ audio → transcribe → embeddings
   (Run both branches simultaneously)

   Saves: ~50% time = 1.7 minutes
   ```

4. **Remove Pixeltable overhead:**
   - Direct vector DB writes (no Pixeltable)
   - Saves: ~30 seconds

**Total: 3.4 min → 1 min** ✅

**New capacity (same 4 workers):**
```
4 × (60 / 1) = 240 videos/hour
240 × 24 = 5,760 videos/day
```

---

### Option 3: Hybrid (Scale + Optimize)

**3 worker containers + optimizations:**
```
3 containers × 4 workers × (60 / 1 min) = 720 videos/hour
720 × 24 = 17,280 videos/day

Can handle: 10K users uploading 1-2 videos in first day ✅
Cost: 3x current infra (reasonable)
```

---

## Production-Ready Architecture for 10K+ Users

```
┌─────────────────────────────────────────────────────────┐
│ LOAD BALANCER (Nginx/CloudFlare)                       │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│ FastAPI (3-5 instances, auto-scaling)                  │
│ - Handle uploads → S3                                   │
│ - Enqueue processing jobs                              │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│ Redis/RabbitMQ (Managed service: AWS ElastiCache)      │
│ - Job queue (millions of jobs OK)                      │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│ Celery Workers (Auto-scaling: 3-20 instances)          │
│ - Base: 3 instances (12 workers)                       │
│ - Peak: 20 instances (80 workers)                      │
│ - Trigger: Queue depth > 100 → scale up                │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│ STORAGE                                                 │
├─────────────────────────────────────────────────────────┤
│ PostgreSQL (Managed: AWS RDS, 2 replicas)              │
│ - Connection pooling (PgBouncer)                       │
│ - Handles 1000s concurrent writes                      │
│                                                         │
│ Vector DB (Pinecone/Qdrant Cloud)                      │
│ - Auto-scaling                                          │
│ - Built for millions of vectors                        │
│                                                         │
│ S3/CloudFlare R2                                       │
│ - Unlimited storage                                     │
│ - CDN for video delivery                               │
└─────────────────────────────────────────────────────────┘
```

**Capacity:**
```
Peak: 20 workers × 4 concurrency × 60 videos/hour = 4,800 videos/hour
Daily: 115,200 videos/day
Can handle: 50K+ users easily
```

**Cost breakdown (AWS):**
```
Base (100 videos/day):
├─ ECS Fargate (3 workers): $100/month
├─ RDS PostgreSQL (db.t3.medium): $50/month
├─ ElastiCache Redis: $15/month
├─ S3 storage (100 GB): $2.30/month
├─ Pinecone (free tier): $0/month
└─ Total: ~$170/month

Peak (10K users spike):
├─ ECS Fargate (20 workers): $650/month
├─ RDS PostgreSQL (db.t3.large): $150/month
├─ ElastiCache Redis: $50/month
├─ S3 storage (1 TB): $23/month
├─ Pinecone (starter): $70/month
├─ OpenAI API: $500/month (10K videos × captions+transcripts)
└─ Total: ~$1,450/month (during spike)
```

---

## Answer to Your Question

**Can your current architecture handle 10K users overnight?**

**NO. Hell no.**

- Current capacity: **1,680 videos/day**
- 10K users (1 video each): **10,000 videos needed**
- **You'd need 6 days to process the backlog**

**What you need:**

### 1. Immediate (survive the spike):
- Scale to 6 Celery workers (docker-compose replicas)
- Optimize to 1 min/video (reduce frames, batch API calls)
- Upgrade OpenAI tier to handle rate limits
- **Capacity: ~8,600 videos/day** → barely survive

### 2. Short-term (1 week):
- Migrate off Pixeltable → PostgreSQL + Vector DB
- Deploy on cloud (AWS ECS/GCP Cloud Run)
- Auto-scaling workers (3-20 instances)
- **Capacity: 100K+ videos/day** → comfortable

### 3. Long-term (1 month):
- Multi-region deployment
- Priority queues (paid users first)
- Video preprocessing optimization
- **Capacity: Unlimited** → ready for scale

**Bottom line: You'd survive with emergency scaling, but users would wait hours. Not ideal.**
