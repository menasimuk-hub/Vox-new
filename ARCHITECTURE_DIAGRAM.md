# VOXBULK Architecture Diagram

## System Overview

VOXBULK is a multi-tenant B2B SaaS platform for businesses across industries, providing AI-powered communication services including WhatsApp surveys, voice agents, appointment scheduling, and CRM integrations.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              VOXBULK PLATFORM                                    │
│                                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐              │
│  │   Public Site    │  │    Dashboard     │  │     Admin Panel  │              │
│  │  (voxbulk.com)   │  │ (dashboard.vox)  │  │  (admin.voxbulk) │              │
│  │                  │  │                  │  │                  │              │
│  │  React/TanStack  │  │  React/TanStack  │  │  React/Vite      │              │
│  │  Port: 5173      │  │  Port: 5175      │  │  Port: 5174      │              │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘              │
│           │                     │                     │                         │
│           └─────────────────────┼─────────────────────┘                         │
│                                 │                                               │
│                                 ▼                                               │
│                    ┌──────────────────────┐                                     │
│                    │     FastAPI Backend  │                                     │
│                    │     (voxbulk-api)    │                                     │
│                    │                      │                                     │
│                    │  Python 3.11+         │                                     │
│                    │  Port: 8000          │                                     │
│                    │  Uvicorn Server      │                                     │
│                    └──────────┬───────────┘                                     │
│                               │                                                 │
└───────────────────────────────┼───────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   Database    │     │     Redis     │     │   External    │
│               │     │               │     │  Integrations │
│ MySQL/SQLite  │     │               │     │               │
│ Alembic Migrations│   │ Celery Queue  │     │ • Telnyx      │
│               │     │               │     │ • Vapi        │
│ Models:       │     │ • Broker      │     │ • GoCardless  │
│ • User        │     │ • Result      │     │ • Stripe      │
│ • Organisation│     │               │     │ • Airwallex   │
│ • Subscription│     │               │     │ • HubSpot     │
│ • Survey      │     │               │     │ • Pipedrive   │
│ • Appointment │     │               │     │ • Zoho CRM    │
│ • Agent       │     │               │     │ • Calendly    │
│ • Billing     │     │               │     │ • Google Cal  │
└───────────────┘     └───────────────┘     └───────────────┘
```

## Backend Architecture (FastAPI)

### Core Components

```
main.py (Entry Point)
├── Lifespan Management
│   ├── Database Initialization
│   ├── Local Demo Account Creation
│   ├── Email Template Seeding
│   ├── Platform Services Setup
│   └── Scheduler Startup
├── Middleware
│   ├── CORS
│   ├── TrustedHost
│   └── Exception Handlers
└── Router Registration (45+ routers)
```

### Directory Structure

```
voxbulk-api/
├── app/
│   ├── core/              # Configuration & utilities
│   │   ├── config.py      # Pydantic settings
│   │   ├── database.py    # SQLAlchemy session management
│   │   ├── security.py    # JWT & encryption
│   │   └── logging.py     # Structured logging
│   │
│   ├── models/            # SQLAlchemy ORM models (83 models)
│   │   ├── user.py
│   │   ├── organisation.py
│   │   ├── subscription.py
│   │   ├── survey_session.py
│   │   ├── appointment.py
│   │   ├── agent.py
│   │   ├── billing_invoice.py
│   │   └── ... (75+ more)
│   │
│   ├── routers/           # API endpoints (45 routers)
│   │   ├── auth.py
│   │   ├── organisations.py
│   │   ├── dashboard.py
│   │   ├── whatsapp.py
│   │   ├── billing.py
│   │   ├── admin.py
│   │   └── ... (40+ more)
│   │
│   ├── services/          # Business logic (343 services)
│   │   ├── survey_whatsapp_conversation_service.py
│   │   ├── interview_call_dispatch_service.py
│   │   ├── voice_agent_service.py
│   │   ├── billing_lifecycle_service.py
│   │   ├── gocardless_service.py
│   │   ├── hubspot_contact_sync_service.py
│   │   └── ... (337+ more)
│   │
│   ├── schemas/           # Pydantic schemas
│   ├── utils/             # Helper functions
│   ├── workers/           # Celery tasks
│   ├── constants/         # Application constants
│   └── data/              # Seed data
│
├── alembic/               # Database migrations
├── scripts/               # Utility scripts
├── tests/                 # Test suite
└── main.py                # Application entry point
```

## Frontend Architecture

### Public Site (voxbulk.com/frontend)

```
React 19 + TanStack Start + Vite
├── src/
│   ├── routes/            # File-based routing
│   ├── components/        # Reusable UI components (55)
│   ├── lib/               # Utilities & API clients
│   ├── hooks/             # Custom React hooks
│   └── assets/            # Static assets
└── package.json
    ├── @tanstack/react-router
    ├── @tanstack/react-query
    ├── @radix-ui/*        # UI primitives
    ├── tailwindcss
    └── @telnyx/webrtc     # WebRTC integration
```

### Dashboard (dashboard.voxbulk.com/dashboard-web)

```
React 19 + TanStack Start + Vite
├── src/
│   ├── routes/            # 56 route modules
│   ├── components/        # 108 UI components
│   ├── lib/               # 60 utility modules
│   ├── hooks/             # Custom hooks
│   └── server.ts          # Server-side logic
└── package.json
    ├── @tanstack/react-router
    ├── @tanstack/react-query
    ├── @radix-ui/*
    ├── recharts           # Charts
    └── simple-icons       # Integration icons
```

### Admin Panel (admin.voxbulk.com/adim-web)

```
React 18 + React Router + Vite
├── src/
│   ├── components/        # Admin UI components
│   ├── routes/            # Admin routes
│   └── assets/
└── package.json
    ├── react-router-dom
    ├── recharts
    ├── wavesurfer.js      # Audio visualization
    └── @vapi-ai/web       # Vapi integration
```

## Key Data Flows

### 1. WhatsApp Survey Flow

```
User initiates survey
    ↓
Dashboard creates survey_session
    ↓
API generates WhatsApp template
    ↓
Telnyx sends WhatsApp message
    ↓
User responds via WhatsApp
    ↓
Telnyx webhook → API /telnyx/webhooks/messages
    ↓
survey_wa_inbound_parse_service processes response
    ↓
survey_flow_engine_service determines next step
    ↓
survey_whatsapp_template_service generates reply
    ↓
Telnyx sends next message
    ↓
[Repeat until survey complete]
    ↓
survey_results_service compiles results
    ↓
CRM sync (HubSpot/Pipedrive/Zoho)
```

### 2. Voice Agent Call Flow

```
Dashboard initiates call
    ↓
API creates call_log via voice_agent_service
    ↓
Vapi/Telnyx initiates call
    ↓
Voice agent runtime handles conversation
    ↓
Real-time transcription (Whisper/DeepInfra)
    ↓
LLM processes responses (OpenAI/DeepSeek/Groq)
    ↓
Call completes
    ↓
voice_transcription_service processes audio
    ↓
Results stored & CRM sync
```

### 3. Appointment Booking Flow

```
User requests appointment
    ↓
appointment_calendar_service checks availability
    ↓
Integration with Cal.com/Google Calendar/Cronofy
    ↓
appointment_booking_service confirms slot
    ↓
appointment_wa_service sends WhatsApp confirmation
    ↓
CRM sync (HubSpot/Pipedrive/Zoho)
    ↓
appointment_billing_service charges usage
```

### 4. Billing Flow

```
Subscription created/updated
    ↓
gocardless_service/stripe_service handles payment
    ↓
billing_lifecycle_service processes event
    ↓
usage_wallet_service tracks usage
    ↓
invoice_service generates invoice
    ↓
invoice_pdf_service creates PDF
    ↓
billing_email_service sends invoice
    ↓
subscription_cancellation_service handles cancellations
```

## Background Schedulers

The API runs multiple async schedulers:

```
lead_sales_scheduler_loop           # Lead follow-up automation
survey_call_scheduler_loop          # Survey call dispatch
interview_call_scheduler_loop       # Interview call dispatch
career_mailbox_scheduler_loop       # Career mailbox processing
interview_ats_scheduler_loop        # ATS integration
uk_compliance_retention_scheduler_loop # UK compliance
weekly_digest_scheduler_loop        # Weekly digest emails
```

## External Integrations

### Communication Providers
- **Telnyx**: WhatsApp messaging, voice calls, phone numbers
- **Vapi**: Voice AI agents, call handling
- **Twilio**: Alternative voice/messaging provider

### Payment Providers
- **GoCardless**: Direct debit (UK/EU)
- **Stripe**: Card payments
- **Airwallex**: Global payments

### CRM Platforms
- **HubSpot**: CRM & marketing automation
- **Pipedrive**: Sales CRM
- **Zoho CRM**: Business CRM

### Calendar/Scheduling
- **Cal.com**: Scheduling platform
- **Google Calendar**: Calendar integration
- **Cronofy**: Calendar API
- **Microsoft Calendar**: Outlook integration

### AI/ML Services
- **OpenAI**: GPT models
- **DeepSeek**: Alternative LLM
- **Groq**: Fast inference
- **DeepInfra**: Whisper STT, Mistral models
- **ElevenLabs**: Text-to-speech
- **Azure Speech**: Microsoft speech services

### Email Services
- **Resend**: Transactional email
- **SMTP**: Custom email servers

### Industry-Specific
- **Dentally**: Dental practice management

## Database Schema (Key Models)

### Core Entities
- **User**: Authentication & user management
- **Organisation**: Multi-tenant organization
- **OrganisationMembership**: User-org relationships
- **Subscription**: Billing subscriptions
- **Plan**: Pricing plans

### Survey System
- **SurveySession**: Survey instances
- **SurveyFlow**: Survey logic/flows
- **SurveyType**: Survey templates
- **TelnyxWhatsappTemplate**: WhatsApp templates

### Appointment System
- **Appointment**: Booking records
- **DentallyAppointment**: Dentally sync
- **ServiceOrder**: Service requests

### AI/Agents
- **Agent**: AI agent configurations
- **AgentKnowledgeFile**: Agent training data
- **AITeamSettings**: AI team configuration

### Billing
- **BillingInvoice**: Invoice records
- **WalletTransaction**: Wallet transactions
- **PaymentEvent**: Payment events

## Security Architecture

### Authentication
- JWT-based authentication
- 7-day token expiration
- Multi-tenant scoping via JWT claims
- OAuth integration (Google, HubSpot, etc.)

### Authorization
- Role-based access control (RBAC)
- Organisation membership enforcement
- Admin superuser privileges

### Data Protection
- Fernet encryption for sensitive data
- HMAC webhook signature verification
- CORS middleware
- TrustedHost middleware

## Development Workflow

### Local Development
```bash
# Start all services
npm run dev

# Individual services
npm run dev:api      # FastAPI backend
npm run dev:public   # Public frontend
npm run dev:admin    # Admin panel
```

### Database Migrations
```bash
cd voxbulk-api
alembic upgrade head
```

### Testing
```bash
cd voxbulk-api
pytest
```

## Deployment Architecture

### Production VPS
- Nginx reverse proxy
- Supervisor process management
- MySQL database
- Redis for Celery
- SSL/TLS termination

### Environment Variables
- `.env` file for configuration
- Separate configs for dev/staging/production
- CORS origins configured per environment
- Trusted hosts for security

## Monitoring & Observability

### Health Endpoints
- `/health` - Basic health check
- `/health/db` - Database schema verification
- `/health/build` - Deploy verification
- `/health/pricing` - Pricing schema status

### Logging
- Structured JSON logging
- Log levels: INFO, ERROR, DEBUG
- Request/response logging
- Error tracking

## Key Technologies

### Backend
- **FastAPI**: Modern Python web framework
- **SQLAlchemy**: ORM
- **Alembic**: Database migrations
- **Celery**: Background tasks
- **Redis**: Task queue & caching
- **Pydantic**: Data validation
- **Uvicorn**: ASGI server

### Frontend
- **React**: UI library
- **TanStack Start**: Full-stack React framework
- **TanStack Router**: File-based routing
- **TanStack Query**: Data fetching
- **Vite**: Build tool
- **TailwindCSS**: Styling
- **Radix UI**: Component primitives

### Infrastructure
- **Python 3.11+**: Backend runtime
- **Node.js/Bun**: Frontend runtime
- **MySQL/SQLite**: Database
- **Redis**: Caching & queue
- **Nginx**: Reverse proxy

## Scalability Considerations

### Horizontal Scaling
- Stateless API design
- Redis for shared state
- Celery for distributed task processing
- Database connection pooling

### Performance
- Async/await for I/O operations
- Database query optimization
- Caching strategies
- CDN for static assets

### Reliability
- Database migrations
- Error handling & logging
- Webhook retry logic
- Graceful degradation

---

*Generated: June 24, 2026*
*VOXBULK Multi-tenant B2B SaaS Platform*
